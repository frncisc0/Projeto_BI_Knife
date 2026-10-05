import json

from app.core.config import get_settings
from app.core.exceptions import AnalysisError
from app.models.analysis_models import FileAnalysis
from app.semantic.builder import build_semantic_model
from app.insights.engine import discover_insights
from app.blueprint.builder import build_dashboard_blueprint


def report_payload(analysis: FileAnalysis) -> dict:
    """Return a JSON-ready report without dataframe or reader-specific types."""
    payload = analysis.model_dump(mode="json", exclude_none=True)
    payload.update(discovery_payload(analysis))
    report_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if report_size > get_settings().report_max_bytes:
        raise AnalysisError("O relatório excede o tamanho máximo configurado. Reduza os limites de linhas ou colunas e tente novamente.")
    return payload


def discovery_payload(analysis: FileAnalysis) -> dict:
    """Build V2 discovery blocks from an already computed AnalysisResult."""
    semantic = build_semantic_model(analysis)
    insights, kpis = discover_insights(semantic, analysis.quality.score, analysis)
    semantic.calculated_candidates = [item.model_dump(mode="json") for item in kpis.calculation_candidates]
    blueprint = build_dashboard_blueprint(semantic, insights, kpis)
    return {
        "semantic_model": semantic.model_dump(mode="json"),
        "insights": insights.model_dump(mode="json"),
        "kpis": kpis.model_dump(mode="json"),
        "dashboard_blueprint": blueprint.model_dump(mode="json"),
    }


def refresh_discovery_payload(report: dict) -> None:
    """Refresh discovery blocks after batch relationships have been attached to the report."""
    analysis = FileAnalysis.model_validate(report)
    report.update(discovery_payload(analysis))
