import pytest

from app.core.exceptions import FileValidationError
from app.security.file_validation import validate_upload_detailed
from app.services.analysis_service import analyze_file


def _analyze(name: str, content: bytes, **options):
    filename, file_type, encoding, security = validate_upload_detailed(name, content)
    return analyze_file(filename, file_type, content, encoding, security_metadata=security, **options)


@pytest.mark.parametrize(
    ("delimiter", "content"),
    [
        (",", b"id,name\n001,Ana\n002,Bia\n"),
        (";", "id;nome\n001;João\n002;Bia\n".encode("utf-8")),
        ("\t", "id\tnome\n001\tJoão\n002\tBia\n".encode("utf-8")),
    ],
)
def test_delimiters_and_values_reach_the_shared_analysis_pipeline(delimiter, content):
    report = _analyze("sample.csv", content, csv_delimiter=delimiter, header_mode="true")
    table = report.tables[0]
    assert table.rows == 2
    assert table.columns == 2
    assert table.column_analyses[0].name == "id"
    assert report.settings["csv_delimiter"] == delimiter


def test_utf8_bom_cp1252_and_accented_headers_are_supported():
    bom_report = _analyze("bom.csv", b"\xef\xbb\xbfnome,cidade\nJo\xc3\xa3o,S\xc3\xa3o Paulo\n", header_mode="true")
    cp_report = _analyze("windows.csv", "nome,cidade\nJoão,São Paulo\n".encode("cp1252"), header_mode="true")
    assert [column.name for column in bom_report.tables[0].column_analyses] == ["nome", "cidade"]
    assert cp_report.tables[0].rows == 1
    assert cp_report.settings["csv_encoding"] == "cp1252"


def test_quoted_delimiters_empty_values_and_mixed_types_are_preserved():
    content = 'id,comment,value\n001,"vendas, varejo",10\n002,"texto com ""aspas""",\n003,texto,indefinido\n'.encode()
    report = _analyze("quoted.csv", content, csv_delimiter=",", header_mode="true")
    table = report.tables[0]
    assert table.rows == 3
    assert table.column_analyses[0].name == "id"
    assert table.column_analyses[2].null_count == 1
    assert report.settings["csv_delimiter"] == ","


def test_headerless_small_and_single_column_csvs_are_analyzed():
    report = _analyze("headerless.csv", b"001;10\n002;20\n", csv_delimiter=";", header_mode="false")
    one_column = _analyze("one-column.csv", b"value\n1\n2\n", csv_delimiter=",", header_mode="true")
    assert report.tables[0].rows == 2
    assert [column.name for column in report.tables[0].column_analyses] == ["0", "1"]
    assert one_column.tables[0].columns == 1
    assert one_column.tables[0].rows_analyzed == 2
    assert any("possui apenas uma coluna" in warning for warning in one_column.warnings)


def test_csv_reader_preserves_zero_padded_source_values():
    from app.analyzers.file_analyzer import read_tables

    frame = read_tables(b"codigo\n00123\n", "csv", "utf-8", header_mode="true")["Dados"]
    assert frame.iloc[0, 0] == "00123"


@pytest.mark.parametrize("content", [b"", b"\n\r\n", b"a,b\n1,2\n3\n"])
def test_empty_or_inconsistent_csv_is_rejected_with_actionable_error(content):
    with pytest.raises(FileValidationError):
        validate_upload_detailed("invalid.csv", content)


def test_inconsistent_quoted_rows_are_rejected():
    with pytest.raises(FileValidationError, match="aspas e delimitadores"):
        validate_upload_detailed("invalid.csv", b'a,b\n1,"unterminated\n')


def test_latin1_small_csv_reaches_pipeline():
    content = "produto;preço\nCafé;10,50\n".encode("latin-1")
    report = _analyze("latin1.csv", content, header_mode="true")
    assert report.tables[0].rows == 1
    assert report.settings["csv_delimiter"] == ";"
