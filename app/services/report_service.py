import json

from app.core.config import get_settings
from app.core.exceptions import AnalysisError
from app.models.analysis_models import FileAnalysis


def report_payload(analysis: FileAnalysis) -> dict:
    """Return a JSON-ready report without dataframe or reader-specific types."""
    payload = analysis.model_dump(mode="json", exclude_none=True)
    report_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if report_size > get_settings().report_max_bytes:
        raise AnalysisError("O relatório excede o tamanho máximo configurado. Reduza os limites de linhas ou colunas e tente novamente.")
    return payload
