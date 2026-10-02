from io import BytesIO
import zipfile

from openpyxl import Workbook

from app.security.file_validation import validate_upload_detailed
from app.services.analysis_service import analyze_file
from app.services.report_service import report_payload


def test_xlsx_detects_sheets_and_relationships():
    workbook = Workbook()
    customers = workbook.active
    customers.title = "Clientes"
    customers.append(["id", "nome"])
    customers.append([10, "Ana"])
    customers.append([20, "Bia"])
    orders = workbook.create_sheet("Pedidos")
    orders.append(["pedido", "id"])
    orders.append([100, 10])
    orders.append([101, 20])
    buffer = BytesIO()
    workbook.save(buffer)

    report = analyze_file("sample.xlsx", "xlsx", buffer.getvalue())
    assert {table.name for table in report.tables} == {"Clientes", "Pedidos"}
    assert report.relationships
    assert report.relationships[0].coverage_pct == 100


def test_relationship_confidence_is_limited_when_tables_are_sampled(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "enable_sampling", True)
    monkeypatch.setattr(settings, "sample_size", 1)

    workbook = Workbook()
    customers = workbook.active
    customers.title = "Clientes"
    customers.append(["cliente_id"])
    customers.append([10])
    customers.append([20])
    orders = workbook.create_sheet("Pedidos")
    orders.append(["cliente_id"])
    orders.append([10])
    orders.append([10])
    buffer = BytesIO()
    workbook.save(buffer)

    report = analyze_file("sampled.xlsx", "xlsx", buffer.getvalue())
    assert report.relationships
    assert report.relationships[0].confidence == "medium"
    assert "amostra" in report.relationships[0].reason


def test_xlsx_combined_profile_cell_limit_is_shared_across_sheets(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_xlsx_profile_cells", 4)
    workbook = Workbook()
    first = workbook.active
    first.title = "First"
    first.append(["id", "amount"])
    first.append([1, 10])
    first.append([2, 20])
    second = workbook.create_sheet("Second")
    second.append(["id", "amount"])
    second.append([3, 30])
    second.append([4, 40])
    buffer = BytesIO()
    workbook.save(buffer)

    report = analyze_file("limited.xlsx", "xlsx", buffer.getvalue())
    assert sum(table.rows_analyzed * table.columns_analyzed for table in report.tables) <= 4
    assert report.tables[1].rows_analyzed == 0
    assert report.settings["max_xlsx_profile_cells"] == 4


def _add_xlsx_parts(content: bytes, parts: dict[str, bytes], stored_parts: set[str] | None = None) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(content)) as original, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as updated:
        for name in original.namelist():
            updated.writestr(name, original.read(name))
        for name, value in parts.items():
            compression = zipfile.ZIP_STORED if stored_parts and name in stored_parts else zipfile.ZIP_DEFLATED
            updated.writestr(name, value, compress_type=compression)
    return output.getvalue()


def test_detected_vba_and_embedded_content_are_reported_but_sheets_are_analyzed(monkeypatch):
    import app.analyzers.file_analyzer as file_analyzer

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Resumo"
    worksheet.append(["employee_id", "hours"])
    worksheet.append([101, 40])
    buffer = BytesIO()
    workbook.save(buffer)
    content = _add_xlsx_parts(buffer.getvalue(), {
        "xl/vbaProject.bin": b"synthetic-vba",
        "xl/embeddings/object.bin": b"synthetic-object",
        "xl/activeX/activeX1.bin": b"synthetic-control",
        "xl/connections.xml": b"<connections />",
        "xl/externalLinks/externalLink1.xml": b"<externalLink />",
    })

    filename, file_type, encoding, security = validate_upload_detailed("safe-test.xlsm", content)
    original_loader = file_analyzer.load_workbook
    loader_options = []

    def safe_loader(*args, **kwargs):
        loader_options.append(kwargs.copy())
        return original_loader(*args, **kwargs)

    monkeypatch.setattr(file_analyzer, "load_workbook", safe_loader)
    report = analyze_file(filename, file_type, content, encoding, security_metadata=security)
    serialized = report.model_dump(mode="json")

    assert report.status == "completed"
    assert report.file_type == "xlsm"
    assert report.tables[0].name == "Resumo"
    assert report.tables[0].header_row_used == 1
    assert report.tables[0].rows == 1
    assert set(report.security.active_content_types) == {
        "macro", "embedded_object", "activeX_control", "connection_definition", "external_link",
    }
    assert report.security.active_content_action == "not_executed"
    assert report.security.macros_executed is False
    assert report.security.external_connections_accessed is False
    assert report.security.external_connections_updated is False
    assert report.security.embedded_objects_executed is False
    assert report.security.formulas_recalculated is False
    assert serialized["security"]["external_relationships_followed"] is False
    assert loader_options[0] == {"read_only": True, "data_only": True, "keep_links": False, "keep_vba": False}


