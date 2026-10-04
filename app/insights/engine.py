from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models.discovery_models import CalculationCandidate, Insight, InsightsBlock, KpisBlock, SemanticModel


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def _ref(field: Any) -> dict[str, str]:
    if isinstance(field, dict):
        return {"table": str(field.get("table", "")),
                "column": str(field.get("name") or field.get("column", ""))}
    return {"table": field.table, "column": field.name}


def _confidence(*values: str) -> str:
    if all(value == "high" for value in values):
        return "high"
    return "low" if any(value == "low" for value in values) else "medium"


def _priority(confidence: str, distinct_count: int | None = None) -> str:
    if confidence == "high" and (distinct_count is None or 2 <= distinct_count <= 50):
        return "high"
    return "medium" if confidence != "low" else "low"


def _slug(*values: str) -> str:
    normalized = _norm("-".join(values))
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:100] or "insight"


def _insight(kind: str, title: str, question: str, *, dimensions=(), measures=(), dates=(), visual: str,
             confidence: str, priority: str, evidence: list[str], reason: str, warnings=()) -> Insight:
    return Insight(
        id=_slug(kind, title), type=kind, title=title, business_question=question,
        dimensions=[_ref(field) for field in dimensions], measures=[_ref(field) for field in measures],
        dates=[_ref(field) for field in dates], visual=visual, confidence=confidence,
        priority=priority, evidence=evidence, reason=reason, warnings=list(warnings),
    )


def _calculation_candidates(model: SemanticModel) -> list[CalculationCandidate]:
    candidates: list[CalculationCandidate] = []
    for table in model.tables:
        named = {_norm(field.name): field for field in table.measures}
        covered = next((field for key, field in named.items() if "cobert" in key and "descobert" not in key), None)
        uncovered = next((field for key, field in named.items() if "descobert" in key), None)
        total = next((field for key, field in named.items() if "total" in key and "risco" in key), None)
        pairs: list[tuple[str, Any, Any]] = []
        if covered and total and covered.name != total.name:
            pairs.append(("% Cobertura", covered, total))
        if uncovered and total and uncovered.name != total.name:
            pairs.append(("% Risco Descoberto", uncovered, total))
        for title, numerator, denominator in pairs:
            confidence = _confidence(numerator.confidence, denominator.confidence)
            candidates.append(CalculationCandidate(
                name=title, formula_type="ratio", numerator=numerator.name,
                denominator=denominator.name, table=table.name, confidence=confidence,
                evidence=[f"Medida numeradora encontrada: {numerator.name}.",
                          f"Medida denominadora encontrada: {denominator.name}."],
                reason="Candidata derivada por compatibilidade explícita dos nomes; a fórmula deve ser validada pela regra de negócio.",
            ))
    return candidates


