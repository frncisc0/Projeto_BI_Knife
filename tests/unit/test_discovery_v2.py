import json
from datetime import date
from io import BytesIO
from unittest.mock import patch

from openpyxl import Workbook
from app.models.analysis_models import RelationshipCandidate
from app.services.analysis_service import analyze_file
from app.services.html_report_service import render_html_report
from app.services.pdf_report_service import render_pdf_report
from app.services.report_service import report_payload


def _report():
    return _xlsx_report(
        ["Contratada", "Status", "Risco Total", "Risco Coberto", "Risco Descoberto", "Custo de Rescisão", "Início", "Contrato SAP", "Email"],
        [[f"Fornecedor {letter}", "Ativo" if letter != "C" else "Encerrado", index * 100, index * 70,
          index * 30, index * 25, date(2026, index, 1), f"SAP-{index:03d}", f"{letter.lower()}@example.test"]
         for index, letter in enumerate("ABCDEF", 1)],
        "synthetic-sensitive.xlsx",
    )


def _xlsx_report(headers, rows, filename="synthetic.xlsx"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return analyze_file(filename, "xlsx", buffer.getvalue())


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
    assert {"ranking", "comparison", "kpi", "trend", "coverage"} <= types
    assert "correlation" not in types
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


def test_relevance_score_orders_risk_ranking_above_generic_measures():
    items = _payload()["insights"]["items"]
    risk = next(item for item in items if item["title"] == "Risco Descoberto por Contratada")
    generic = next(item for item in items if item["type"] == "kpi" and item["title"] == "Custo de Rescisão")
    assert 0 <= risk["relevance_score"] <= 100
    assert risk["priority"] == "high"
    assert risk["relevance_score"] > generic["relevance_score"]
    kpis = _payload()["kpis"]["suggested"]
    assert [item["relevance_score"] for item in kpis] == sorted(
        (item["relevance_score"] for item in kpis), reverse=True)


def test_relevance_score_penalizes_warnings_and_low_quality():
    from app.insights.engine import _relevance_score

    semantic = _payload()["semantic_model"]
    dimension = next(field for field in semantic["dimensions"] if field["name"] == "Contratada")
    measure = next(field for field in semantic["measures"] if field["name"] == "Risco Descoberto")
    from app.models.discovery_models import SemanticField
    dimension_field, measure_field = SemanticField.model_validate(dimension), SemanticField.model_validate(measure)
    baseline = _relevance_score("ranking", [dimension_field], [measure_field], [], "high", [], 100)
    penalized = _relevance_score("ranking", [dimension_field], [measure_field], [], "high", ["warning"], 50)
    assert penalized < baseline


def test_business_questions_use_natural_templates_for_common_dimensions():
    from app.insights.engine import _business_question

    assert _business_question("Contratada", "Risco Descoberto")[2] == "Quais contratadas apresentam maior risco descoberto?"
    assert _business_question("Empresa Enel", "Risco Total")[2] == "Quais empresas Enel concentram maior risco total?"
    assert _business_question("Diretoria", "Custo da Folha")[2] == "Quais diretorias concentram maior custo da folha?"


def test_date_name_alone_does_not_create_a_trend():
    report = _xlsx_report(["Data", "Custo Total"],
                          [[date(2026, 1, index), index * 100] for index in range(1, 7)], "one-month.xlsx")
    semantic = report_payload(report)["semantic_model"]
    assert semantic["dates"][0]["temporal_support"] is False
    assert not any(item["type"] == "trend" for item in report_payload(report)["insights"]["items"])


def test_outlier_suggestion_requires_anomaly_evidence_in_analysis_result():
    report = _xlsx_report(["Risco Total"], [[value] for value in [1, 2, 3, 4, 5, 6, 7, 1000]], "outlier.xlsx")
    payload = report_payload(report)
    outliers = [item for item in payload["insights"]["items"] if item["type"] == "outlier"]
    assert outliers
    assert "AnalysisResult registrou" in " ".join(outliers[0]["evidence"])
    regular = _xlsx_report(["Risco Total"], [[value] for value in range(1, 9)], "no-outlier.xlsx")
    assert not any(item["type"] == "outlier" for item in report_payload(regular)["insights"]["items"])


def test_current_interface_uses_v3_brand_and_exposes_human_centered_views():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    index = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    assert "BI SWISS KNIFE · V3.0" in index
    assert "Resumo · Descobertas · Análises possíveis · Dashboard recomendado" in index
    assert "V0.3.0" not in index and "FERRAMENTA DE DIAGNÓSTICO DE DADOS" not in index
    for view in ("Visão Geral", "Descobertas", "O que posso analisar?", "Dashboard recomendado", "Análise técnica", "Segurança"):
        assert view in script


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


def test_v22_scoring_rewards_relevant_measures_and_dimensions_and_penalizes_weaknesses():
    from app.insights.engine import _relevance_score
    from app.models.discovery_models import SemanticField

    def field(name, role, distinct=8, completeness=100, confidence="high"):
        return SemanticField(table="Aba", name=name, role=role, confidence=confidence, reason="teste",
                             distinct_count=distinct, completeness_pct=completeness)

    strong_dim, weak_dim = field("Diretoria", "dimension"), field("Coluna7", "dimension")
    strong_measure, aux_measure = field("Risco Descoberto", "measure"), field("Código auxiliar", "measure")
    base = _relevance_score("ranking", [strong_dim], [strong_measure], [], "high", [], 100)
    assert base > _relevance_score("ranking", [strong_dim], [aux_measure], [], "high", [], 100)
    assert base > _relevance_score("ranking", [weak_dim], [strong_measure], [], "high", [], 100)
    assert base > _relevance_score("ranking", [strong_dim], [strong_measure], [], "high", ["warning"], 45)
    assert base > _relevance_score("ranking", [strong_dim], [strong_measure], [], "medium", [], 100)
    assert base > _relevance_score("ranking", [field("Diretoria", "dimension", distinct=900)],
                                   [strong_measure], [], "high", [], 100)
    assert _relevance_score("ranking", [strong_dim], [field("FGTS (Qtd)", "measure", confidence="high")],
                            [], "high", [], 100) < base


def test_v22_semantic_deduplication_collapses_cross_table_equivalents_only():
    from app.insights.engine import _deduplicate
    from app.models.discovery_models import Insight

    def insight(title, dim, measure="Risco Descoberto", table="Aba 1", score=80):
        return Insight(id=title, type="ranking", title=title, business_question="Pergunta", visual="barras",
                       confidence="high", priority="high", relevance_score=score,
                       dimensions=[{"table": table, "column": dim}], measures=[{"table": table, "column": measure}],
                       reason="evidência", evidence=["campos analisados"])

    items, removed = _deduplicate([
        insight("Risco por Contratada", "Contratada", table="Aba 1", score=75),
        insight("Risco por Contratada (outra aba)", "Contratada", table="Aba 2", score=82),
        insight("Risco por Diretoria", "Diretoria"),
        insight("Custo por Contratada", "Contratada", measure="Custo Total"),
    ])
    assert removed == 1
    assert len(items) == 3
    winner = next(item for item in items if "Contratada" in item.title and "outra" in item.title)
    assert winner.relevance_score == 80
    assert "penalidade de redundância" in winner.reason


def test_v22_priority_requires_confidence_for_high_and_downgrades_weak_evidence():
    from app.insights.engine import _priority
    from app.models.discovery_models import SemanticField

    strong_dim = SemanticField(table="A", name="Contratada", role="dimension", confidence="high", reason="x")
    strong_measure = SemanticField(table="A", name="Risco Total", role="measure", confidence="high", reason="x")
    weak_dim = SemanticField(table="A", name="Coluna7", role="dimension", confidence="high", reason="x")
    assert _priority(90, "high", (), [strong_dim], [strong_measure]) == "high"
    assert _priority(90, "medium", (), [strong_dim], [strong_measure]) == "medium"
    assert _priority(90, "high", (), [weak_dim], [strong_measure]) != "high"
    assert _priority(30, "high") == "low"


def test_v22_blueprint_uses_only_prioritized_final_insights_and_limits_executive_page():
    from app.blueprint.builder import build_dashboard_blueprint
    from app.models.discovery_models import Insight, InsightsBlock, KpisBlock, SemanticModel

    items = [Insight(id=f"item-{index}", type="ranking", title=f"Insight {index}",
                     business_question="Pergunta", visual="barras", confidence="high", priority="high",
                     relevance_score=90-index, reason="baseado em evidências", evidence=["metadados"],
                     dimensions=[{"table": "A", "column": "Contratada"}],
                     measures=[{"table": "A", "column": "Risco Total"}]) for index in range(8)]
    items.append(Insight(id="low", type="ranking", title="Ignorado", business_question="Pergunta", visual="barras",
                         confidence="low", priority="low", relevance_score=99, reason="evidência fraca", evidence=["x"]))
    blueprint = build_dashboard_blueprint(SemanticModel(), InsightsBlock(generated=True, items=items), KpisBlock())
    executive = next(page for page in blueprint.recommended_pages if page["name"] == "Visão Geral")
    assert len(executive["visuals"]) <= 5
    assert all(item["priority"] in {"high", "medium"} for item in executive["visuals"])
    assert "low" not in blueprint.insights
