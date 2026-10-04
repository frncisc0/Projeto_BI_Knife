import asyncio
import hashlib
import json
from pathlib import Path
import re
import socket
import zipfile
from io import BytesIO

from starlette.datastructures import UploadFile

from app.ai.provider import NoAIProvider
from app.api import routes
from app.api.routes import analyze, analyze_batch
from app.services.analysis_service import analyze_file


def test_sensitive_cell_values_do_not_appear_in_analysis_report():
    secrets = ["12345678901", "person@example.test", "+55 11 99999-1234", "Ana Silva", "9876.54"]
    content = ("cpf,email,telefone,nome,salario\n" + ",".join(secrets) + "\n").encode("utf-8")
    report = analyze_file("synthetic.csv", "csv", content, "utf-8")
    serialized = json.dumps(report.model_dump(mode="json", exclude_none=True), ensure_ascii=False)

    for secret in secrets[:-1]:
        assert secret not in serialized
    assert "preview" not in serialized
    columns = {column.name: column for column in report.tables[0].column_analyses}
    assert all(columns[name].sensitive for name in ("cpf", "email", "telefone"))
    assert not columns["nome"].sensitive and not columns["salario"].sensitive
    assert all(not columns[name].statistics.model_dump(exclude_none=True) for name in ("cpf", "email", "telefone"))