def discover_insights(model: SemanticModel) -> tuple[InsightsBlock, KpisBlock]:
    """Create explainable suggestions from semantic metadata, without cell values or file reads."""
    insights: list[Insight] = []
    kpis: list[dict[str, Any]] = []
    calculations = _calculation_candidates(model)

    for table in model.tables:
        for measure in table.measures:
            confidence = measure.confidence
            kpis.append({
                "name": measure.name, "table": table.name, "measure": _ref(measure),
                "confidence": confidence, "priority": _priority(confidence),
                "evidence": [*measure.evidence, "A coluna foi classificada como medida; nenhum valor individual é incluído."],
                "reason": measure.reason,
            })
            insights.append(_insight(
                "kpi", measure.name, f"Qual é o valor de {measure.name}?", measures=[measure], visual="card/KPI",
                confidence=confidence, priority=_priority(confidence), evidence=measure.evidence,
                reason="Sugestão baseada em uma medida identificada no AnalysisResult.",
            ))

        for dimension in table.dimensions:
            for measure in table.measures:
                confidence = _confidence(dimension.confidence, measure.confidence)
                priority = _priority(confidence, dimension.distinct_count)
                normalized_dimension = _norm(dimension.name)
                metric = measure.name
                title = f"{metric} por {dimension.name}"
                if any(word in normalized_dimension for word in ("contratada", "fornecedor", "empresa")):
                    question = f"Quais {dimension.name.lower()} apresentam maior {metric.lower()}?"
                    kind, visual = "ranking", "barras horizontais"
                elif dimension.distinct_count is not None and dimension.distinct_count <= 8:
                    question = f"Como {metric.lower()} se distribui entre {dimension.name.lower()}?"
                    kind, visual = "distribution", "barras/colunas"
                elif dimension.distinct_count is not None and dimension.distinct_count <= 12:
                    question = f"Como {metric.lower()} se distribui entre {dimension.name.lower()}?"
                    kind, visual = "comparison", "barras/colunas"
                else:
                    question = f"Como {metric.lower()} varia por {dimension.name.lower()}?"
                    kind, visual = "ranking", "barras horizontais"
                evidence = [f"{dimension.name} foi identificada como dimensão categórica.",
                            f"{metric} foi identificada como medida ({measure.format or 'número'})."]
                insights.append(_insight(
                    kind, title, question, dimensions=[dimension], measures=[measure], visual=visual,
                    confidence=confidence, priority=priority, evidence=evidence,
                    reason=f"Combinação gerada porque {dimension.name} é dimensão e {metric} é medida na mesma aba.",
                ))

        # A bounded two-dimension segmentation helps produce richer questions without a Cartesian explosion.
        bounded_dimensions = table.dimensions[:8]
        for first_index, first_dimension in enumerate(bounded_dimensions):
            for second_dimension in bounded_dimensions[first_index + 1:]:
                for measure in table.measures[:5]:
                    confidence = _confidence(first_dimension.confidence, second_dimension.confidence, measure.confidence)
                    dims = [first_dimension, second_dimension]
                    title = f"{measure.name} por {first_dimension.name} e {second_dimension.name}"
                    insights.append(_insight(
                        "segmentation", title,
                        f"Como {measure.name.lower()} varia por {first_dimension.name.lower()} e {second_dimension.name.lower()}?",
                        dimensions=dims, measures=[measure], visual="barras agrupadas",
                        confidence=confidence, priority=_priority(confidence, max(
                            first_dimension.distinct_count or 0, second_dimension.distinct_count or 0)),
                        evidence=[f"{first_dimension.name} e {second_dimension.name} foram identificadas como dimensões.",
                                  f"{measure.name} foi identificada como medida."],
                        reason="Sugestão de segmentação baseada em duas dimensões e uma medida da mesma aba.",
                    ))

        usable_dates = [date for date in table.dates if date.distinct_count is not None
                        and date.distinct_count >= 4 and (date.completeness_pct or 0) >= 80]
        for date in usable_dates:
            for measure in table.measures:
                confidence = _confidence(date.confidence, measure.confidence)
                title = f"Evolução de {measure.name} por {date.name}"
                warning_list = []
                if any(word in _norm(date.name) for word in ("inicio", "fim", "admissao", "vencimento", "vigencia")):
                    warning_list.append("Valide se a data representa um evento temporal adequado para agregação ao longo do tempo.")
                    if confidence == "high":
                        confidence = "medium"
                insights.append(_insight(
                    "trend", title, f"Como {measure.name.lower()} evolui ao longo de {date.name.lower()}?",
                    measures=[measure], dates=[date], visual="linha", confidence=confidence,
                    priority=_priority(confidence),
                    evidence=[f"{date.name} tem {date.distinct_count} valores distintos e {date.completeness_pct:.1f}% de preenchimento.",
                              f"{measure.name} foi identificada como medida."],
                    reason="A data tem preenchimento e cardinalidade suficientes para uma hipótese temporal; valide o significado de negócio.",
                    warnings=warning_list,
                ))

        # Detail tables require a key candidate, and keep a bounded number of suggestions.
        for identifier in [field for field in table.identifiers if field.role == "identifier" and field.confidence == "high"][:2]:
            if not table.measures:
                continue
            measure = table.measures[0]
            confidence = _confidence(identifier.confidence, measure.confidence)
            insights.append(_insight(
                "detail_table", f"Detalhamento de {measure.name} por {identifier.name}",
                f"Quais registros de {identifier.name} devem ser revisados por {measure.name}?",
                dimensions=[identifier], measures=[measure], visual="tabela detalhada", confidence=confidence,
                priority="medium" if confidence != "low" else "low",
                evidence=[f"{identifier.name} atende aos critérios atuais de identificador.",
                          f"{measure.name} foi reconhecida como medida."],
                reason="A combinação oferece contexto de registro; o relatório contém referências de campos, sem valores brutos.",
            ))

    for calculation in calculations:
        title = calculation.name
        insights.append(_insight(
            "coverage", title, f"Qual é a proporção de {calculation.numerator} sobre {calculation.denominator}?",
            measures=[{"table": calculation.table, "name": calculation.numerator},
                      {"table": calculation.table, "name": calculation.denominator}],
            visual="card/KPI", confidence=calculation.confidence,
            priority=_priority(calculation.confidence), evidence=calculation.evidence,
            reason="Candidata de razão baseada em medidas complementares; nenhuma fórmula foi executada nem DAX foi criado.",
            warnings=["Valide denominador, filtros e regra de negócio antes de calcular."],
        ))
        kpis.append({
            "name": calculation.name, "table": calculation.table,
            "calculation_candidate": calculation.model_dump(mode="json"),
            "confidence": calculation.confidence, "priority": _priority(calculation.confidence),
            "reason": calculation.reason,
        })

    # Avoid unbounded combinations on wide workbooks while retaining strongest suggestions.
    priority_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda item: (priority_order[item.priority], item.type, item.title, item.id))
    insights = insights[:100]
    warnings = list(model.semantic_warnings)
    if not insights:
        warnings.append("Não foram encontradas combinações suficientes de dimensão, medida ou data para sugerir análises.")
    return InsightsBlock(generated=True, items=insights, warnings=list(dict.fromkeys(warnings))), KpisBlock(
        suggested=kpis[:100], calculation_candidates=calculations,
    )
