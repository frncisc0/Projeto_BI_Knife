from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models.analysis_models import FileAnalysis
from app.models.discovery_models import SemanticField, SemanticModel, SemanticTable


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def _format(column: Any) -> str:
    inferred = _norm(column.inferred_type)
    if "moeda" in inferred or any(word in _norm(column.name) for word in ("custo", "valor", "risco", "salario", "passivo", "encargo", "retencao", "garantia")):
        return "currency"
    if "percent" in inferred or "percent" in _norm(column.name) or "aderencia" in _norm(column.name):
        return "percentage"
    if "inteiro" in inferred:
        return "integer"
    if "decimal" in inferred or "numer" in inferred:
        return "decimal"
    return "number"


def _evidence(column: Any) -> list[str]:
    return [
        f"Papel semântico do AnalysisResult: {column.semantic_role} ({column.semantic_role_confidence}).",
        f"Preenchimento: {column.completeness_pct:.1f}%; cardinalidade: {column.cardinality} ({column.distinct_count} valores distintos).",
    ]


def _confidence(column: Any, sampled: bool) -> str:
    confidence = column.semantic_role_confidence
    if column.completeness_pct < 70:
        confidence = "low"
    elif column.completeness_pct < 90 and confidence == "high":
        confidence = "medium"
    if sampled and confidence == "high":
        confidence = "medium"
    return confidence


def _field(table: Any, column: Any, role: str, reason: str, *, format: str | None = None) -> SemanticField:
    statistics = column.statistics.model_dump(mode="python")
    periods = int(statistics.get("periods", 0) or 0) if role in {"date", "datetime"} else None
    temporal_support = bool(role in {"date", "datetime"} and periods >= 3
                            and column.distinct_count >= 6 and column.completeness_pct >= 80)
    return SemanticField(
        table=table.name, name=column.name, role=role,
        confidence=_confidence(column, table.sampled), evidence=_evidence(column),
        reason=reason, format=format, distinct_count=column.distinct_count,
        completeness_pct=column.completeness_pct,
        temporal_periods=periods, temporal_support=temporal_support,
    )


def _table_kind(table: Any, dimensions: list[SemanticField], measures: list[SemanticField]) -> tuple[str, str, str]:
    existing = table.table_type or "tipo indeterminado"
    if existing != "tipo indeterminado":
        return existing, table.table_type_confidence, table.table_type_reason
    # Enrichment is deliberately conservative and keeps a confidence label.
    if measures and len(measures) >= len(dimensions):
        return "provável fato/transacional", "medium", "Predomínio de medidas reconhecidas sobre dimensões; classificação heurística baseada no AnalysisResult."
    if dimensions and len(dimensions) >= 2 and len(dimensions) > len(measures):
        return "provável dimensão/cadastro", "medium", "Predomínio de atributos categóricos; classificação heurística baseada no AnalysisResult."
    return existing, "low", table.table_type_reason


def _relationship_role(column_name: str, table_name: str, tables: dict[str, Any]) -> str:
    table = tables.get(table_name)
    if not table:
        return "unknown"
    column = next((item for item in table.column_analyses if item.name == column_name), None)
    return column.semantic_role if column else "unknown"


