from io import BytesIO
import zipfile
import json
from pathlib import Path

from openpyxl import Workbook

from app.security.file_validation import validate_upload_detailed
from app.services.analysis_service import analyze_file
from app.services.report_service import report_payload
from app.services.html_report_service import render_html_report
from app.services.pdf_report_service import render_pdf_report


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


def test_sample_workbook_exports_all_formats_from_one_analysis_result(monkeypatch):
    import app.services.analysis_service as analysis_service

    source = Path(__file__).resolve().parents[2] / "test-data" / "sample.xlsx"
    content = source.read_bytes()
    original_analyzer = analysis_service.analyze_file
    calls = []

    def counted_analyzer(*args, **kwargs):
        calls.append(args[0])
        return original_analyzer(*args, **kwargs)

    monkeypatch.setattr(analysis_service, "analyze_file", counted_analyzer)
    result = analysis_service.analyze_file(source.name, "xlsx", content)
    json_report = report_payload(result)
    batch = {"file_count": 1, "results": [{"filename": source.name, "analysis": json_report, "error": None}]}
    json_text = json.dumps(batch, ensure_ascii=False)
    decoded = json.loads(json_text)
    html = render_html_report(decoded)
    pdf = render_pdf_report(decoded)

    assert calls == [source.name]
    assert decoded["results"][0]["analysis"]["analysis_id"] == result.analysis_id
    assert source.name in html and "Qualidade geral" in html
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")


def test_target_like_sheets_keep_semantic_roles_consistent_and_export_together():
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = {
        "Risco Consolidado - Fornecedor": (
            ["Fornecedor", "Gestor", "Risco Consolidado - Fornecedor", "Custo da Folha", "Contrato SAP"],
            [["Fornecedor A", "Ana", 10, "R$ 1.000,00", "SAP-001"],
             ["Fornecedor B", "Bia", 20, "R$ 2.000,00", "SAP-001"],
             ["Fornecedor C", "Caio", 30, "R$ 3.000,00", "SAP-003"]]),
        "Risco - Contratos Ativos": (
            ["Contrato", "Quantidade de Colaboradores", "Custo de Rescisão", "Status"],
            [["CT-001", 10, "R$ 100,00", "Ativo"],
             ["CT-002", 20, "R$ 200,00", "Ativo"],
             ["CT-003", 30, "R$ 300,00", "Encerrado"]]),
        "Risco Completo": (
            ["Custo Rescisório Total", "Aderência", "Conformidade"],
            [[1000, 95, 99], [2000, 90, 97], [3000, 85, 95]]),
        "Relação de Colaboradores": (
            ["Empresa Enel", "Gestor", "Função", "Quantidade de Colaboradores"],
            [["Enel A", "Ana", "Analista", 10], ["Enel B", "Bia", "Técnica", 20],
             ["Enel A", "Ana", "Analista", 30]]),
        "Resumo Encargos": (
            ["Encargo", "Retenção", "Garantia", "Passivo", "Processo"],
            [[100, 10, 20, 30, 1], [200, 20, 30, 40, 2], [300, 30, 40, 50, 3]]),
    }
    for name, (headers, rows) in sheets.items():
        worksheet = workbook.create_sheet(name)
        worksheet.append(headers)
        for row in rows:
            worksheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)

    analysis = analyze_file("semantic-regression.xlsx", "xlsx", buffer.getvalue())
    payload = report_payload(analysis)
    batch = {"file_count": 1, "results": [{"filename": analysis.filename, "analysis": payload, "error": None}]}
    serialized = json.dumps(batch, ensure_ascii=False)
    html = render_html_report(json.loads(serialized))
    pdf = render_pdf_report(json.loads(serialized))
    columns = {column.name: column for table in analysis.tables for column in table.column_analyses}

    assert {table.name for table in analysis.tables} == set(sheets)
    for name in ("Risco Consolidado - Fornecedor", "Custo da Folha", "Custo de Rescisão",
                 "Custo Rescisório Total", "Quantidade de Colaboradores",
                 "Aderência", "Conformidade", "Encargo", "Retenção", "Garantia", "Passivo", "Processo"):
        assert columns[name].semantic_role == "measure", name
    for name in ("Fornecedor", "Gestor", "Status", "Empresa Enel", "Função"):
        assert columns[name].semantic_role == "category", name
    assert columns["Contrato SAP"].semantic_role == "identifier"
    assert columns["Contrato SAP"].key_candidate is False
    assert json.loads(serialized)["results"][0]["analysis"]["analysis_id"] == analysis.analysis_id
    assert "Qualidade geral" in html and pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")