def test_formula_is_not_recalculated_or_included_as_cell_content():
    import json

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["formula_result"])
    worksheet.append(['=HYPERLINK("https://example.invalid/secret", "open")'])
    buffer = BytesIO()
    workbook.save(buffer)
    content = buffer.getvalue()
    filename, file_type, encoding, security = validate_upload_detailed("formula.xlsx", content)
    report = analyze_file(filename, file_type, content, encoding, security_metadata=security)
    output = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert report.security.formulas_action == "cached_values_only"
    assert report.tables[0].column_analyses[0].null_count == 1
    assert "HYPERLINK" not in output
    assert "example.invalid" not in output


def test_sheet_failure_is_recorded_without_losing_other_sheets(monkeypatch):
    import app.analyzers.file_analyzer as file_analyzer

    class Worksheet:
        def __init__(self, title, broken=False):
            self.title = title
            self.max_row = 2
            self.max_column = 2
            self.broken = broken

        def iter_rows(self, **kwargs):
            if self.broken:
                raise ValueError("synthetic private parser detail")
            return iter([("id", "amount"), (1, 25)])

    class FakeWorkbook:
        worksheets = [Worksheet("Good"), Worksheet("Broken", broken=True), Worksheet("AlsoGood")]

        def close(self):
            self.closed = True

    fake_workbook = FakeWorkbook()
    monkeypatch.setattr(file_analyzer, "load_workbook", lambda *args, **kwargs: fake_workbook)
    report = analyze_file("partial.xlsx", "xlsx", b"synthetic package", security_metadata={})
    serialized = report.model_dump_json()

    assert report.status == "partial"
    assert [table.status for table in report.tables] == ["completed", "failed", "completed"]
    assert report.tables[1].error_message == "Falha de leitura da aba (ValueError)."
    assert "synthetic private parser detail" not in serialized
    assert fake_workbook.closed is True


def test_synthetic_xlsx_around_30mb_is_profiled_with_bounded_sheet_rows():
    import hashlib

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Data"
    worksheet.append(["id", "amount"])
    for row in range(1, 1001):
        worksheet.append([row, row * 10])
    buffer = BytesIO()
    workbook.save(buffer)
    payload_size = 30 * 1024 * 1024
    content = _add_xlsx_parts(buffer.getvalue(), {"custom/unused-test-payload.bin": b"x" * payload_size},
                              stored_parts={"custom/unused-test-payload.bin"})
    original_hash = hashlib.sha256(content).hexdigest()
    filename, file_type, encoding, security = validate_upload_detailed("synthetic-large.xlsx", content)
    report = analyze_file(filename, file_type, content, encoding, security_metadata=security)
    payload = report_payload(report)

    assert report.file_size_bytes >= payload_size
    assert report.file_sha256 == original_hash
    assert report.status == "completed"
    assert report.tables[0].rows == 1000
    assert report.tables[0].rows_analyzed <= 100000
    assert payload["tables"][0]["name"] == "Data"
