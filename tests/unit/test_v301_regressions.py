"""Regression tests for v3.0.1 — each test reproduces a defect found in the
technical audit (docs/01_DIAGNOSTICO_TECNICO.md, section 4) and must fail on
v3.0.0.
"""
import asyncio

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.analyzers.schema_analyzer import infer_type
from app.analyzers.statistics_analyzer import numeric_values
from app.core.config import get_settings
from app.services.analysis_service import analyze_file


def _columns(report):
    return {column.name: column for column in report.tables[0].column_analyses}


# --- D1: ISO dates must never have day and month swapped -------------------

def test_d1_iso_dates_keep_month_and_day():
    content = b"id,data_admissao\n1,2024-01-10\n2,2023-05-02\n3,2022-11-20\n4,2021-03-15\n"
    column = _columns(analyze_file("rh.csv", "csv", content, "utf-8"))["data_admissao"]
    assert column.statistics.min == "2021-03-15T00:00:00"
    assert column.statistics.max == "2024-01-10T00:00:00"
    assert column.statistics.by_month == {"2021-03": 1, "2022-11": 1, "2023-05": 1, "2024-01": 1}
    assert column.invalid_dates == 0


def test_d1_brazilian_dates_remain_day_first():
    content = b"id,data\n1,10/01/2024\n2,02/05/2023\n3,20/11/2022\n"
    column = _columns(analyze_file("br.csv", "csv", content, "utf-8"))["data"]
    assert column.statistics.max == "2024-01-10T00:00:00"
    assert column.statistics.min == "2022-11-20T00:00:00"


# --- D2: SECURITY.md promises suppression for name, salary and bank data --

@pytest.mark.parametrize("column_name", [
    "nome", "nome_cliente", "nome_completo", "salario", "salário", "remuneracao",
    "conta_bancaria", "agencia", "chave_pix", "data_nascimento",
])
def test_d2_sensitive_columns_promised_by_security_md_are_suppressed(column_name):
    rows = "\n".join(f"{i},{1000 + i * 37}" if column_name != "data_nascimento" else f"{i},1990-01-{i:02d}"
                     for i in range(1, 11))
    content = f"id,{column_name}\n{rows}\n".encode()
    column = _columns(analyze_file("rh.csv", "csv", content, "utf-8"))[column_name]
    assert column.sensitive is True
    assert column.statistics.min is None
    assert column.statistics.max is None
    assert column.statistics.mean is None


@pytest.mark.parametrize("column_name", ["nome_produto", "nome_categoria", "valor", "conta_contabil"])
def test_d2_non_personal_columns_are_not_flagged(column_name):
    content = f"id,{column_name}\n1,10\n2,20\n3,30\n".encode()
    assert _columns(analyze_file("x.csv", "csv", content, "utf-8"))[column_name].sensitive is False


# --- D3: alphanumeric codes are not numbers ---------------------------------

@pytest.mark.parametrize("values", [["P12", "P900", "P45"], ["AB-1001", "AB-1002", "XY-77"], ["SKU9", "SKU10", "SKU11"]])
def test_d3_alphanumeric_codes_are_not_numeric(values):
    assert infer_type(pd.Series(values * 5), "produto") == "categórico"
    assert numeric_values(pd.Series(values)).isna().all()


def test_d3_currency_and_percent_symbols_still_parse():
    assert numeric_values(pd.Series(["R$ 80", "US$ 10", "15%", "-5"])).tolist() == [80.0, 10.0, 15.0, -5.0]


# --- D4: Brazilian thousands separator ------------------------------------

def test_d4_brazilian_thousands_separator():
    assert numeric_values(pd.Series(["R$ 1.234", "R$ 80", "R$ 2.500,50"])).tolist() == [1234.0, 80.0, 2500.5]
    assert numeric_values(pd.Series(["1.234.567", "12"])).tolist() == [1234567.0, 12.0]
    assert numeric_values(pd.Series(["1.234,56"])).tolist() == [1234.56]


