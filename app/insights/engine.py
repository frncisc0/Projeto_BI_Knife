from __future__ import annotations

import re
from typing import Any

from app.core.text import fold
from app.models.analysis_models import FileAnalysis
from app.models.discovery_models import CalculationCandidate, Insight, InsightsBlock, KpisBlock, SemanticModel


def _ref(field: Any) -> dict[str, str]:
    if isinstance(field, dict):
        return {"table": str(field.get("table", "")),
                "column": str(field.get("name") or field.get("column", ""))}
    return {"table": field.table, "column": field.name}


def _confidence(*values: str) -> str:
    if all(value == "high" for value in values):
        return "high"
    return "low" if any(value == "low" for value in values) else "medium"


def _priority(score: int, confidence: str = "high", warnings=(), dimensions=(), measures=()) -> str:
    """Priority requires score plus confidence and relevant evidence, not score alone."""
    def field_value(field, key, default=None):
        return field.get(key, default) if isinstance(field, dict) else getattr(field, key, default)

    dimension_strengths = [_dimension_strength(field_value(field, "name", field_value(field, "column", "")))
                           for field in dimensions]
    measure_strengths = [_measure_strength(field_value(field, "name", field_value(field, "column", "")),
                                            field_value(field, "format"), field_value(field, "table", ""))
                         for field in measures]
    if dimension_strengths and max(dimension_strengths) == 0:
        return "low"
    if measure_strengths and max(measure_strengths) == 0:
        return "low"
    if score >= 76 and confidence == "high" and not warnings:
        if all(field_value(field, "distinct_count") is None or 2 <= field_value(field, "distinct_count") <= 200
               for field in dimensions) \
                and (not dimensions or any(value >= 2 for value in dimension_strengths)) \
                and (not measures or any(value >= 3 for value in measure_strengths)):
            return "high"
    return "medium" if score >= 52 and confidence != "low" else "low"


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(value)))


def _dimension_strength(name: str) -> int:
    tokens = _tokens(name)
    strong = {"empresa", "contratada", "fornecedor", "contrato", "diretoria", "gerencia", "gestor",
              "status", "vigencia", "funcao", "regiao", "unidade", "departamento", "categoria"}
    weak = {"coluna", "campo", "auxiliar", "observacao", "sequencia", "ordem", "linha", "indice", "flag"}
    if tokens & weak or re.fullmatch(r"(?:coluna|campo)?\s*\d+", fold(name).strip()):
        return 0
    if tokens & strong:
        return 3
    if len(tokens) == 1 and next(iter(tokens), "") in {"id", "codigo", "chave", "numero"}:
        return 0
    return 1


def _measure_strength(name: str, format: str | None = None, table: str = "") -> int:
    tokens = _tokens(name)
    strong = {"risco", "passivo", "cobertura", "coberto", "descoberto", "garantia", "custo", "valor",
              "processo", "faturamento", "receita", "despesa", "folha", "rescisao", "saldo", "total",
              "montante", "prejuizo", "pagamento", "quantidade", "volume", "percentual", "taxa"}
    weak = {"indice", "ordem", "sequencia", "codigo", "id", "flag", "auxiliar", "contador", "chave"}
    if tokens & weak:
        return 0
    if tokens & strong:
        return 3
    # Type/format and table labels provide supporting evidence when the measure name is generic.
    context_tokens = _tokens(table)
    context = {"risco", "financeiro", "financeira", "contrato", "venda", "pedido", "faturamento", "folha"}
    if (format or "").casefold() in {"currency", "percentage"} or context_tokens & context:
        return 2
    return 1


