from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models.analysis_models import FileAnalysis
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


def _priority(score: int) -> str:
    return "high" if score >= 75 else "medium" if score >= 55 else "low"


def _relevance_score(kind: str, dimensions, measures, dates, confidence: str,
                     warnings: list[str], quality_score: float) -> int:
    """Weighted score: semantic 20, measure 25, dimension 15, fit 20, quality 20, penalties up to 20.

    Business keywords add evidence only; they never assert that a field is a company's principal indicator.
    """
    semantic = {"high": 20, "medium": 14, "low": 6}[confidence]
    measure_terms = {"risco", "passivo", "cobertura", "coberto", "descoberto", "garantia",
                     "custo", "valor", "processo", "encargo", "faturamento"}
    measure_name = " ".join(_norm(field.name) for field in measures)
    measure_relevance = min(25, sum(5 for term in measure_terms if term in measure_name))
    dimension_terms = {"contratada", "fornecedor", "empresa", "diretoria", "gerencia", "gestor", "status", "regiao"}
    dimension_name = " ".join(_norm(field.name) for field in dimensions)
    dimension_relevance = 15 if any(term in dimension_name for term in dimension_terms) else (8 if dimensions else 0)
    fit = {"ranking": 20, "comparison": 19, "trend": 20, "coverage": 20, "distribution": 15,
           "segmentation": 13, "detail_table": 12, "kpi": 15}.get(kind, 8)
    quality = round(20 * max(0, min(100, quality_score)) / 100)
    warning_penalty = min(8, len(warnings) * 4)
    confidence_penalty = {"high": 0, "medium": 3, "low": 6}[confidence]
    distinct_penalty = 0
    for field in dimensions:
        if field.distinct_count is not None and field.distinct_count > 50:
            distinct_penalty = min(6, distinct_penalty + 6)
    return max(0, min(100, semantic + measure_relevance + dimension_relevance + fit + quality
                      - warning_penalty - confidence_penalty - distinct_penalty))


def _slug(*values: str) -> str:
    normalized = _norm("-".join(values))
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:100] or "insight"


def _insight(kind: str, title: str, question: str, *, dimensions=(), measures=(), dates=(), visual: str,
             confidence: str, priority: str, evidence: list[str], reason: str, warnings=(),
             relevance_score: int = 0) -> Insight:
    return Insight(
        id=_slug(kind, title), type=kind, title=title, business_question=question,
        dimensions=[_ref(field) for field in dimensions], measures=[_ref(field) for field in measures],
        dates=[_ref(field) for field in dates], visual=visual, confidence=confidence,
        priority=priority, relevance_score=relevance_score, evidence=evidence, reason=reason, warnings=list(warnings),
    )


def _business_question(dimension_name: str, measure_name: str) -> tuple[str, str, str]:
    normalized = _norm(dimension_name)
    measure = measure_name.casefold()
    if "contratada" in normalized:
        return "ranking", "barras horizontais", f"Quais contratadas apresentam maior {measure}?"
    if "fornecedor" in normalized or "supplier" in normalized:
        return "ranking", "barras horizontais", f"Quais fornecedores apresentam maior {measure}?"
    entity_forms = (("empresa", "empresas"), ("diretoria", "diretorias"), ("gerencia", "gerências"),
                    ("gestor", "gestores"), ("status", "categorias de status"), ("regiao", "regiões"))
    for singular, plural in entity_forms:
        if singular in normalized:
            if singular == "empresa":
                parts = dimension_name.split(maxsplit=1)
                suffix = parts[1].strip() if len(parts) > 1 and _norm(parts[0]) == "empresa" else ""
                entity = "empresas" + (f" {suffix}" if suffix else "")
                return "comparison", "barras/colunas", f"Como o {measure} está distribuído entre as {entity}?"
            return "comparison", "barras/colunas", f"Quais {plural} concentram maior {measure}?"
    if "status" in normalized:
        return "comparison", "barras/colunas", f"Como o {measure} varia por {dimension_name.lower()}?"
    return "ranking", "barras horizontais", f"Quais categorias de {dimension_name.lower()} apresentam maior {measure}?"


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


