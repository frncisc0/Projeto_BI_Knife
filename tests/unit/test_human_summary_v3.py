from __future__ import annotations

from app.blueprint.builder import build_dashboard_blueprint
from app.models.discovery_models import Insight, InsightsBlock, KpisBlock, SemanticField, SemanticModel
from app.services.analysis_service import analyze_file
from app.services.html_report_service import render_html_report
from app.services.pdf_report_service import render_pdf_report
from app.services.report_service import report_payload


def _analysis():
    text = "Contratada,Diretoria,Status,Risco Total,Risco Descoberto,Data do Processo\n"
    text += "".join(
        f"Fornecedor {i},Diretoria {i % 3},{'Ativo' if i % 2 else 'Encerrado'},{i * 1000},{i * 250},2026-{i:02d}-01\n"
        for i in range(1, 13)
    )
    return analyze_file("amostra-v3.csv", "csv", text.encode(), "utf-8", header_mode="true")


def _payload():
    return report_payload(_analysis())


def _insight(identifier, dim="Contratada", measure="Risco Total", *, score=90, priority="high", table="Aba"):
    return Insight(
        id=identifier, type="ranking", title=f"{measure} por {dim}",
        business_question=f"Quais {dim} concentram maior {measure}?", visual="barras horizontais",
        confidence="high", priority=priority, relevance_score=score, reason="Campos identificados como dimensão e medida.",
        evidence=["Papel semântico identificado"],
        dimensions=[{"table": table, "column": dim}], measures=[{"table": table, "column": measure}],
    )


def test_v3_summary_explains_the_existing_analysis_and_quality():
    summary = _payload()["human_summary"]
    assert "Analisamos 1 aba" in summary["executive_summary"]
    assert "colunas" in summary["executive_summary"]
    assert summary["data_quality_summary"]
    assert {"Completude", "Consistência", "Validade", "Unicidade"} <= {
        item["name"] for item in summary["quality_components"]
    }


def test_v3_key_findings_are_limited_and_reference_real_final_insights():
    payload = _payload()
    summary = payload["human_summary"]
    final_ids = {item["id"] for item in payload["insights"]["items"]}
    findings = summary["key_findings"]
    assert len(findings) <= 6
    assert all(item["insight_id"] in final_ids for item in findings)
    assert all(item["description"] and item["why"] and item["importance"] for item in findings)


def test_v3_warning_translation_preserves_severity_without_treating_all_warnings_as_errors():
    analysis = _analysis()
    analysis.warnings.append("Date field confidence low")
    analysis.tables[0].quality.alerts.append({"severity": "information", "message": "Type mismatch detected."})
    payload = report_payload(analysis)
    points = payload["human_summary"]["attention_points"]
    assert any("coluna de data suficientemente confiável" in point["message"] for point in points)
    assert any("formatos diferentes" in point["message"] for point in points)
    assert any(point["severity"] == "information" for point in points)
    assert not any(point["severity"] == "critical" for point in points)


def test_v3_analysis_opportunities_only_reference_existing_insights():
    payload = _payload()
    final = {item["id"]: item for item in payload["insights"]["items"]}
    groups = payload["human_summary"]["analysis_opportunities"]
    assert groups
    for group in groups:
        assert group["category"]
        for suggestion in group["suggestions"]:
            assert suggestion["insight_id"] in final
            assert suggestion["question"] == final[suggestion["insight_id"]]["business_question"]


def test_v3_dashboard_summary_matches_the_existing_blueprint():
    payload = _payload()
    summary = payload["human_summary"]["dashboard_summary"]
    blueprint = payload["dashboard_blueprint"]
    assert str(len(blueprint["recommended_pages"])) in summary
    assert "dashboard recomendado" in summary.lower() or "indicador" in summary.lower()
    assert all(page.get("purpose") and page.get("rationale") for page in blueprint["recommended_pages"])


def test_v3_does_not_invent_findings_or_temporal_opportunities_without_support():
    analysis = analyze_file("sem-campos.csv", "csv", b"left,right\na,b\nc,d\n", "utf-8", header_mode="true")
    payload = report_payload(analysis)
    assert payload["human_summary"]["key_findings"] == []
    assert not any(group["category"] == "Evolução" for group in payload["human_summary"]["analysis_opportunities"])
    assert not any(item["type"] == "trend" for item in payload["insights"]["items"])


