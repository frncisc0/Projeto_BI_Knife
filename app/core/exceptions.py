class FileValidationError(ValueError):
    """Raised when an uploaded file is unsupported or malformed."""


class AnalysisError(RuntimeError):
    """Raised when a supported file cannot be analyzed safely."""