def build_semantic_model(analysis: FileAnalysis) -> SemanticModel:
    """Build a semantic view strictly from the completed AnalysisResult metadata."""
    semantic_tables: list[SemanticTable] = []
    by_name: dict[str, Any] = {table.name: table for table in analysis.tables}
    relationships: list[dict[str, Any]] = []
    possible_foreign_keys: list[dict[str, Any]] = []
    dimensions: list[SemanticField] = []
    measures: list[SemanticField] = []
    dates: list[SemanticField] = []
    identifiers: list[SemanticField] = []
    warnings: list[str] = []

    for table in analysis.tables:
        table_dimensions: list[SemanticField] = []
        table_measures: list[SemanticField] = []
        table_dates: list[SemanticField] = []
        table_identifiers: list[SemanticField] = []
        for column in table.column_analyses:
            # Sensitive fields are intentionally excluded from discovery, even as names.
            if column.sensitive or column.empty or column.completeness_pct < 50:
                continue
            role = column.semantic_role
            if role == "category":
                if column.completeness_pct < 80 or column.distinct_count < 2 or column.distinct_count > 1000:
                    continue
                reason = "Campo categórico com preenchimento e cardinalidade compatíveis com segmentação."
                candidate = _field(table, column, "dimension", reason)
                table_dimensions.append(candidate)
                dimensions.append(candidate)
            elif role == "measure":
                reason = "Campo identificado como medida pelo papel semântico; alta unicidade não o transforma em chave."
                candidate = _field(table, column, "measure", reason, format=_format(column))
                table_measures.append(candidate)
                measures.append(candidate)
            elif role in {"date", "datetime"}:
                stats = column.statistics.model_dump(mode="python")
                period_count = int(stats.get("periods", 0) or 0)
                reason = (f"Campo data/hora com {period_count} períodos mensais observados; tendência só é elegível com pelo menos 3 períodos, 6 datas distintas e 80% de preenchimento."
                          if period_count else "Campo identificado como data/hora; sem evidência de cobertura em períodos suficiente para uma tendência.")
                candidate = _field(table, column, role, reason, format="date" if role == "date" else "datetime")
                table_dates.append(candidate)
                dates.append(candidate)
            elif role in {"identifier", "code"}:
                classification = "identifier" if column.key_candidate else "possible_identifier"
                reason = ("Nome/papel semântico compatível e critérios de chave atendidos." if column.key_candidate
                          else "Nome/papel semântico de identificador; unicidade insuficiente ou ausente para confirmar chave.")
                candidate = _field(table, column, classification, reason)
                table_identifiers.append(candidate)
                identifiers.append(candidate)

        kind, kind_confidence, kind_reason = _table_kind(table, table_dimensions, table_measures)
        evidence = [f"Classificação V1: {table.table_type} ({table.table_type_confidence})."]
        if len(table_dimensions) or len(table_measures):
            evidence.append(f"Semantic layer: {len(table_dimensions)} dimensões e {len(table_measures)} medidas elegíveis.")
        semantic_tables.append(SemanticTable(
            name=table.name, table_type=kind, confidence=kind_confidence, evidence=evidence,
            reason=kind_reason, dimensions=table_dimensions, measures=table_measures,
            dates=table_dates, identifiers=table_identifiers,
        ))
        if table.sampled:
            warnings.append(f"A semântica da aba '{table.name}' foi inferida sobre uma amostra.")
        if table.status not in {"completed", "completed_empty"}:
            warnings.append(f"A aba '{table.name}' não foi analisada integralmente (status: {table.status}).")

    for relationship in analysis.relationships:
        source_role = _relationship_role(relationship.source_column, relationship.source_table, by_name)
        target_role = _relationship_role(relationship.target_column, relationship.target_table, by_name)
        if source_role == "measure" or target_role == "measure":
            continue
        item = {
            "source_table": relationship.source_table, "source_column": relationship.source_column,
            "target_table": relationship.target_table, "target_column": relationship.target_column,
            "confidence": relationship.confidence, "reason": relationship.reason,
            "relationship_type": relationship.cardinality,
        }
        relationships.append(item)
        if {source_role, target_role} & {"identifier", "code"}:
            possible_foreign_keys.append(item)

    domain_rules = {
        "trabalhista": ("trabalh", "rescis", "admiss", "passivo"),
        "financeiro": ("custo", "valor", "faturamento", "encargo", "retencao", "garantia"),
        "contratos": ("contrato", "vigencia", "fornecedor", "contratada"),
        "recursos humanos": ("colaborador", "funcionario", "gestor", "salario"),
    }
    names = " ".join([table.name for table in analysis.tables] + [column.name for table in analysis.tables for column in table.column_analyses])
    normalized_names = _norm(names)
    domains = [domain for domain, terms in domain_rules.items() if any(_norm(term) in normalized_names for term in terms)]
    if not semantic_tables:
        warnings.append("Nenhuma tabela produziu evidência semântica suficiente.")
    all_types = [table.table_type for table in semantic_tables]
    dominant_type = "desconhecida"
    if all_types and all(item.startswith("provável fato") or "transacional" in item for item in all_types):
        dominant_type = "provável fato/transacional"
    elif all_types and all("dimensão" in item or "cadastro" in item for item in all_types):
        dominant_type = "provável dimensão/cadastro"

    return SemanticModel(
        tables=semantic_tables, table_type=dominant_type,
        table_type_confidence="medium" if dominant_type != "desconhecida" else "low",
        dimensions=dimensions, measures=measures, dates=dates, identifiers=identifiers,
        possible_foreign_keys=possible_foreign_keys, relationships=relationships,
        business_domains=domains, semantic_warnings=list(dict.fromkeys(warnings)),
    )