def _relevance_score(kind: str, dimensions, measures, dates, confidence: str,
                     warnings: list[str], quality_score: float) -> int:
    """Deterministic 100-point score. Component weights are explicit for review:

    semantic fit 20, measure importance 18, analytical usefulness 18, data quality 15,
    cardinality fit 10, business signal 10, confidence 9; penalties up to 20.
    Names are weak evidence only; this score never asserts business truth.
    """
    semantic_fit = 8
    if dimensions:
        semantic_fit = round(sum(8 + 4 * _dimension_strength(field.name) for field in dimensions) / len(dimensions))
        semantic_fit = min(20, semantic_fit)
    if dates and kind == "trend":
        semantic_fit = min(20, 12 + 4 * sum(bool(field.temporal_support) for field in dates))

    strengths = [_measure_strength(field.name, field.format, field.table) for field in measures]
    importance = round(18 * (sum(strengths) / (3 * len(strengths)))) if strengths else 0
    usefulness = {"ranking": 18, "comparison": 18, "trend": 17, "coverage": 18,
                  "distribution": 13, "segmentation": 12, "detail_table": 7, "kpi": 13,
                  "outlier": 14}.get(kind, 8)
    quality = round(15 * max(0, min(100, quality_score)) / 100)
    field_completeness = [field.completeness_pct for field in [*dimensions, *measures, *dates]
                          if field.completeness_pct is not None]
    if field_completeness:
        quality = round((quality + 15 * min(field_completeness) / 100) / 2)

    cardinality = 10
    for field in dimensions:
        count = field.distinct_count
        if count is None:
            cardinality -= 2
        elif count <= 1:
            cardinality -= 10
        elif count <= 30:
            cardinality += 0
        elif count <= 100:
            cardinality -= 2
        elif count <= 500:
            cardinality -= 5
        else:
            cardinality -= 8
    cardinality = max(0, min(10, cardinality))
    confidence_points = {"high": 9, "medium": 6, "low": 2}[confidence]
    business_signal = min(10, sum(3 for strength in strengths if strength >= 2)
                          + sum(2 for field in dimensions if _dimension_strength(field.name) >= 2))

    warning_penalty = min(12, len(warnings) * 3)
    weak_semantics = sum(4 for field in dimensions if _dimension_strength(field.name) == 0)
    weak_semantics += sum(3 for field, strength in zip(measures, strengths, strict=False)
                          if strength == 0 or _measure_strength(field.name, field.format, field.table) == 0)
    redundancy_penalty = 0  # Applied after semantic duplicate groups are ranked.
    return max(0, min(100, semantic_fit + importance + usefulness + quality + cardinality
                      + business_signal + confidence_points - warning_penalty
                      - min(12, weak_semantics) - redundancy_penalty))


def _semantic_key(item: Insight) -> tuple:
    """Ignore source sheet and generated ID so equivalent analyses collapse across tables."""
    def refs(values):
        return tuple(sorted(fold(value.get("column", "")) for value in values))
    return item.type, refs(item.dimensions), refs(item.measures), refs(item.dates)


def _deduplicate(items: list[Insight]) -> tuple[list[Insight], int]:
    grouped: dict[tuple, list[Insight]] = {}
    for item in items:
        grouped.setdefault(_semantic_key(item), []).append(item)
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    result = []
    for equivalent in grouped.values():
        winner = max(equivalent, key=lambda item: (item.relevance_score, -priority_rank[item.priority],
                                                    item.confidence == "high"))
        # Repeated source tabs signal overlap. Keep the best source, but reflect that redundancy in its final score.
        redundancy_penalty = min(10, 2 * (len(equivalent) - 1))
        if redundancy_penalty:
            new_score = max(0, winner.relevance_score - redundancy_penalty)
            adjusted_priority = _priority(new_score, winner.confidence, winner.warnings)
            if priority_rank[adjusted_priority] < priority_rank[winner.priority]:
                adjusted_priority = winner.priority
            winner = winner.model_copy(update={
                "relevance_score": new_score, "priority": adjusted_priority,
                "reason": (winner.reason + f" Uma análise semanticamente equivalente apareceu em {len(equivalent)} abas; "
                           f"foi mantida a origem mais relevante e aplicada penalidade de redundância ({redundancy_penalty} pontos)."),
            })
        result.append(winner)
    result.sort(key=lambda item: (-item.relevance_score, priority_rank[item.priority], item.type, item.title, item.id))
    return result, len(items) - len(result)


def _deduplicate_kpis(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple, dict[str, Any]] = {}
    for item in items:
        calculation = item.get("calculation_candidate") or {}
        if calculation:
            key = ("calculation", fold(calculation.get("numerator", "")),
                   fold(calculation.get("denominator", "")))
        else:
            key = ("measure", fold(item.get("name", "")))
        current = best.get(key)
        if current is None or (item.get("relevance_score", 0), item.get("confidence") == "high") > \
                (current.get("relevance_score", 0), current.get("confidence") == "high"):
            best[key] = item
    return sorted(best.values(), key=lambda item: (-item.get("relevance_score", 0),
                                                    item.get("priority") != "high", item.get("name", "")))


def _slug(*values: str) -> str:
    normalized = fold("-".join(values))
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:100] or "insight"


