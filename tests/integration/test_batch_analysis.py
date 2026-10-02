import asyncio
from io import BytesIO

from starlette.datastructures import UploadFile

from app.api.routes import analyze_batch


def test_batch_analyzes_multiple_files_and_reports_bad_files_individually():
    uploads = [
        UploadFile(filename="vendas/sul.csv", file=BytesIO(b"id,valor\n1,10\n2,20\n")),
        UploadFile(filename="clientes.csv", file=BytesIO(b"id,nome\n1,Ana\n")),
        UploadFile(filename="macro.xlsm", file=BytesIO(b"conteudo nao permitido")),
    ]

    result = asyncio.run(analyze_batch(uploads, "auto", "auto", "auto"))

    assert result["file_count"] == 3
    assert result["results"][0]["analysis"]["filename"] == "vendas/sul.csv"
    assert result["results"][0]["analysis"]["tables"][0]["rows"] == 2
    assert result["results"][1]["analysis"]["filename"] == "clientes.csv"
    assert result["results"][2]["analysis"] is None
    assert ".xlsx ou .csv" in result["results"][2]["error"]
