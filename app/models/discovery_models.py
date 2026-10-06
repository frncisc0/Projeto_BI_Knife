from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Confidence = Literal["low", "medium", "high"]


class SemanticField(BaseModel):
    table: str
    name: str
    role: str
    confidence: Confidence
    evidence: list[str] = Field(default_factory=list)
    source: str = "AnalysisResult"
    reason: str
    format: str | None = None
    distinct_count: int | None = None
    completeness_pct: float | None = None
    temporal_periods: int | None = None
    temporal_support: bool = False


class SemanticTable(BaseModel):
    name: str
    table_type: str
    confidence: Confidence
    evidence: list[str] = Field(default_factory=list)
    reason: str
    dimensions: list[SemanticField] = Field(default_factory=list)
    measures: list[SemanticField] = Field(default_factory=list)
    dates: list[SemanticField] = Field(default_factory=list)
    identifiers: list[SemanticField] = Field(default_factory=list)


class SemanticModel(BaseModel):
    tables: list[SemanticTable] = Field(default_factory=list)
    table_type: str = "desconhecida"
    table_type_confidence: Confidence = "low"
    dimensions: list[SemanticField] = Field(default_factory=list)
    measures: list[SemanticField] = Field(default_factory=list)
    dates: list[SemanticField] = Field(default_factory=list)
    identifiers: list[SemanticField] = Field(default_factory=list)
    possible_foreign_keys: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    calculated_candidates: list[dict[str, Any]] = Field(default_factory=list)
    business_domains: list[str] = Field(default_factory=list)
    semantic_warnings: list[str] = Field(default_factory=list)


class Insight(BaseModel):
    id: str
    type: str
    title: str
    business_question: str
    dimensions: list[dict[str, str]] = Field(default_factory=list)
    measures: list[dict[str, str]] = Field(default_factory=list)
    dates: list[dict[str, str]] = Field(default_factory=list)
    visual: str
    confidence: Confidence
    priority: Literal["low", "medium", "high"]
    relevance_score: int = 0
    evidence: list[str] = Field(default_factory=list)
    reason: str
    warnings: list[str] = Field(default_factory=list)


class CalculationCandidate(BaseModel):
    name: str
    formula_type: str
    numerator: str
    denominator: str
    table: str
    confidence: Confidence
    evidence: list[str] = Field(default_factory=list)
    reason: str


class InsightsBlock(BaseModel):
    generated: bool
    items: list[Insight] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    deduplicated_count: int = 0
    duplicates_removed: int = 0
    top_limit: int = 12


class KpisBlock(BaseModel):
    suggested: list[dict[str, Any]] = Field(default_factory=list)
    calculation_candidates: list[CalculationCandidate] = Field(default_factory=list)


class DashboardBlueprint(BaseModel):
    title: str
    objective: str
    recommended_pages: list[dict[str, Any]] = Field(default_factory=list)
    kpis: list[dict[str, Any]] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    filters: list[dict[str, str]] = Field(default_factory=list)
    dimensions: list[dict[str, str]] = Field(default_factory=list)
    measures: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
