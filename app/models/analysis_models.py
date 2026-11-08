from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StatisticsAnalysis(BaseModel):
    """Extensible statistics contract; category labels and raw examples are excluded."""

    model_config = {"extra": "allow"}
    min: int | float | str | None = None
    max: int | float | str | None = None
    mean: float | None = None
    median: float | None = None
    std_dev: float | None = None
    q1: float | None = None
    q3: float | None = None
    p10: float | None = None
    p90: float | None = None
    zero_count: int | None = None
    negative_count: int | None = None


class ColumnAnalysis(BaseModel):
    name: str
    original_type: str
    physical_type: str = "unknown"
    inferred_type: str
    semantic_role: Literal["identifier", "category", "measure", "date", "datetime", "boolean", "text", "code", "unknown"] = "unknown"
    semantic_role_confidence: Literal["low", "medium", "high"] = "low"
    confidence: Literal["low", "medium", "high"]
    type_reason: str
    sensitive: bool = False
    sensitivity_reason: str | None = None
    sensitivity_category: str | None = None
    sensitivity_confidence: Literal["low", "medium", "high"] = "low"
    value_count: int
    null_count: int
    null_pct: float
    completeness_pct: float
    distinct_count: int
    distinct_pct: float
    cardinality: str
    duplicate_count: int
    empty: bool
    key_candidate: bool
    key_assessment: Literal["strong_candidate", "possible_identifier", "high_uniqueness_measure", "high_uniqueness_unconfirmed", "not_candidate"] = "not_candidate"
    key_confidence: Literal["low", "medium", "high"] | None = None
    key_reasons: list[str] = Field(default_factory=list)
    inconsistent_values: int = 0
    invalid_dates: int = 0
    zero_count: int | None = None
    negative_count: int | None = None
    statistics: StatisticsAnalysis = Field(default_factory=StatisticsAnalysis)
    top_values: list[dict[str, Any]] = Field(default_factory=list)  # Frequencies only; never contains cell values.
    null_classification: str
    anomalies: list[Anomaly] = Field(default_factory=list)


class Anomaly(BaseModel):
    column: str
    method: str
    count: int
    severity: Literal["critical", "attention", "information"]
    description: str


class QualityAnalysis(BaseModel):
    score: float
    classification: Literal["Excelente", "Boa", "Atenção", "Baixa", "Crítica"]
    completeness_pct: float
    uniqueness_pct: float
    consistency_pct: float
    validity_pct: float
    integrity_pct: float | None = None
    integrity_assessed: bool = False
    alerts: list[dict[str, str | int | float]] = Field(default_factory=list)


class FileSecurityAnalysis(BaseModel):
    active_content_detected: bool = False
    active_content_types: list[str] = Field(default_factory=list)
    active_content_action: Literal["not_executed"] = "not_executed"
    external_relationships_detected: bool = False
    external_relationship_count: int = 0
    external_relationships_followed: bool = False
    external_connections_updated: bool = False
    macros_executed: bool = False
    external_connections_accessed: bool = False
    embedded_objects_executed: bool = False
    formulas_recalculated: bool = False
    formulas_action: Literal["cached_values_only", "not_applicable"] = "not_applicable"


class TableAnalysis(BaseModel):
    name: str
    status: Literal["completed", "completed_empty", "partial", "skipped", "error", "failed"] = "completed"
    error_message: str | None = None
    header_row_used: int | None = None
    header_detection: dict[str, Any] = Field(default_factory=dict)
    rows: int
    rows_available: int = 0
    rows_analyzed: int
    sampled: bool
    sampling_method: str = "none"
    rows_empty: int = 0
    trailing_empty_rows: int = 0
    columns: int
    columns_analyzed: int
    empty_rows: int
    empty_columns: int
    duplicate_rows: int
    table_type: str
    table_type_confidence: Literal["low", "medium", "high"]
    table_type_reason: str
    key_candidates: list[dict[str, Any]] = Field(default_factory=list)
    quality: QualityAnalysis
    column_analyses: list[ColumnAnalysis]


class RelationshipCandidate(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    coverage_pct: float
    matched_values: int
    unmatched_values: int
    cardinality: Literal["1:N", "1:1", "N:1", "unclear"]
    confidence: Literal["high", "medium"]
    reason: str


class FileAnalysis(BaseModel):
    analysis_id: str
    analyzed_at: datetime
    processing_time_ms: int
    filename: str
    file_type: Literal["csv", "xlsx", "xlsm"]
    file_size_bytes: int
    file_sha256: str
    status: Literal["completed", "partial", "failed"]
    settings: dict[str, Any] = Field(default_factory=dict)
    security_warnings: list[str] = Field(default_factory=list)
    security: FileSecurityAnalysis | None = None
    tables: list[TableAnalysis]
    relationships: list[RelationshipCandidate]
    anomalies: list[Anomaly] = Field(default_factory=list)
    quality: QualityAnalysis
    warnings: list[str] = Field(default_factory=list)


class AnalysisReport(FileAnalysis):
    """Versioned structured report contract; inherits the file metadata envelope."""