def _insight(kind: str, title: str, question: str, *, dimensions=(), measures=(), dates=(), visual: str,
             confidence: str, priority: str, evidence: list[str], reason: str, warnings=(),
             relevance_score: int = 0) -> Insight:
    return Insight(
        id=_slug(kind, title), type=kind, title=title, business_question=question,
        dimensions=[_ref(field) for field in dimensions], measures=[_ref(field) for field in measures],
        dates=[_ref(field) for field in dates], visual=visual, confidence=confidence,
        priority=_priority(relevance_score, confidence, warnings, dimensions, measures),
        relevance_score=relevance_score, evidence=evidence, reason=reason, warnings=list(warnings),
    )


def _business_question(dimension_name: str, measure_name: str) -> tuple[str, str, str]:
    normalized = fold(dimension_name)
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
                suffix = parts[1].strip() if len(parts) > 1 and fold(parts[0]) == "empresa" else ""
                entity = "empresas" + (f" {suffix}" if suffix else "")
                return "comparison", "barras/colunas", f"Quais {entity} concentram maior {measure}?"
            return "comparison", "barras/colunas", f"Quais {plural} concentram maior {measure}?"
    if "status" in normalized:
        return "comparison", "barras/colunas", f"Como o {measure} varia por {dimension_name.lower()}?"
    return "ranking", "barras horizontais", f"Quais categorias de {dimension_name.lower()} apresentam maior {measure}?"


def _quality_warnings(fields, analysis: FileAnalysis | None) -> list[str]:
    """Return only structural quality flags for the fields used by this candidate."""
    warnings: list[str] = []
    if analysis is None:
        return warnings
    tables = {table.name: table for table in analysis.tables}
    for field in fields:
        table = tables.get(field.table)
        column = next((item for item in table.column_analyses if item.name == field.name), None) if table else None
        if column is None:
            continue
        if column.completeness_pct < 80:
            warnings.append(f"Preenchimento baixo em {field.name}.")
        if column.inconsistent_values:
            warnings.append(f"Valores inconsistentes detectados em {field.name}.")
        if column.invalid_dates:
            warnings.append(f"Datas inválidas detectadas em {field.name}.")
        if table and table.status not in {"completed", "completed_empty"}:
            warnings.append(f"Aba {table.name} teve análise {table.status}.")
    return list(dict.fromkeys(warnings))


