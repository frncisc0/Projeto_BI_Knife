import asyncio
import json
from io import BytesIO

from starlette.datastructures import UploadFile

from app.api.routes import analyze_batch
from app.services.analysis_service import analyze_file


def test_csv_header_names_are_preserved_when_evidence_is_clear():
    report = analyze_file("header.csv", "csv", b"id,cliente,categoria,valor\n1,Ana,A,10\n2,Bia,B,20\n", "utf-8")
    assert [column.name for column in report.tables[0].column_analyses] == ["id", "cliente", "categoria", "valor"]
    assert not any("ambígua" in warning for warning in report.warnings)


def test_csv_without_header_uses_generic_names_and_keeps_first_row():
    report = analyze_file("headerless.csv", "csv", b"1,10\n2,20\n3,30\n", "utf-8")
    assert [column.name for column in report.tables[0].column_analyses] == ["0", "1"]
    assert report.tables[0].rows == 3


def test_ambiguous_csv_is_reported_without_promoting_first_row_values():
    report = analyze_file("ambiguous.csv", "csv", b"Equipe,10\nEquipe B,20\nEquipe C,30\n", "utf-8")
    serialized = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
    assert [column.name for column in report.tables[0].column_analyses] == ["0", "1"]
    assert "Equipe" not in serialized
    assert any("ambígua" in warning for warning in report.warnings)


def test_sensitive_header_names_remain_visible_and_cell_values_are_suppressed():
    secrets = ["12345678901", "person@example.test"]
    report = analyze_file("sensitive.csv", "csv", ("CPF,email\n" + ",".join(secrets) + "\n").encode(), "utf-8")
    payload = json.dumps(report.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
    columns = report.tables[0].column_analyses
    assert [column.name for column in columns] == ["CPF", "email"]
    assert all(column.sensitive for column in columns)
    assert all(secret not in payload for secret in secrets)


def test_numeric_text_reports_physical_type_and_conservative_semantic_role():
    report = analyze_file("numeric-text.csv", "csv", b"measure\n10.5\n20.5\n30.5\n40.5\ntexto\n", "utf-8", header_mode="true")
    column = report.tables[0].column_analyses[0]
    assert column.physical_type == "string"
    assert column.inferred_type == "numérico (texto)"
    assert column.semantic_role == "measure"
    assert column.semantic_role_confidence == "low"


def test_numeric_identifiers_are_not_labeled_as_measures():
    report = analyze_file("numeric-ids.csv", "csv", b"record_id\n1001\n1002\n1003\n", "utf-8")
    column = report.tables[0].column_analyses[0]
    assert column.inferred_type == "identificador"
    assert column.semantic_role == "identifier"
    assert column.physical_type == "integer"


def test_many_nulls_are_described_as_absence_to_review_not_an_error():
    report = analyze_file("nulls.csv", "csv", b"segmento,score\nA,\nB,\nC,\nD,\n", "utf-8", header_mode="true")
    messages = " ".join(alert["message"] for alert in report.quality.alerts)
    assert "valores ausentes" in messages
    assert "avalie se a ausência é esperada" in messages
    assert "erro" not in messages.casefold()


def test_batch_detects_possible_relationship_between_two_csv_files():
    uploads = [
        UploadFile(filename="customers.csv", file=BytesIO(b"customer_id,name\n1,Ana\n2,Bia\n3,Caio\n")),
        UploadFile(filename="orders.csv", file=BytesIO(b"order_id,customer_id,total\n10,1,25\n11,1,30\n12,2,40\n")),
    ]
    result = asyncio.run(analyze_batch(uploads, "auto", "auto", "auto"))
    assert result["relationships"]
    relation = result["relationships"][0]
    assert relation["source_table"] != relation["target_table"]
    assert relation["coverage_pct"] >= 70
    assert "correspondência" in relation["reason"]
    assert all(item["analysis"]["relationships"] for item in result["results"])
    assert all(item["analysis"]["quality"]["integrity_assessed"] for item in result["results"])


def test_batch_does_not_suggest_relationships_for_unrelated_csv_files():
    uploads = [
        UploadFile(filename="regions.csv", file=BytesIO(b"region,area\nNorte,10\nSul,20\n")),
        UploadFile(filename="products.csv", file=BytesIO(b"sku,price\nA,5\nB,6\n")),
    ]
    result = asyncio.run(analyze_batch(uploads, "auto", "auto", "auto"))
    assert result["relationships"] == []


def test_similar_column_names_alone_do_not_create_a_relationship():
    uploads = [
        UploadFile(filename="customers.csv", file=BytesIO(b"customer_id\n1\n2\n3\n")),
        UploadFile(filename="orders.csv", file=BytesIO(b"customer_id\n10\n20\n30\n")),
    ]
    result = asyncio.run(analyze_batch(uploads, "auto", "auto", "auto"))
    assert result["relationships"] == []


def test_multiple_header_type_transitions_support_header_detection():
    content = b"Customer Name,Order Date,Revenue\nAna,2026-01-01,10\nBia,2026-01-02,20\nCaio,2026-01-03,30\n"
    report = analyze_file("clear-header.csv", "csv", content, "utf-8")
    assert [column.name for column in report.tables[0].column_analyses] == ["Customer Name", "Order Date", "Revenue"]
    assert not any("ambígua" in warning for warning in report.warnings)
