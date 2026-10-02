import io
import zipfile

import pytest

from app.core.exceptions import FileValidationError
from app.security.file_validation import display_filename, validate_filename, validate_upload


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


def test_xlsx_external_relationships_are_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("_rels/.rels", '<Relationships><Relationship TargetMode="External" Target="https://example.test"/></Relationships>')
    with pytest.raises(FileValidationError, match="referências externas"):
        validate_upload("external.xlsx", buffer.getvalue())


def test_xlsx_embedded_macro_content_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/vbaProject.bin", b"synthetic-macro")
    with pytest.raises(FileValidationError, match="macros"):
        validate_upload("macro.xlsx", buffer.getvalue())


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
