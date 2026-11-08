"""Markdown export for AI assistants: structure only, never data values."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.services.markdown_report_service import render_markdown_report

GOLDEN = Path(__file__).parents[1] / "golden" / "inputs"


def _batch(client: TestClient, *names: str, extra: list[tuple[str, bytes]] = ()) -> dict:
    files = [("uploads", (name, (GOLDEN / name).read_bytes(), "text/csv")) for name in names]
    files += [("uploads", (name, content, "text/csv")) for name, content in extra]
    response = client.post("/api/analyze-batch", files=files, data={"header_mode": "true"})
    assert response.status_code == 200
    return response.json()


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def test_markdown_contains_structure_and_no_cell_values(client):
    sales = ("pedido_id;regiao;produto;valor;data\n"
             "1;CANARIO_REGIAO;CANARIO_PRODUTO;1.234,56;10/01/2024\n"
             "2;Sudoeste;Teclado;98,70;11/02/2024\n").encode("cp1252")
    batch = _batch(client, "rh.csv", "intl.csv", extra=[("vendas.csv", sales)])
    markdown = render_markdown_report(batch)

    # Structure is present
    for expected in ("`nome`", "`salario`", "`order_date`", "`amount`", "`regiao`", "Instruções para a IA"):
        assert expected in markdown, expected

    # No cell values, category labels or examples
    for secret in ("Ana Silva", "Bruno Lima", "111.222.333-44", "12345-6", "Analista", "Gerente",
                   "Widget", "Gadget", "A-1", "CANARIO_REGIAO", "CANARIO_PRODUTO", "Sudoeste", "Teclado"):
        assert secret not in markdown, secret
    # No value statistics: amounts, extremes, means or date ranges
    for statistic in ("1000.25", "1000,25", "339.25", "339,25", "1.234,56", "1234.56", "98,70",
                      "5000.5", "9100", "2024-12-31", "2024-01-10", "10/01/2024", "2021-03-15"):
        assert statistic not in markdown, statistic


def test_sensitive_columns_are_flagged(client):
    markdown = render_markdown_report(_batch(client, "rh.csv"))
    for column in ("nome", "salario", "conta_bancaria", "cpf"):
        line = next(line for line in markdown.splitlines() if line.startswith(f"| `{column}`"))
        assert "🔒 sensível" in line, column
    assert "🔒" not in next(line for line in markdown.splitlines() if line.startswith("| `cargo`"))


def test_star_schema_relationships_listed_once_with_coverage(client):
    markdown = render_markdown_report(_batch(client, "fato_vendas.csv", "dim_cliente.csv", "dim_produto.csv"))
    relation_rows = [line for line in markdown.splitlines() if line.startswith("| `dim_")]
    assert relation_rows == [
        "| `dim_cliente.csv`.`cliente_id` | `fato_vendas.csv`.`cliente_id` | 1:N | 90,0% | média |",
        "| `dim_produto.csv`.`produto_id` | `fato_vendas.csv`.`produto_id` | 1:N | 100,0% | alta |",
    ]
    assert "10,0% dos valores de `fato_vendas.csv`.`cliente_id` não existem em `dim_cliente.csv`" in markdown


def test_markdown_is_deterministic_and_compact(client):
    batch = _batch(client, "fato_vendas.csv", "dim_cliente.csv", "dim_produto.csv")
    first, second = render_markdown_report(batch), render_markdown_report(batch)
    assert first == second
    assert len(first) < 40_000  # roughly 10k tokens: fits any assistant's context comfortably


def test_column_names_cannot_break_the_markdown_table(client):
    content = b"id,coluna|com pipe\n1,a\n2,b\n"
    markdown = render_markdown_report(_batch(client, extra=[("estranho.csv", content)]))
    assert "`coluna\\|com pipe`" in markdown


def test_empty_batch_still_renders():
    markdown = render_markdown_report({"results": [{"filename": "x.csv", "analysis": None, "error": "falhou"}]})
    assert "Nenhum arquivo pôde ser analisado" in markdown


def test_markdown_endpoint(client):
    batch = _batch(client, "intl.csv")
    response = client.post("/api/report-markdown", json=batch)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert ".md" in response.headers["content-disposition"]
    assert response.text.startswith("# Dossiê de dados")
    assert client.post("/api/report-markdown", json={"not": "a batch"}).status_code == 400