def test_ambiguous_header_defaults_to_generic_names_and_masks_detected_pii():
    emails = ["ana@example.test", "bia@example.test"]
    phones = ["5511999991234", "5511888885678"]
    content = f"{emails[0]},{phones[0]}\n{emails[1]},{phones[1]}\n".encode()
    report = analyze_file("no-header.csv", "csv", content, "utf-8")
    serialized = json.dumps(report.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
    assert report.tables[0].column_analyses[0].name == "0"
    assert report.warnings
    assert all(secret not in serialized for secret in emails)
    assert report.tables[0].column_analyses[0].sensitive
    assert not report.tables[0].column_analyses[1].sensitive


def test_ambiguous_mixed_type_first_row_is_not_exposed_as_a_header():
    first_row_value = "Ana"
    content = b"Ana,unknown\nBia,10\n"
    report = analyze_file("mixed-no-header.csv", "csv", content, "utf-8")
    serialized = json.dumps(report.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
    assert first_row_value not in serialized
    assert [column.name for column in report.tables[0].column_analyses] == ["0", "1"]
    assert any("ambígua" in warning for warning in report.warnings)


def test_unexpected_error_logs_only_exception_type(monkeypatch, caplog):
    secret = "person@example.test"

    def fail_with_sensitive_text(*args, **kwargs):
        raise RuntimeError(f"parser context included {secret}")

    monkeypatch.setattr(routes, "analyze_file", fail_with_sensitive_text)
    upload = UploadFile(filename="synthetic.csv", file=BytesIO(b"email\nperson@example.test\n"))
    with caplog.at_level("ERROR"):
        result = asyncio.run(analyze_batch([upload], "auto", "auto", "auto"))
    assert result["results"][0]["error"]
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_single_upload_logs_do_not_include_cell_values(monkeypatch, caplog):
    secret = "98765432100"

    def fail_with_sensitive_text(*args, **kwargs):
        raise RuntimeError(f"parser context included {secret}")

    monkeypatch.setattr(routes, "analyze_file", fail_with_sensitive_text)
    upload = UploadFile(filename="synthetic.csv", file=BytesIO(f"cpf\n{secret}\n".encode()))
    with caplog.at_level("ERROR"):
        try:
            asyncio.run(analyze(upload, "auto", "auto", "auto"))
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 500
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_default_ai_provider_is_disabled():
    provider = NoAIProvider()
    assert provider.enabled is False
    assert provider.name == "none"


def test_analysis_succeeds_when_network_connections_are_disabled(monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("A análise tentou abrir conexão de rede.")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    upload = UploadFile(filename="synthetic.csv", file=BytesIO(b"id,valor\n1,10\n2,20\n"))
    report = asyncio.run(analyze(upload, "auto", "auto", "auto"))
    assert report["status"] == "completed"


def test_xlsx_external_relationship_is_never_followed(monkeypatch):
    from openpyxl import Workbook

    def deny_network(*args, **kwargs):
        raise AssertionError("O processamento Excel tentou abrir uma conexão de rede.")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    workbook = Workbook()
    workbook.active.append(["id", "amount"])
    workbook.active.append([1, 10])
    buffer = BytesIO()
    workbook.save(buffer)
    modified = BytesIO()
    with zipfile.ZipFile(BytesIO(buffer.getvalue())) as original, zipfile.ZipFile(modified, "w", zipfile.ZIP_DEFLATED) as updated:
        for name in original.namelist():
            data = original.read(name)
            if name == "_rels/.rels":
                data = data.replace(b"</Relationships>", b'<Relationship Id="rIdOutside" TargetMode="External" Target="https://example.invalid/source" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"/></Relationships>')
            updated.writestr(name, data)
        updated.writestr("xl/connections.xml", "<connections />")
    upload = UploadFile(filename="external.xlsx", file=BytesIO(modified.getvalue()))
    report = asyncio.run(analyze(upload, "auto", "auto", "auto"))

    assert report["status"] == "completed"
    assert report["security"]["external_relationships_detected"] is True
    assert report["security"]["external_relationships_followed"] is False
    assert report["security"]["external_connections_accessed"] is False
    assert "connection_definition" in report["security"]["active_content_types"]


def test_production_sources_have_no_external_network_clients_or_urls():
    project_root = Path(__file__).resolve().parents[2]
    production_files = [*project_root.joinpath("app").rglob("*.py"),
                        *project_root.joinpath("frontend").rglob("*.html"),
                        *project_root.joinpath("frontend").rglob("*.js"),
                        *project_root.joinpath("frontend").rglob("*.css")]
    source = "\n".join(path.read_text(encoding="utf-8") for path in production_files)
    assert not re.search(r"https?://", source, flags=re.IGNORECASE)
    assert not re.search(r"(?:from|import)\s+(?:requests|httpx|urllib|socket|smtplib)\b", source)
    fetch_targets = re.findall(r"fetch\(\s*['\"`]([^'\"`]+)", source)
    assert all(target.startswith("/") and not target.startswith("//") for target in fetch_targets)


def test_uploaded_original_files_remain_byte_for_byte_unchanged(tmp_path):
    from openpyxl import Workbook

    csv_path = tmp_path / "synthetic.csv"
    csv_path.write_bytes(b"id,valor\n1,10\n2,20\n")
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["id", "valor"])
    worksheet.append([1, "=SUM(1,2)"])
    xlsx_path = tmp_path / "synthetic.xlsx"
    workbook.save(xlsx_path)

    for path in (csv_path, xlsx_path):
        original = path.read_bytes()
        original_hash = hashlib.sha256(original).hexdigest()
        upload = UploadFile(filename=path.name, file=path.open("rb"))
        result = asyncio.run(analyze(upload, "auto", "auto", "auto"))
        assert result["file_sha256"] == original_hash
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
        assert upload.file.closed
        if path.suffix == ".xlsx":
            assert "=SUM(1,2)" not in json.dumps(result, ensure_ascii=False)


def test_sensitive_columns_are_excluded_from_cross_file_relationship_matching():
    uploads = [
        UploadFile(filename="people.csv", file=BytesIO(b"cpf,nome\n123.456.789-00,Ana Silva\n987.654.321-00,Bia Lima\n")),
        UploadFile(filename="payments.csv", file=BytesIO(b"cpf,amount\n123.456.789-00,100\n987.654.321-00,200\n")),
    ]
    result = asyncio.run(analyze_batch(uploads, "auto", "auto", "auto"))
    serialized = json.dumps(result, ensure_ascii=False)
    assert result["relationships"] == []
    assert "123.456.789-00" not in serialized
    assert "987.654.321-00" not in serialized


def test_sensitive_columns_are_excluded_from_workbook_relationship_matching():
    from openpyxl import Workbook

    workbook = Workbook()
    people = workbook.active
    people.title = "Pessoas"
    people.append(["CPF"])
    people.append(["123.456.789-00"])
    people.append(["987.654.321-00"])
    payroll = workbook.create_sheet("Folha")
    payroll.append(["CPF"])
    payroll.append(["123.456.789-00"])
    payroll.append(["987.654.321-00"])
    content = BytesIO()
    workbook.save(content)

    report = analyze_file("sensitive.xlsx", "xlsx", content.getvalue())
    serialized = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert report.relationships == []
    assert all(column.sensitive for table in report.tables for column in table.column_analyses)
    assert "123.456.789-00" not in serialized
    assert "987.654.321-00" not in serialized