def test_xlsx_xml_declaration_is_accepted_and_workbook_is_analyzed():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Risco"
    sheet.append(["id", "descricao"])
    sheet.append([1, "Exemplo"])
    buffer = BytesIO()
    workbook.save(buffer)

    with zipfile.ZipFile(BytesIO(buffer.getvalue())) as archive:
        worksheet_xml = archive.read("xl/worksheets/sheet1.xml")
    declared_xml = b'<?xml version="1.0" encoding="UTF-8"?>' + worksheet_xml
    content = _add_xlsx_parts(buffer.getvalue(), {"xl/worksheets/sheet1.xml": declared_xml})

    filename, file_type, encoding, security = validate_upload_detailed("declared.xlsx", content)
    report = analyze_file(filename, file_type, content, encoding, security_metadata=security)

    assert report.status == "completed"
    assert report.tables[0].name == "Risco"
    assert report.tables[0].columns_analyzed == 2
    assert report.tables[0].rows == 1


def test_xlsx_utf16_xml_is_not_rejected_for_containing_nul_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "UTF16"
    sheet.append(["id"])
    sheet.append([1])
    buffer = BytesIO()
    workbook.save(buffer)

    with zipfile.ZipFile(BytesIO(buffer.getvalue())) as archive:
        worksheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    declared_xml = '<?xml version="1.0" encoding="UTF-16"?>' + worksheet_xml
    content = _add_xlsx_parts(
        buffer.getvalue(),
        {"xl/worksheets/sheet1.xml": declared_xml.encode("utf-16")},
    )

    filename, file_type, encoding, security = validate_upload_detailed("utf16.xlsx", content)
    report = analyze_file(filename, file_type, content, encoding, security_metadata=security)

    assert report.tables[0].name == "UTF16"
    assert report.tables[0].rows == 1


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


def test_xlsx_header_after_title_and_inflated_used_range_excludes_trailing_rows():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Risco"
    sheet.merge_cells("A1:E1")
    sheet["A1"] = "Relatório de risco trabalhista"
    sheet.append([])
    sheet.append(["Empresa Parceira", "Contrato", "Fornecedor", "Valor", "Data"])
    sheet.append(["Empresa A", "C-1", "Fornecedor A", 100, "2026-01-01"])
    sheet.append([None, None, None, None, None])
    sheet.append(["Empresa B", "C-2", "Fornecedor B", 200, "2026-01-02"])
    sheet["A10000"].number_format = "@"
    buffer = BytesIO()
    workbook.save(buffer)

    report = analyze_file("used-range.xlsx", "xlsx", buffer.getvalue())
    table = report.tables[0]

    assert table.header_row_used == 3
    assert table.header_detection["status"] == "detected"
    assert table.header_detection["header_source"] == "worksheet"
    assert [column.name for column in table.column_analyses] == [
        "Empresa Parceira", "Contrato", "Fornecedor", "Valor", "Data",
    ]
    assert table.rows_available == table.rows == 2
    assert table.rows_analyzed == 2
    assert table.rows_empty == 1
    assert table.trailing_empty_rows >= 9990
    assert table.empty_rows == 1
    assert table.status == "completed"


def test_xlsx_without_reliable_header_generates_names_but_keeps_all_rows():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([1001, 42])
    sheet.append([1002, 43])
    sheet.append([1003, 44])
    buffer = BytesIO()
    workbook.save(buffer)

    table = analyze_file("headerless.xlsx", "xlsx", buffer.getvalue()).tables[0]
    assert table.header_detection["status"] == "generated"
    assert table.header_detection["header_source"] == "generated"
    assert table.header_row_used is None
    assert [column.name for column in table.column_analyses] == ["Coluna 1", "Coluna 2"]
    assert table.rows_available == table.rows_analyzed == 3


def test_xlsx_empty_worksheet_is_completed_empty_not_completed_with_zero_rows():
    workbook = Workbook()
    workbook.active.title = "Vazia"
    buffer = BytesIO()
    workbook.save(buffer)

    table = analyze_file("empty-sheet.xlsx", "xlsx", buffer.getvalue()).tables[0]
    assert table.status == "completed_empty"
    assert table.rows_available == table.rows_analyzed == 0
    assert table.quality.classification == "Atenção"
    assert all(alert["severity"] != "critical" for alert in table.quality.alerts)


def test_xlsx_sampling_uses_nonempty_rows_and_reports_method(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "sample_size", 4)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["id", "valor"])
    for row in range(1, 21):
        sheet.append([row, row * 10])
    sheet["A10000"].number_format = "@"
    buffer = BytesIO()
    workbook.save(buffer)

    table = analyze_file("sampled-bounds.xlsx", "xlsx", buffer.getvalue()).tables[0]
    assert table.rows_available == 20
    assert table.rows_analyzed == 4
    assert table.sampled is True
    assert table.sampling_method == "uniform_reservoir"
    assert table.trailing_empty_rows >= 9970


def _add_xlsx_parts(content: bytes, parts: dict[str, bytes], stored_parts: set[str] | None = None) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(content)) as original, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as updated:
        for name in original.namelist():
            if name not in parts:
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
    assert report.tables[0].status == "completed_empty"
    assert report.tables[0].rows_analyzed == 0
    assert report.tables[0].column_analyses[0].name == "formula_result"
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
