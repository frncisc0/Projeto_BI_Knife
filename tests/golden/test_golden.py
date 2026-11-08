"""Golden dataset: hand-verified expectations (test oracle).

Every expected value below was calculated by hand from the rows in
``build_inputs.py``; none was copied from the program output. When a test
here fails, either the program is wrong or the expectation is wrong; decide
which by recomputing by hand, never by pasting the new output.

Expectations about behaviour that does not exist yet are marked
``xfail(strict=True)`` with the roadmap version that should deliver it, so
the test starts failing (and must be un-marked) when the feature lands.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.security.file_validation import validate_upload_detailed
from app.services.analysis_service import analyze_file

INPUTS = Path(__file__).parent / "inputs"
NUMERIC = {"inteiro", "decimal", "numérico (texto)", "moeda", "percentual"}
DATE = {"data", "data/hora (texto)"}


def analyze(name: str, header_mode: str = "auto"):
    """Analyze an input. header_mode="true" reproduces the user's answer in the
    UI dialog that appears when the header is ambiguous."""
    content = (INPUTS / name).read_bytes()
    safe_name, file_type, encoding, security = validate_upload_detailed(name, content)
    return analyze_file(safe_name, file_type, content, encoding, header_mode=header_mode,
                        security_metadata=security)


def columns(report, table_index: int = 0):
    return {column.name: column for column in report.tables[table_index].column_analyses}


# --- CSV in the default Brazilian Excel format -------------------------------

def test_br_excel_csv_cp1252_semicolon_decimal_comma():
    report = analyze("br_excel.csv")
    table = report.tables[0]
    assert report.settings["csv_encoding"] == "cp1252"
    assert report.settings["csv_delimiter"] == ";"
    assert (table.rows, table.columns, table.duplicate_rows) == (5, 5, 0)
    cols = columns(report)
    assert list(cols) == ["id", "categoria", "cidade", "valor", "data_venda"]
    assert cols["cidade"].distinct_count == 3  # São Paulo, Goiânia, Brasília (accents decoded)
    assert cols["categoria"].distinct_count == 2
    valor = cols["valor"]
    assert valor.inferred_type in NUMERIC
    assert valor.null_count == 1
    assert (valor.statistics.min, valor.statistics.max) == (80.0, 2500.0)
    assert valor.statistics.mean == pytest.approx(978.6)  # (1234.50 + 80 + 2500 + 99.90) / 4
    data = cols["data_venda"]
    assert data.inferred_type in DATE
    assert (data.statistics.min, data.statistics.max) == ("2024-01-10T00:00:00", "2024-04-01T00:00:00")
    assert data.statistics.by_month == {"2024-01": 1, "2024-02": 1, "2024-03": 2, "2024-04": 1}


def test_international_csv_utf8_comma_decimal_point_iso_dates():
    report = analyze("intl.csv")
    cols = columns(report)
    assert report.tables[0].rows == 3
    assert cols["order_id"].inferred_type not in NUMERIC  # "A-1" is a code
    assert cols["product"].distinct_count == 2
    amount = cols["amount"]
    assert amount.inferred_type in NUMERIC
    assert (amount.statistics.min, amount.statistics.max) == (7.0, 1000.25)
    assert amount.statistics.mean == pytest.approx(339.25)  # (10.50 + 1000.25 + 7.00) / 3
    order_date = cols["order_date"]
    assert (order_date.statistics.min, order_date.statistics.max) == ("2024-01-10T00:00:00", "2024-12-31T00:00:00")


def test_iso_dates_with_day_up_to_12_keep_month():
    data = columns(analyze("iso_low_days.csv"))["data"]
    assert data.inferred_type in DATE
    assert (data.statistics.min, data.statistics.max) == ("2024-01-02T00:00:00", "2024-07-08T00:00:00")
    assert data.statistics.by_month == {"2024-01": 1, "2024-03": 1, "2024-05": 1, "2024-07": 1}
    assert data.invalid_dates == 0


def test_brazilian_currency_with_thousands_separator():
    preco = columns(analyze("br_numbers.csv"))["preco"]
    assert preco.inferred_type in NUMERIC
    assert preco.inconsistent_values == 0
    assert (preco.statistics.min, preco.statistics.max) == (80.0, 10000.0)
    assert preco.statistics.mean == pytest.approx(3453.625)  # (1234 + 80 + 2500.50 + 10000) / 4


def test_alphanumeric_codes_are_not_numbers():
    cols = columns(analyze("codes.csv", header_mode="true"))
    assert cols["sku"].inferred_type not in NUMERIC
    assert cols["sku"].distinct_count == 4
    assert cols["qtd"].inferred_type in NUMERIC
    assert cols["qtd"].statistics.mean == pytest.approx(5.25)  # (3 + 10 + 7 + 1) / 4


# --- Privacy ----------------------------------------------------------------

def test_hr_file_sensitive_columns_and_no_cell_values_in_report():
    report = analyze("rh.csv")
    cols = columns(report)
    assert {name for name, column in cols.items() if column.sensitive} == {"nome", "salario", "conta_bancaria", "cpf"}
    for name in ("nome", "salario", "conta_bancaria", "cpf"):
        stats = cols[name].statistics
        assert (stats.min, stats.max, stats.mean) == (None, None, None), name
        assert cols[name].top_values == [], name
    assert cols["cargo"].distinct_count == 3
    assert cols["data_admissao"].statistics.max == "2024-01-10T00:00:00"
    payload = report.model_dump(mode="json")
    payload.pop("file_sha256")  # a hex digest may contain any digit sequence
    serialized = json.dumps(payload, ensure_ascii=False)
    for secret in ("Ana Silva", "Bruno Lima", "Caio Souza", "Dani Rocha", "111.222.333-44", "12345-6",
                   "5000.5", "7200", "3100", "9100", "Analista", "Gerente", "Diretor"):
        assert secret not in serialized, secret


# --- Quality ----------------------------------------------------------------

def test_duplicates_and_nulls_are_counted():
    report = analyze("duplicates_nulls.csv")
    table = report.tables[0]
    cols = columns(report)
    assert (table.rows, table.duplicate_rows) == (5, 1)
    assert cols["categoria"].null_count == 1
    assert cols["valor"].null_count == 1
    assert cols["valor"].statistics.mean == pytest.approx(20.0)  # (10 + 20 + 20 + 30) / 4
    assert cols["id"].key_candidate is False  # "2" repeats


@pytest.mark.xfail(strict=True, reason="CMP-03 (nulos disfarçados) previsto para v3.2.0")
def test_disguised_nulls_are_counted_as_missing():
    assert columns(analyze("disguised_nulls.csv"))["status"].null_count == 2  # "n/d" and "-"


# --- Excel workbook -----------------------------------------------------------

def test_workbook_title_rows_multiple_sheets_and_relationship():
    report = analyze("workbook.xlsx")
    tables = {table.name: table for table in report.tables}
    assert list(tables) == ["Vendas", "Clientes", "Vazia"]
    vendas = tables["Vendas"]
    assert vendas.header_row_used == 4
    assert vendas.rows == 3
    assert [column.name for column in vendas.column_analyses] == ["pedido_id", "cliente_id", "valor", "data_pedido"]
    valor = {column.name: column for column in vendas.column_analyses}["valor"]
    assert (valor.statistics.min, valor.statistics.max) == (20.0, 75.5)
    assert valor.statistics.mean == pytest.approx(48.5)  # (50 + 75.5 + 20) / 3
    data = {column.name: column for column in vendas.column_analyses}["data_pedido"]
    assert (data.statistics.min, data.statistics.max) == ("2024-01-10T00:00:00", "2024-03-08T00:00:00")
    assert tables["Clientes"].rows == 2
    assert tables["Vazia"].status == "completed_empty"
    assert report.security.active_content_detected is False
    relations = {(r.source_table, r.source_column, r.target_table, r.target_column): r for r in report.relationships}
    assert set(relations) == {("Clientes", "cliente_id", "Vendas", "cliente_id")}
    relation = relations[("Clientes", "cliente_id", "Vendas", "cliente_id")]
    assert (relation.coverage_pct, relation.cardinality) == (100.0, "1:N")


# --- Star schema across files (batch) -------------------------------------------

def test_star_schema_relationships_across_csv_files():
    from app import main

    files = [("uploads", (name, (INPUTS / name).read_bytes(), "text/csv"))
             for name in ("fato_vendas.csv", "dim_cliente.csv", "dim_produto.csv")]
    with TestClient(main.app) as client:
        # dim_* headers are ambiguous for the heuristic; the UI asks the user (answer: header).
        response = client.post("/api/analyze-batch", files=files, data={"header_mode": "true"})
    assert response.status_code == 200
    relations = {
        (r["source_table"].split("::")[0], r["source_column"], r["target_table"].split("::")[0], r["target_column"]): r
        for r in response.json()["relationships"]
    }
    assert set(relations) == {
        ("dim_cliente.csv", "cliente_id", "fato_vendas.csv", "cliente_id"),
        ("dim_produto.csv", "produto_id", "fato_vendas.csv", "produto_id"),
    }
    cliente = relations[("dim_cliente.csv", "cliente_id", "fato_vendas.csv", "cliente_id")]
    # 10 sales, one with cliente_id 99 that does not exist in dim_cliente -> 9/10
    assert (cliente["coverage_pct"], cliente["matched_values"], cliente["unmatched_values"]) == (90.0, 9, 1)
    assert cliente["cardinality"] == "1:N"
    produto = relations[("dim_produto.csv", "produto_id", "fato_vendas.csv", "produto_id")]
    assert (produto["coverage_pct"], produto["cardinality"], produto["confidence"]) == (100.0, "1:N", "high")


# --- Header detection ---------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="Cabeçalho simples ainda é considerado ambíguo; melhoria prevista (BK-025, v3.3.0)")
@pytest.mark.parametrize("name, expected", [
    ("codes.csv", ["sku", "descricao", "qtd"]),
    ("dim_cliente.csv", ["cliente_id", "segmento"]),
])
def test_simple_headers_are_detected_without_asking(name, expected):
    assert list(columns(analyze(name))) == expected
