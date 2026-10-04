import json
from unittest.mock import patch

from app.models.analysis_models import RelationshipCandidate
from app.services.analysis_service import analyze_file
from app.services.html_report_service import render_html_report
from app.services.pdf_report_service import render_pdf_report
from app.services.report_service import report_payload


def _report():
    content = (
        "Contratada,Status,Risco Total,Risco Coberto,Risco Descoberto,Custo de Rescisão,Início,Contrato SAP,Email\n"
        "Fornecedor A,Ativo,100,70,30,25,2026-01-01,SAP-001,a@example.test\n"
        "Fornecedor B,Ativo,200,140,60,50,2026-01-02,SAP-002,b@example.test\n"
        "Fornecedor C,Encerrado,300,210,90,75,2026-01-03,SAP-003,c@example.test\n"
        "Fornecedor D,Ativo,400,280,120,100,2026-01-04,SAP-004,d@example.test\n"
        "Fornecedor E,Ativo,500,350,150,125,2026-01-05,SAP-005,e@example.test\n"
        "Fornecedor F,Encerrado,600,420,180,150,2026-01-06,SAP-006,f@example.test\n"
    ).encode()
    return analyze_file("synthetic-sensitive.csv", "csv", content, "utf-8", header_mode="true")


def _payload():
    return report_payload(_report())


def test_semantic_layer_classifies_dimensions_measures_dates_and_identifiers():
    payload = _payload()
    semantic = payload["semantic_model"]
    assert "Contratada" in {field["name"] for field in semantic["dimensions"]}
    assert {"Risco Total", "Risco Coberto", "Custo de Rescisão"} <= {field["name"] for field in semantic["measures"]}
    assert "Início" in {field["name"] for field in semantic["dates"]}
    assert "Contrato SAP" in {field["name"] for field in semantic["identifiers"]}
    assert "Email" not in {field["name"] for field in [*semantic["dimensions"], *semantic["measures"]]}


def test_unique_measure_remains_measure_and_not_a_key_candidate():
    report = _report()
    table = report.tables[0]
    risk = next(column for column in table.column_analyses if column.name == "Risco Total")
    assert risk.semantic_role == "measure"
    assert risk.key_candidate is False
    assert risk.key_assessment == "high_uniqueness_measure"


def test_discovery_generates_ranking_comparison_kpi_trend_and_coverage_candidate():
    payload = _payload()
    items = payload["insights"]["items"]
    types = {item["type"] for item in items}
    assert {"ranking", "distribution", "kpi", "trend", "coverage"} <= types
    assert any(item["title"] == "% Cobertura" for item in items)
    candidate = payload["kpis"]["calculation_candidates"][0]
    assert candidate["numerator"] == "Risco Coberto"
    assert candidate["denominator"] == "Risco Total"
    assert candidate["formula_type"] == "ratio"


def test_comparison_is_suggested_for_a_moderate_cardinality_dimension():
    content = "Status,Custo Total\n" + "".join(f"Status {index},{index * 100}\n" for index in range(1, 10))
    report = analyze_file("comparison.csv", "csv", content.encode(), "utf-8", header_mode="true")
    items = report_payload(report)["insights"]["items"]
    assert any(item["type"] == "comparison" for item in items)


def test_insights_have_confidence_priority_evidence_and_explanation():
    items = _payload()["insights"]["items"]
    assert items
    for item in items:
        assert item["confidence"] in {"high", "medium", "low"}
        assert item["priority"] in {"high", "medium", "low"}
        assert item["evidence"]
        assert item["reason"]
        assert item["business_question"]


def test_no_fields_means_no_fabricated_insights():
    report = analyze_file("empty-semantic.csv", "csv", b"left,right\na,b\nc,d\n", "utf-8", header_mode="true")
    payload = report_payload(report)
    assert payload["insights"]["generated"] is True
    assert payload["insights"]["items"] == []
    assert payload["kpis"]["suggested"] == []
    assert payload["dashboard_blueprint"]["recommended_pages"] == []


def test_measure_to_measure_relationship_is_excluded_from_semantic_model():
    report = _report()
    report.relationships.append(RelationshipCandidate(
        source_table=report.tables[0].name, source_column="Risco Total",
        target_table=report.tables[0].name, target_column="Risco Descoberto",
        coverage_pct=100, matched_values=6, unmatched_values=0, cardinality="1:1",
        confidence="high", reason="Relação sintética usada para verificar o filtro semântico.",
    ))
    payload = report_payload(report)
    assert payload["semantic_model"]["relationships"] == []


def test_dashboard_blueprint_uses_evidenced_fields_and_suggestions():
    blueprint = _payload()["dashboard_blueprint"]
    assert blueprint["title"]
    assert blueprint["recommended_pages"]
    assert blueprint["dimensions"]
    assert blueprint["measures"]
    assert all(page["visuals"] for page in blueprint["recommended_pages"])


def test_json_html_and_pdf_include_v2_discovery_without_raw_sensitive_values():
    report = _payload()
    encoded = json.dumps(report, ensure_ascii=False)
    batch = {"file_count": 1, "results": [{"filename": report["filename"], "analysis": report, "error": None}]}
    html = render_html_report(batch)
    pdf = render_pdf_report(batch)
    for raw_value in ("a@example.test", "b@example.test", "Fornecedor A"):
        assert raw_value not in encoded
        assert raw_value not in html
        assert raw_value.encode() not in pdf
    assert "dashboard_blueprint" in encoded
    assert "O que posso analisar?" in html
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 1000


def test_discovery_does_not_call_network_services():
    with patch("urllib.request.urlopen", side_effect=AssertionError("network call")) as urlopen:
        _payload()
        urlopen.assert_not_called()
