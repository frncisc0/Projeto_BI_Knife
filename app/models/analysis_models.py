from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnAnalysis(BaseModel):
    name: str
    inferred_type: str
    null_count: int
    null_pct: float
    distinct_count: int
    distinct_pct: float
    duplicate_count: int
    empty: bool
    key_candidate: bool
    inconsistent_values: int = 0
    invalid_dates: int = 0
    statistics: dict[str, Any] = Field(default_factory=dict)
    top_values: list[dict[str, Any]] = Field(default_factory=list)


class TableAnalysis(BaseModel):
    name: str
    rows: int
    columns: int
    duplicate_rows: int
    preview: list[dict[str, Any]]
    column_analyses: list[ColumnAnalysis]


class RelationshipCandidate(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    coverage_pct: float
    confidence: Literal["high", "medium"]
    reason: str


class FileAnalysis(BaseModel):
    filename: str
    file_type: Literal["csv", "xlsx"]
    file_size_bytes: int
    tables: list[TableAnalysis]
    relationships: list[RelationshipCandidate]
    warnings: list[str] = Field(default_factory=list)