def test_d4_plain_decimal_point_values_are_preserved():
    assert numeric_values(pd.Series(["1.5", "2.25", "10"])).tolist() == [1.5, 2.25, 10.0]


# --- D5: CSV sampling must be uniform and correctly labelled --------------

def test_d5_csv_sample_covers_whole_file_and_is_labelled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_cells_to_analyze", 400)  # 2 columns -> 200 rows
    lines = ["id,mes"] + [f"{i},{1 + (i - 1) * 12 // 2000}" for i in range(1, 2001)]  # file sorted by month
    report = analyze_file("sorted.csv", "csv", ("\n".join(lines) + "\n").encode(), "utf-8")
    table = report.tables[0]
    assert table.sampled is True
    assert table.rows == 2000
    assert table.rows_analyzed == 200
    assert table.sampling_method == "uniform_random"
    month = _columns(report)["mes"]
    assert month.statistics.max >= 11  # a head-of-file sample would only see month 1-2


def test_d5_unsampled_csv_reports_no_sampling():
    table = analyze_file("small.csv", "csv", b"id,v\n1,2\n2,3\n", "utf-8").tables[0]
    assert table.sampled is False
    assert table.sampling_method == "none"


# --- D6: heavy analysis must not run on the event loop --------------------

def test_d6_single_analysis_runs_outside_event_loop(monkeypatch):
    from app import main
    from app.api import routes

    seen = {}
    original = routes.analyze_file

    def spy(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return original(*args, **kwargs)

    monkeypatch.setattr(routes, "analyze_file", spy)
    with TestClient(main.app) as client:
        response = client.post("/api/analyze", files={"upload": ("a.csv", b"id,v\n1,2\n2,3\n", "text/csv")})
        assert response.status_code == 200
        response = client.post("/api/analyze-batch", files=[("uploads", ("b.csv", b"id,v\n1,2\n", "text/csv"))])
        assert response.status_code == 200
    assert seen["on_loop"] is False


# --- Hardening: only local Host headers are accepted ----------------------

def test_untrusted_host_header_is_rejected():
    from app import main
    with TestClient(main.app) as client:
        assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400
        assert client.get("/api/health", headers={"host": "127.0.0.1:8000"}).status_code == 200
        assert client.get("/api/health", headers={"host": "localhost:8000"}).status_code == 200


# --- v3.0.2: values parsed as dates outside pandas' range must not crash -----

def test_v302_out_of_range_date_candidates_do_not_crash_analysis():
    from app.analyzers.date_parsing import parse_dates

    parsed = parse_dates(pd.Series(["00123", "2024-01-10", "0099-01-01", "10/01/2024"]))
    assert parsed.isna().tolist() == [True, False, True, False]
    assert str(parsed.dtype) == "datetime64[ns]"
    content = b"sku,descricao,qtd\nP12,Caneta,3\nAB-1001,Caderno,10\n00123,Borracha,7\nP900,Lapis,1\n"
    report = analyze_file("codes.csv", "csv", content, "utf-8", header_mode="true")
    assert _columns(report)["sku"].inferred_type == "categórico"


# --- v3.0.3: progress reporting on large CSV must not abort the analysis -------

def test_v303_csv_larger_than_one_chunk_with_progress_callback():
    """The UI always passes a progress callback; CSV files above 50,000 rows
    (more than one read chunk) failed with 'OSError: telling position disabled'."""
    from app.analyzers.file_analyzer import read_tables

    content = ("id,valor\n" + "".join(f"{i},{i % 97}\n" for i in range(60_000))).encode()
    events = []
    frames = read_tables(content, "csv", "utf-8", on_progress=events.append)
    assert frames["Dados"].attrs["total_rows"] == 60_000
    fractions = [event["stage_progress"] for event in events if event.get("stage") == "csv_reading"]
    assert fractions and fractions == sorted(fractions)  # monotonic
    assert 0 < fractions[0] <= 1 and fractions[-1] == pytest.approx(1.0, abs=0.01)