def discover_insights(model: SemanticModel, quality_score: float = 100,
                      analysis: FileAnalysis | None = None) -> tuple[InsightsBlock, KpisBlock]:
    """Create explainable suggestions from semantic metadata, without cell values or file reads."""
    insights: list[Insight] = []
    kpis: list[dict[str, Any]] = []
    calculations = _calculation_candidates(model)

    for table in model.tables:
        for measure in table.measures:
            confidence = measure.confidence
            score = _relevance_score("kpi", [], [measure], [], confidence, [], quality_score)
            kpis.append({
                "name": measure.name, "table": table.name, "measure": _ref(measure),
                "confidence": confidence, "relevance_score": score, "priority": _priority(score),
                "evidence": [*measure.evidence, "A coluna foi classificada como medida; nenhum valor individual é incluído."],
                "reason": measure.reason,
            })
            insights.append(_insight(
                "kpi", measure.name, f"Qual é o valor de {measure.name}?", measures=[measure], visual="card/KPI",
                confidence=confidence, priority=_priority(score), relevance_score=score, evidence=measure.evidence,
                reason="Sugestão baseada em uma medida identificada no AnalysisResult.",
            ))

    if analysis is not None:
        semantic_measures = {(field.table, field.name): field for field in model.measures}
        for table in analysis.tables:
            for column in table.column_analyses:
                if column.sensitive:
                    continue
                measure = semantic_measures.get((table.name, column.name))
                for anomaly in column.anomalies:
                    confidence = measure.confidence if measure else "medium"
                    warnings = ["Anomalia estatística é um sinal para revisão e não confirma erro de negócio."]
                    score = _relevance_score("outlier", [], [measure] if measure else [], [], confidence,
                                             warnings, quality_score)
                    insights.append(_insight(
                        "outlier", f"Revisar anomalias em {column.name}",
                        f"Quais ocorrências de {column.name} merecem investigação?",
                        measures=[measure] if measure else [], visual="boxplot/tabela de revisão",
                        confidence=confidence, priority=_priority(score), relevance_score=score,
                        evidence=[f"O AnalysisResult registrou {anomaly.count} ocorrência(s) pelo método {anomaly.method}.",
                                  anomaly.description],
                        reason="Sugestão criada somente porque o AnalysisResult contém evidência estatística para esta coluna.",
                        warnings=warnings,
                    ))

    for table in model.tables:
        for dimension in table.dimensions:
            for measure in table.measures:
                confidence = _confidence(dimension.confidence, measure.confidence)
                kind, visual, question = _business_question(dimension.name, measure.name)
                score = _relevance_score(kind, [dimension], [measure], [], confidence, [], quality_score)
                metric = measure.name
                title = f"{metric} por {dimension.name}"
                if kind == "ranking" and dimension.distinct_count is not None and dimension.distinct_count > 100:
                    score = max(0, score - 8)
                evidence = [f"{dimension.name} foi identificada como dimensão categórica.",
                            f"{metric} foi identificada como medida ({measure.format or 'número'})."]
                insights.append(_insight(
                    kind, title, question, dimensions=[dimension], measures=[measure], visual=visual,
                    confidence=confidence, priority=_priority(score), relevance_score=score, evidence=evidence,
                    reason=(f"Combinação gerada porque {dimension.name} é dimensão e {metric} é medida na mesma aba. "
                            "O nome da medida e da dimensão contribui apenas como evidência heurística, não como confirmação do contexto empresarial."),
                ))

        # A bounded two-dimension segmentation helps produce richer questions without a Cartesian explosion.
        bounded_dimensions = table.dimensions[:8]
        for first_index, first_dimension in enumerate(bounded_dimensions):
            for second_dimension in bounded_dimensions[first_index + 1:]:
                for measure in table.measures[:5]:
                    confidence = _confidence(first_dimension.confidence, second_dimension.confidence, measure.confidence)
                    dims = [first_dimension, second_dimension]
                    score = _relevance_score("segmentation", dims, [measure], [], confidence, [], quality_score)
                    title = f"{measure.name} por {first_dimension.name} e {second_dimension.name}"
                    insights.append(_insight(
                        "segmentation", title,
                        f"Como {measure.name.lower()} varia por {first_dimension.name.lower()} e {second_dimension.name.lower()}?",
                        dimensions=dims, measures=[measure], visual="barras agrupadas",
                        confidence=confidence, priority=_priority(score), relevance_score=score,
                        evidence=[f"{first_dimension.name} e {second_dimension.name} foram identificadas como dimensões.",
                                  f"{measure.name} foi identificada como medida."],
                        reason="Sugestão de segmentação baseada em duas dimensões e uma medida da mesma aba.",
                    ))

        usable_dates = [date for date in table.dates if date.temporal_support]
        for date in usable_dates:
            for measure in table.measures:
                confidence = _confidence(date.confidence, measure.confidence)
                title = f"Evolução de {measure.name} por {date.name}"
                warning_list = []
                normalized_date_name = _norm(date.name)
                if any(word in normalized_date_name for word in ("inicio", "fim", "admissao", "vencimento", "vigencia")):
                    warning_list.append("Confirme se a data de vigência representa o evento temporal que se deseja acompanhar.")
                score = _relevance_score("trend", [], [measure], [date], confidence, warning_list, quality_score)
                insights.append(_insight(
                    "trend", title, f"Como {measure.name.lower()} evolui ao longo de {date.name.lower()}?",
                    measures=[measure], dates=[date], visual="linha", confidence=confidence,
                    priority=_priority(score), relevance_score=score,
                    evidence=[f"{date.name} tem {date.distinct_count} valores distintos em {date.temporal_periods} períodos mensais e {date.completeness_pct:.1f}% de preenchimento.",
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
            score = _relevance_score("detail_table", [identifier], [measure], [], confidence, [], quality_score)
            insights.append(_insight(
                "detail_table", f"Detalhamento de {measure.name} por {identifier.name}",
                f"Quais registros de {identifier.name} devem ser revisados por {measure.name}?",
                dimensions=[identifier], measures=[measure], visual="tabela detalhada", confidence=confidence,
                priority=_priority(score), relevance_score=score,
                evidence=[f"{identifier.name} atende aos critérios atuais de identificador.",
                          f"{measure.name} foi reconhecida como medida."],
                reason="A combinação oferece contexto de registro; o relatório contém referências de campos, sem valores brutos.",
            ))

    for calculation in calculations:
        title = calculation.name
        calculation_warnings = ["Valide denominador, filtros e regra de negócio antes de calcular."]
        numerator = next((field for table in model.tables if table.name == calculation.table for field in table.measures
                          if field.name == calculation.numerator), None)
        denominator = next((field for table in model.tables if table.name == calculation.table for field in table.measures
                            if field.name == calculation.denominator), None)
        score = _relevance_score("coverage", [], [field for field in (numerator, denominator) if field], [],
                                 calculation.confidence, calculation_warnings, quality_score)
        insights.append(_insight(
            "coverage", title, f"Qual é a proporção de {calculation.numerator} sobre {calculation.denominator}?",
            measures=[{"table": calculation.table, "name": calculation.numerator},
                      {"table": calculation.table, "name": calculation.denominator}],
            visual="card/KPI", confidence=calculation.confidence,
            priority=_priority(score), relevance_score=score, evidence=calculation.evidence,
            reason="Candidata de razão baseada em medidas complementares; nenhuma fórmula foi executada nem DAX foi criado.",
            warnings=calculation_warnings,
        ))
        kpis.append({
            "name": calculation.name, "table": calculation.table,
            "calculation_candidate": calculation.model_dump(mode="json"),
            "confidence": calculation.confidence, "relevance_score": score, "priority": _priority(score),
            "reason": calculation.reason,
        })

    # Avoid unbounded combinations on wide workbooks while retaining strongest suggestions.
    priority_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda item: (-item.relevance_score, priority_order[item.priority], item.type, item.title, item.id))
    insights = insights[:100]
    warnings = list(model.semantic_warnings)
    if not insights:
        warnings.append("Não foram encontradas combinações suficientes de dimensão, medida ou data para sugerir análises.")
    kpis.sort(key=lambda item: (-item["relevance_score"], priority_order.get(item["priority"], 3), item["name"]))
    return InsightsBlock(generated=True, items=insights, warnings=list(dict.fromkeys(warnings))), KpisBlock(
        suggested=kpis[:100], calculation_candidates=calculations,
    )