def test_v3_filters_exclude_unrelated_high_cardinality_and_identifier_fields():
    status = SemanticField(table="A", name="Status", role="dimension", confidence="high", reason="categórica",
                           distinct_count=4, completeness_pct=100)
    customer_id = SemanticField(table="A", name="Customer ID", role="dimension", confidence="high", reason="id",
                                distinct_count=10000, completeness_pct=100)
    unused = SemanticField(table="A", name="Região", role="dimension", confidence="high", reason="não referenciada",
                           distinct_count=5, completeness_pct=100)
    semantic = SemanticModel(dimensions=[status, customer_id, unused])
    insight = _insight("status-risk", dim="Status", table="A")
    blueprint = build_dashboard_blueprint(semantic, InsightsBlock(generated=True, items=[insight]), KpisBlock())
    assert blueprint.filters == [{"table": "A", "column": "Status"}]


def test_v3_blueprint_uses_only_final_priority_insights_and_omits_a_single_weak_page():
    final = _insight("final", priority="high")
    weak = _insight("weak", dim="Coluna7", measure="Valor auxiliar", score=60, priority="low")
    blueprint = build_dashboard_blueprint(SemanticModel(), InsightsBlock(generated=True, items=[final, weak]), KpisBlock())
    assert blueprint.insights == ["final"]
    assert [page["name"] for page in blueprint.recommended_pages] == ["Visão Geral"]

    one_medium = _insight("medium", priority="medium")
    empty = build_dashboard_blueprint(SemanticModel(), InsightsBlock(generated=True, items=[one_medium]), KpisBlock())
    assert empty.recommended_pages == []


def test_v3_blueprint_deduplicates_visuals_and_groups_coherent_topic_pages():
    items = [_insight(f"risk-{index}", measure=f"Risco {index}", score=100-index) for index in range(7)]
    items.append(_insight("same-analysis-again", measure="Risco 6", score=80, table="Outra aba"))
    blueprint = build_dashboard_blueprint(SemanticModel(), InsightsBlock(generated=True, items=items), KpisBlock())
    visuals = [item["id"] for page in blueprint.recommended_pages for item in page["visuals"]]
    assert len(visuals) == len(set(visuals))
    assert len(visuals) == 7
    assert any(page["name"] == "Análise por Contratada" and len(page["visuals"]) == 2
               for page in blueprint.recommended_pages)


def test_v3_does_not_infer_hierarchy_or_cross_filter_from_names_alone():
    semantic = SemanticModel(dimensions=[
        SemanticField(table="A", name="Diretoria", role="dimension", confidence="high", reason="nome", distinct_count=4),
        SemanticField(table="A", name="Gerência", role="dimension", confidence="high", reason="nome", distinct_count=8),
        SemanticField(table="A", name="Gestor", role="dimension", confidence="high", reason="nome", distinct_count=10),
    ])
    blueprint = build_dashboard_blueprint(semantic, InsightsBlock(generated=True, items=[]), KpisBlock())
    assert blueprint.interactions == []


def test_v3_preserves_technical_details_and_renders_human_layer_in_json_html_and_pdf():
    payload = _payload()
    for key in ("tables", "semantic_model", "insights", "kpis", "dashboard_blueprint", "security_warnings"):
        assert key in payload
    assert payload["human_summary"]["technical_details_available"] is True
    batch = {"file_count": 1, "results": [{"filename": payload["filename"], "analysis": payload, "error": None}]}
    html = render_html_report(batch)
    pdf = render_pdf_report(batch)
    assert "Resumo da análise" in html
    assert "Principais descobertas" in html
    assert "Dashboard recomendado" in html
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")


def test_v3_dashboard_does_not_repeat_recommended_visual_ids():
    items = [_insight(f"analysis-{i}", measure=f"Metric {i}", score=100-i) for i in range(9)]
    blueprint = build_dashboard_blueprint(SemanticModel(), InsightsBlock(generated=True, items=items), KpisBlock())
    page_ids = [identifier for page in blueprint.recommended_pages for identifier in page["insight_ids"]]
    assert len(page_ids) == len(set(page_ids))
    assert set(page_ids) == set(blueprint.insights)
