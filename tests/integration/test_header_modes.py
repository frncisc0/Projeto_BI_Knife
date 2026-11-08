"""Per-file header choices keep cross-file relationships (ambiguous-header dialog)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main

GOLDEN = Path(__file__).parents[1] / "golden" / "inputs"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def test_per_file_header_modes_keep_cross_file_relationships(client):
    """The UI re-analyses the whole batch with one header choice per file after the
    ambiguous-header dialog; relationships between files must survive."""
    names = ("fato_vendas.csv", "dim_cliente.csv", "dim_produto.csv")
    files = [("uploads", (name, (GOLDEN / name).read_bytes(), "text/csv")) for name in names]
    response = client.post("/api/analyze-batch", files=files,
                           data={"header_modes": '["auto", "true", "true"]'})
    assert response.status_code == 200
    assert len(response.json()["relationships"]) == 2


@pytest.mark.parametrize("modes", ['["true"]', '["sim", "true", "true"]', "não é json"])
def test_invalid_header_modes_are_rejected(client, modes):
    names = ("fato_vendas.csv", "dim_cliente.csv", "dim_produto.csv")
    files = [("uploads", (name, (GOLDEN / name).read_bytes(), "text/csv")) for name in names]
    assert client.post("/api/analyze-batch", files=files, data={"header_modes": modes}).status_code == 400
