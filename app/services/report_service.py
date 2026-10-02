from app.models.analysis_models import FileAnalysis


def report_payload(analysis: FileAnalysis) -> dict:
    """Return a JSON-ready report without dataframe or reader-specific types."""
    return analysis.model_dump(mode="json")
