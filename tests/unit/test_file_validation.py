import io
import zipfile

import pytest

from app.core.exceptions import FileValidationError
from app.security.file_validation import display_filename, validate_filename, validate_upload, validate_upload_detailed


def test_path_like_filename_is_reduced_to_basename():
    filename, extension = validate_filename(r"..\private\sales.csv")
    assert filename == "sales.csv"
    assert extension == ".csv"


def test_display_filename_preserves_only_safe_relative_label():
    assert display_filename(r"C:\\Sales\\2026\\jan.csv") == "Sales/2026/jan.csv"
    assert display_filename("../../private.csv") == "private.csv"


def test_disallowed_extension_is_rejected():
    with pytest.raises(FileValidationError):
        validate_upload("macro.xlsm", b"not a workbook")


def test_xlsx_requires_workbook_structure():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "not excel")
    with pytest.raises(FileValidationError):
        validate_upload("fake.xlsx", buffer.getvalue())


def test_xlsx_external_relationships_are_reported_without_blocking_package():
    from openpyxl import Workbook

    workbook = Workbook()
    buffer = io.BytesIO()
    workbook.save(buffer)
    source = buffer.getvalue()
    modified = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(modified, "w", zipfile.ZIP_DEFLATED) as updated:
        for name in original.namelist():
            data = original.read(name)
            if name == "_rels/.rels":
                data = data.replace(b"</Relationships>", b'<Relationship Id="rIdExternal" TargetMode="External" Target="https://example.invalid/source" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"/></Relationships>')
            updated.writestr(name, data)

    name, kind, encoding, security = validate_upload_detailed("external.xlsx", modified.getvalue())
    assert (name, kind, encoding) == ("external.xlsx", "xlsx", None)
    assert security["external_relationships_detected"] is True
    assert security["active_content_types"] == ["external_relationship"]


def test_xlsm_vba_project_is_reported_without_blocking_package():
    from openpyxl import Workbook

    workbook = Workbook()
    buffer = io.BytesIO()
    workbook.save(buffer)
    modified = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as original, zipfile.ZipFile(modified, "w", zipfile.ZIP_DEFLATED) as updated:
        for name in original.namelist():
            updated.writestr(name, original.read(name))
        updated.writestr("xl/vbaProject.bin", b"synthetic-vba-project")

    name, kind, encoding, security = validate_upload_detailed("macro.xlsm", modified.getvalue())
    assert (name, kind, encoding) == ("macro.xlsm", "xlsm", None)
    assert security["active_content_detected"] is True
    assert security["active_content_types"] == ["macro"]


def test_xlsx_xml_entity_declarations_are_rejected_before_parsing():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<!DOCTYPE worksheet [<!ENTITY expanded "synthetic">]><worksheet>&expanded;</worksheet>',
        )
    with pytest.raises(FileValidationError, match="declarações XML"):
        validate_upload("entity.xlsx", buffer.getvalue())


def test_analysis_service_validates_xlsx_xml_before_openpyxl(monkeypatch):
    from openpyxl import Workbook

    import app.analyzers.file_analyzer as file_analyzer
    from app.services.analysis_service import analyze_file

    workbook = Workbook()
    buffer = io.BytesIO()
    workbook.save(buffer)
    unsafe = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as original, zipfile.ZipFile(unsafe, "w", zipfile.ZIP_DEFLATED) as updated:
        for name in original.namelist():
            if name == "xl/worksheets/sheet1.xml":
                updated.writestr(name, '<!DOCTYPE worksheet [<!ENTITY secret "blocked">]><worksheet>&secret;</worksheet>')
            else:
                updated.writestr(name, original.read(name))

    def parser_must_not_run(*args, **kwargs):
        pytest.fail("OpenPyXL foi chamado antes da validação de XML.")

    monkeypatch.setattr(file_analyzer, "load_workbook", parser_must_not_run)
    with pytest.raises(FileValidationError, match="declarações XML"):
        analyze_file("unsafe.xlsx", "xlsx", unsafe.getvalue())


def test_csv_accepts_latin1_semicolon():
    name, kind, encoding = validate_upload("fornecedores.csv", "id;nome\n1;André\n".encode("cp1252"))
    assert (name, kind) == ("fornecedores.csv", "csv")
    assert encoding in {"cp1252", "latin-1"}


def test_empty_csv_is_rejected():
    with pytest.raises(FileValidationError, match="vazio"):
        validate_upload("empty.csv", b"")


def test_utf8_semicolon_csv_is_accepted():
    name, kind, encoding = validate_upload("sales.csv", "id;valor\n1;15\n".encode("utf-8"))
    assert name == "sales.csv"
    assert kind == "csv"
    assert encoding.startswith("utf-8")
