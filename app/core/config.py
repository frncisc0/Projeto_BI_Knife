from functools import lru_cache
import os
from pathlib import Path


class Settings:
    """Centralized settings with conservative local defaults."""

    app_name = "BI Swiss Knife"
    version = "0.2.0"
    max_file_size_mb = int(os.getenv("BI_MAX_FILE_SIZE_MB", "100"))
    max_files_per_batch = int(os.getenv("BI_MAX_FILES_PER_BATCH", "50"))
    max_batch_size_mb = int(os.getenv("BI_MAX_BATCH_SIZE_MB", "500"))
    max_rows_to_preview = int(os.getenv("BI_MAX_ROWS_TO_PREVIEW", "20"))
    max_unique_values = int(os.getenv("BI_MAX_UNIQUE_VALUES", "10"))
    max_category_display = int(os.getenv("BI_MAX_CATEGORY_DISPLAY", "10"))
    temp_file_retention_hours = int(os.getenv("BI_TEMP_FILE_RETENTION_HOURS", "0"))
    allowed_extensions = {".xlsx", ".csv"}
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"


@lru_cache
def get_settings() -> Settings:
    return Settings()
