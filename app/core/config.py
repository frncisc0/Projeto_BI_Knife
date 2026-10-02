from functools import lru_cache
import os
from pathlib import Path


class Settings:
    """Centralized settings with conservative local defaults."""

    app_name = "BI Swiss Knife"
    version = "0.3.0"
    max_file_size_mb = int(os.getenv("BI_MAX_FILE_SIZE_MB", "100"))
    max_xlsx_uncompressed_mb = int(os.getenv("BI_MAX_XLSX_UNCOMPRESSED_MB", "500"))
    max_files_per_batch = int(os.getenv("BI_MAX_FILES_PER_BATCH", "50"))
    max_batch_size_mb = int(os.getenv("BI_MAX_BATCH_SIZE_MB", "500"))
    max_rows_to_analyze = int(os.getenv("BI_MAX_ROWS_TO_ANALYZE", "200000"))
    max_columns_to_analyze = int(os.getenv("BI_MAX_COLUMNS_TO_ANALYZE", "100"))
    max_cells_to_analyze = int(os.getenv("BI_MAX_CELLS_TO_ANALYZE", "250000"))
    max_tables_to_analyze = int(os.getenv("BI_MAX_TABLES_TO_ANALYZE", "20"))
    max_relationship_value_rows = int(os.getenv("BI_MAX_RELATIONSHIP_VALUE_ROWS", "10000"))
    max_batch_relationship_cells = int(os.getenv("BI_MAX_BATCH_RELATIONSHIP_CELLS", "250000"))
    max_relationship_candidates = int(os.getenv("BI_MAX_RELATIONSHIP_CANDIDATES", "100"))
    max_key_candidates = int(os.getenv("BI_MAX_KEY_CANDIDATES", "10"))
    null_attention_threshold_pct = float(os.getenv("BI_NULL_ATTENTION_THRESHOLD_PCT", "5"))
    null_moderate_threshold_pct = float(os.getenv("BI_NULL_MODERATE_THRESHOLD_PCT", "20"))
    null_critical_threshold_pct = float(os.getenv("BI_NULL_CRITICAL_THRESHOLD_PCT", "20"))
    quality_excellent_threshold = float(os.getenv("BI_QUALITY_EXCELLENT_THRESHOLD", "95"))
    quality_good_threshold = float(os.getenv("BI_QUALITY_GOOD_THRESHOLD", "85"))
    quality_attention_threshold = float(os.getenv("BI_QUALITY_ATTENTION_THRESHOLD", "65"))
    quality_completeness_weight = float(os.getenv("BI_QUALITY_COMPLETENESS_WEIGHT", "0.3"))
    quality_uniqueness_weight = float(os.getenv("BI_QUALITY_UNIQUENESS_WEIGHT", "0.25"))
    quality_consistency_weight = float(os.getenv("BI_QUALITY_CONSISTENCY_WEIGHT", "0.15"))
    quality_validity_weight = float(os.getenv("BI_QUALITY_VALIDITY_WEIGHT", "0.2"))
    quality_integrity_weight = float(os.getenv("BI_QUALITY_INTEGRITY_WEIGHT", "0.1"))
    percentiles = tuple(float(value.strip()) for value in os.getenv("BI_PERCENTILES", "10,90").split(",") if value.strip())
    enable_sampling = os.getenv("BI_ENABLE_SAMPLING", "true").casefold() == "true"
    sample_size = int(os.getenv("BI_SAMPLE_SIZE", "100000"))
    analysis_timeout_seconds = int(os.getenv("BI_ANALYSIS_TIMEOUT_SECONDS", "300"))
    report_max_bytes = int(os.getenv("BI_REPORT_MAX_BYTES", str(25 * 1024 * 1024)))
    allowed_extensions = {".xlsx", ".csv"}
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"


@lru_cache
def get_settings() -> Settings:
    return Settings()