def _calculation_candidates(model: SemanticModel) -> list[CalculationCandidate]:
    candidates: list[CalculationCandidate] = []
    for table in model.tables:
        named = {fold(field.name): field for field in table.measures}
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
            candidate_warnings = _quality_warnings([measure], analysis)
            score = _relevance_score("kpi", [], [measure], [], confidence, candidate_warnings, quality_score)
            priority = _priority(score, confidence, candidate_warnings, (), [measure])
            kpis.append({
                "name": measure.name, "table": table.name, "measure": _ref(measure),
                "confidence": confidence, "relevance_score": score, "priority": priority,
                "evidence": [*measure.evidence, "A coluna foi classificada como medida; nenhum valor individual é incluído."],
                "reason": measure.reason,
            })
            insights.append(_insight(
                "kpi", measure.name, f"Qual é o valor de {measure.name}?", measures=[measure], visual="card/KPI",
                confidence=confidence, priority=_priority(score), relevance_score=score, evidence=measure.evidence,
                reason=(f"{measure.name} foi reconhecida como medida ({measure.format or 'formato numérico'}), "
                        f"com confiança {confidence} e preenchimento "
                        f"{measure.completeness_pct if measure.completeness_pct is not None else 'não informado'}%. "
                        "O score também considera a relevância semântica do nome e a qualidade geral dos dados."),
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
                    anomaly_fields = [measure] if measure else []
                    warnings.extend(_quality_warnings(anomaly_fields, analysis))
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
                pair_warnings = _quality_warnings([dimension, measure], analysis)
                score = _relevance_score(kind, [dimension], [measure], [], confidence, pair_warnings, quality_score)
                metric = measure.name
                title = f"{metric} por {dimension.name}"
                if kind == "ranking" and dimension.distinct_count is not None and dimension.distinct_count > 100:
                    score = max(0, score - 8)
                evidence = [f"{dimension.name} foi identificada como dimensão categórica.",
                            f"{metric} foi identificada como medida ({measure.format or 'número'}).",
                            f"Confiança semântica: {confidence}; preenchimento observado: dimensão {dimension.completeness_pct if dimension.completeness_pct is not None else 'não informado'}%, medida {measure.completeness_pct if measure.completeness_pct is not None else 'não informado'}%."]
                insights.append(_insight(
                    kind, title, question, dimensions=[dimension], measures=[measure], visual=visual,
                    confidence=confidence, priority=_priority(score, confidence, pair_warnings, [dimension], [measure]),
                    relevance_score=score, evidence=evidence,
                    reason=(f"Combinação gerada porque {dimension.name} é dimensão e {metric} é medida na mesma aba. "
                            "O nome da medida e da dimensão contribui apenas como evidência heurística, não como confirmação do contexto empresarial."),
                    warnings=pair_warnings,
                ))

        # A bounded two-dimension segmentation helps produce richer questions without a Cartesian explosion.
        bounded_dimensions = table.dimensions[:8]
        for first_index, first_dimension in enumerate(bounded_dimensions):
            for second_dimension in bounded_dimensions[first_index + 1:]:
                for measure in table.measures[:5]:
                    confidence = _confidence(first_dimension.confidence, second_dimension.confidence, measure.confidence)
                    dims = [first_dimension, second_dimension]
                    pair_warnings = _quality_warnings([*dims, measure], analysis)
                    score = _relevance_score("segmentation", dims, [measure], [], confidence, pair_warnings, quality_score)
                    title = f"{measure.name} por {first_dimension.name} e {second_dimension.name}"
                    insights.append(_insight(
                        "segmentation", title,
                        f"Como {measure.name.lower()} varia por {first_dimension.name.lower()} e {second_dimension.name.lower()}?",
                        dimensions=dims, measures=[measure], visual="barras agrupadas",
                        confidence=confidence, priority=_priority(score, confidence, pair_warnings, dims, [measure]),
                        relevance_score=score, warnings=pair_warnings,
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
                normalized_date_name = fold(date.name)
                if any(word in normalized_date_name for word in ("inicio", "fim", "admissao", "vencimento", "vigencia")):
                    warning_list.append("Confirme se a data de vigência representa o evento temporal que se deseja acompanhar.")
                warning_list.extend(_quality_warnings([date, measure], analysis))
                score = _relevance_score("trend", [], [measure], [date], confidence, warning_list, quality_score)
                insights.append(_insight(
                    "trend", title, f"Como {measure.name.lower()} evolui ao longo de {date.name.lower()}?",
                    measures=[measure], dates=[date], visual="linha", confidence=confidence,
                    priority=_priority(score, confidence, warning_list, (), [measure]), relevance_score=score,
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
            detail_warnings = _quality_warnings([identifier, measure], analysis)
            score = _relevance_score("detail_table", [identifier], [measure], [], confidence, detail_warnings, quality_score)
            insights.append(_insight(
                "detail_table", f"Detalhamento de {measure.name} por {identifier.name}",
                f"Quais registros de {identifier.name} devem ser revisados por {measure.name}?",
                dimensions=[identifier], measures=[measure], visual="tabela detalhada", confidence=confidence,
                priority=_priority(score, confidence, detail_warnings, [identifier], [measure]),
                relevance_score=score, warnings=detail_warnings,
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
        calculation_priority = _priority(score, calculation.confidence, calculation_warnings, (),
                                         [field for field in (numerator, denominator) if field])
        insights.append(_insight(
            "coverage", title, f"Qual é a proporção de {calculation.numerator} sobre {calculation.denominator}?",
            measures=[{"table": calculation.table, "name": calculation.numerator},
                      {"table": calculation.table, "name": calculation.denominator}],
            visual="card/KPI", confidence=calculation.confidence,
            priority=calculation_priority, relevance_score=score, evidence=calculation.evidence,
            reason="Candidata de razão baseada em medidas complementares; nenhuma fórmula foi executada nem DAX foi criado.",
            warnings=calculation_warnings,
        ))
        kpis.append({
            "name": calculation.name, "table": calculation.table,
            "calculation_candidate": calculation.model_dump(mode="json"),
            "confidence": calculation.confidence, "relevance_score": score, "priority": calculation_priority,
            "reason": calculation.reason,
        })

    # Deduplicate equivalent semantic analyses across tabs before selecting final candidates.
    candidate_count = len(insights)
    insights, duplicates_removed = _deduplicate(insights)
    insights = insights[:60]
    warnings = list(model.semantic_warnings)
    if not insights:
        warnings.append("Não foram encontradas combinações suficientes de dimensão, medida ou data para sugerir análises.")
    # Keep useful measure candidates for inspection, while preventing weak fields from filling the KPI list.
    kpis = _deduplicate_kpis([item for item in kpis if item["relevance_score"] >= 44])
    return InsightsBlock(generated=True, items=insights, warnings=list(dict.fromkeys(warnings)),
                         candidate_count=candidate_count, deduplicated_count=candidate_count - duplicates_removed,
                         duplicates_removed=duplicates_removed, top_limit=12), KpisBlock(
        suggested=kpis[:40], calculation_candidates=calculations,
    )
