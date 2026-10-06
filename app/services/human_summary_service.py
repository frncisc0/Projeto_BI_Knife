"""Plain-language summaries derived only from the completed analysis payload."""

from __future__ import annotations

import unicodedata
from typing import Any

from app.models.analysis_models import FileAnalysis
from app.models.discovery_models import DashboardBlueprint, HumanCenteredSummary, InsightsBlock, KpisBlock, SemanticModel


QUALITY_TEXT = {
    "Excelente": "Os dados apresentam qualidade excelente segundo as verificações realizadas.",
    "Boa": "Os dados apresentam boa qualidade geral, com alguns pontos que podem merecer revisão.",
    "Atenção": "A qualidade dos dados pede atenção em alguns aspectos antes de usá-los em análises.",
    "Baixa": "A qualidade dos dados é baixa em parte das verificações; revise os alertas antes de tirar conclusões.",
    "Crítica": "Foram encontrados problemas importantes de qualidade; revise os dados antes de usá-los para decisões.",
}

DOMAIN_TEXT = {
    "trabalhista": "relações e custos trabalhistas",
    "financeiro": "valores e indicadores financeiros",
    "contratos": "contratos e fornecedores",
    "recursos humanos": "pessoas e gestão de equipes",
}

TYPE_TEXT = {
    "ranking": "Ranking",
    "comparison": "Comparação",
    "trend": "Evolução",
    "kpi": "Indicador",
    "coverage": "Indicador derivado",
    "distribution": "Distribuição",
    "outlier": "Ponto fora do padrão",
    "correlation": "Relação entre indicadores",
    "segmentation": "Segmentação",
    "detail_table": "Detalhamento",
}

PRIORITY_TEXT = {
    "high": "Prioridade alta",
    "medium": "Prioridade média",
    "low": "Sugestão complementar",
}


def _norm(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _warning_text(message: str) -> str:
    normalized = _norm(message)
    if "date field confidence low" in normalized or "data suficientemente confiavel" in normalized:
        return "Não foi identificada uma coluna de data suficientemente confiável para algumas análises de evolução."
    if "type mismatch" in normalized or "inconsistent type" in normalized:
        return "Algumas colunas apresentam formatos diferentes. Confira esses campos antes de combinar os dados."
    if "amostr" in normalized or "sampled" in normalized or "sampling" in normalized:
        return "Parte dos resultados foi calculada sobre uma amostra dos registros. Considere isso ao interpretar os números."
    if "active content" in normalized or "conteudo potencialmente ativo" in normalized:
        return "O arquivo contém conteúdo ativo. Ele foi identificado, mas não foi executado."
    if "external relationship" in normalized or "relacoes externas" in normalized:
        return "O arquivo contém referências externas. Elas foram identificadas, mas não foram acessadas."
    if any(word in normalized for word in ("falha", "failed", "erro", "error", "skipped", "nao foi analisada")):
        return "Uma parte do arquivo não pôde ser analisada por completo. Consulte os detalhes técnicos para identificar a aba."
    if any(word in normalized for word in ("ausente", "nulo", "null", "preenchimento", "incomplete")):
        return "Algumas informações estão ausentes ou incompletas; confirme se isso é esperado para esses dados."
    if "anomalia" in normalized or "outlier" in normalized:
        return "Há valores que se afastam do padrão observado. Isso indica algo para revisar, não necessariamente um erro."
    return str(message).strip()


def _attention_points(analysis: FileAnalysis, semantic: SemanticModel, insights: InsightsBlock) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []

    def add(message: str, severity: str = "information", source: str = "analysis") -> None:
        if severity == "ok" or not message:
            return
        normalized_severity = severity if severity in {"critical", "attention", "information"} else "information"
        point = {"severity": normalized_severity, "message": _warning_text(message), "source": source}
        if not any(item["severity"] == point["severity"] and item["message"] == point["message"] for item in points):
            points.append(point)

    for table in analysis.tables:
        for alert in table.quality.alerts:
            message = str(alert.get("message", ""))
            table_name = table.name
            if message:
                add(f"{message} (aba: {table_name})", str(alert.get("severity", "information")), "quality")
    for table in analysis.tables:
        if table.status not in {"completed", "completed_empty"}:
            severity = "critical" if table.status in {"error", "failed"} else "attention"
            add(f"Aba '{table.name}' não foi analisada por completo (status: {table.status}).", severity, "analysis")
        if table.sampled:
            add(f"Aba '{table.name}' foi avaliada por amostragem.", "information", "analysis")
    security = analysis.security
    security_has_events = bool(security and (security.active_content_detected or security.external_relationships_detected))
    relevant_security_warnings = analysis.security_warnings if security_has_events else []
    for message in [*analysis.warnings, *relevant_security_warnings, *semantic.semantic_warnings, *insights.warnings]:
        normalized = _norm(message)
        severity = "critical" if any(word in normalized for word in ("falha critica", "critical failure")) else "attention"
        if "conteudo potencialmente ativo" in normalized or "external" in normalized or "externa" in normalized:
            severity = "information"
        add(message, severity, "security" if message in relevant_security_warnings else "analysis")
    return points[:20]


def _finding_explanation(item: Any) -> str:
    dimensions = [ref.get("column", "") for ref in item.dimensions if ref.get("column")]
    measures = [ref.get("column", "") for ref in item.measures if ref.get("column")]
    dates = [ref.get("column", "") for ref in item.dates if ref.get("column")]
    kind = item.type
    if kind in {"ranking", "comparison", "segmentation"} and dimensions and measures:
        return (f"Permite comparar {', '.join(measures)} entre {', '.join(dimensions)} e explorar "
                "quais grupos concentram os maiores valores.")
    if kind == "trend" and measures and dates:
        return f"Permite observar como {', '.join(measures)} varia ao longo de {', '.join(dates)}."
    if kind in {"kpi", "coverage"} and measures:
        return f"Pode resumir {', '.join(measures)} em um indicador; regras de cálculo ainda precisam ser confirmadas quando aplicável."
    if kind == "outlier" and measures:
        return f"Ajuda a revisar valores de {', '.join(measures)} que se afastam do padrão observado, sem afirmar que sejam erros."
    if kind == "detail_table" and dimensions and measures:
        return f"Permite consultar registros de {', '.join(dimensions)} relacionados a {', '.join(measures)}."
    return item.business_question


def _why_item(item: Any) -> str:
    parts = []
    dimensions = [ref.get("column", "") for ref in item.dimensions if ref.get("column")]
    measures = [ref.get("column", "") for ref in item.measures if ref.get("column")]
    dates = [ref.get("column", "") for ref in item.dates if ref.get("column")]
    if dimensions:
        parts.append(f"{', '.join(dimensions)} pode ser usado para agrupar os dados")
    if measures:
        parts.append(f"{', '.join(measures)} foi identificado como valor mensurável")
    if dates:
        parts.append(f"{', '.join(dates)} atende aos critérios existentes para avaliar evolução")
    if not parts:
        parts.append("o AnalysisResult contém evidência para este tipo de sugestão")
    if item.warnings:
        parts.append("os avisos associados devem ser revisados")
    return "A análise sugeriu isso porque " + " e ".join(parts) + "."


def build_human_summary(
    analysis: FileAnalysis,
    semantic: SemanticModel,
    insights: InsightsBlock,
    kpis: KpisBlock,
) -> HumanCenteredSummary:
    """Translate existing analysis blocks into a compact, evidence-linked user summary."""
    sheet_count = len(analysis.tables)
    column_count = sum(table.columns_analyzed or table.columns for table in analysis.tables)
    evaluated_rows = sum(table.rows_analyzed for table in analysis.tables)
    available_rows = sum(table.rows_available or table.rows for table in analysis.tables)
    sampled = any(table.sampled for table in analysis.tables)
    if sampled and available_rows > evaluated_rows:
        records_text = (f"{evaluated_rows:,} linhas avaliadas de aproximadamente {available_rows:,} disponíveis"
                       .replace(",", "."))
    else:
        records_text = f"{evaluated_rows:,} linhas avaliadas".replace(",", ".")
    executive = f"Analisamos {sheet_count} aba(s), {column_count} colunas e {records_text}."
    if analysis.status == "partial":
        executive += " Parte do arquivo não pôde ser processada por completo."

    quality = analysis.quality
    quality_summary = QUALITY_TEXT.get(quality.classification, "A qualidade foi avaliada pelas verificações disponíveis.")
    quality_summary += f" Resultado geral: {quality.score:.1f}/100."
    components = [
        {"name": "Completude", "value": quality.completeness_pct, "description": "Quanto dos campos analisados está preenchido."},
        {"name": "Consistência", "value": quality.consistency_pct, "description": "Se os valores seguem padrões compatíveis."},
        {"name": "Validade", "value": quality.validity_pct, "description": "Se os valores respeitam os formatos esperados."},
        {"name": "Unicidade", "value": quality.uniqueness_pct, "description": "Se há valores repetidos que podem afetar o uso dos campos ou registros."},
    ]
    if quality.integrity_assessed and quality.integrity_pct is not None:
        components.append({"name": "Integridade", "value": quality.integrity_pct,
                           "description": "Compatibilidade entre campos relacionados."})

    domains = [DOMAIN_TEXT.get(domain, domain) for domain in semantic.business_domains]
    what_was_found: list[str] = []
    if domains:
        what_was_found.append("Os nomes das abas e colunas indicam possíveis temas ligados a "
                              f"{', '.join(domains)}; essa classificação é uma pista semântica, não uma conclusão sobre o negócio.")
    what_was_found.append(
        f"Foram identificadas {len(semantic.dimensions)} dimensão(ões) para agrupar comparações, "
        f"{len(semantic.measures)} medida(s) que podem apoiar indicadores e {len(semantic.dates)} campo(s) de data."
    )
    supported_dates = sum(bool(field.temporal_support) for field in semantic.dates)
    if supported_dates:
        what_was_found.append(f"{supported_dates} campo(s) de data têm cobertura suficiente para sugerir análises de evolução.")
    elif semantic.dates:
        what_was_found.append("Há campos de data, mas nenhum atende aos critérios atuais para uma análise de evolução confiável.")
    if semantic.relationships:
        what_was_found.append(f"Também foram encontradas {len(semantic.relationships)} relação(ões) potencial(is) entre tabelas.")

    eligible = [item for item in insights.items if item.priority in {"high", "medium"}]
    findings = [{
        "id": item.id,
        "title": item.business_question or item.title,
        "description": _finding_explanation(item),
        "importance": PRIORITY_TEXT.get(item.priority, "Sugestão para explorar"),
        "type": TYPE_TEXT.get(item.type, "Análise"),
        "insight_id": item.id,
        "why": _why_item(item),
        "warnings": list(item.warnings),
    } for item in eligible[:6]]

    attention = _attention_points(analysis, semantic, insights)
    grouped: dict[str, dict[str, Any]] = {}
    for item in eligible[:12]:
        category = TYPE_TEXT.get(item.type, "Análises")
        entry = grouped.setdefault(category, {"category": category, "insight_ids": [], "questions": [], "suggestions": []})
        entry["insight_ids"].append(item.id)
        entry["questions"].append(item.business_question)
        entry["suggestions"].append({
            "insight_id": item.id,
            "question": item.business_question,
            "description": _finding_explanation(item),
            "why": _why_item(item),
        })
    opportunities = list(grouped.values())
    dashboard_summary = ("As análises e os indicadores priorizados podem ser organizados em uma proposta de dashboard."
                         if eligible else "Ainda não há evidência suficiente para recomendar um dashboard.")
    if not findings:
        executive += " Não foram encontradas análises com evidência suficiente para destacar como prioritárias."

    return HumanCenteredSummary(
        title="Resumo da análise", executive_summary=executive,
        data_quality_summary=quality_summary, quality_components=components,
        what_was_found=what_was_found, key_findings=findings,
        attention_points=attention, analysis_opportunities=opportunities,
        dashboard_summary=dashboard_summary, technical_details_available=True,
    )


def finalize_dashboard_summary(summary: HumanCenteredSummary, blueprint: DashboardBlueprint) -> HumanCenteredSummary:
    """Attach the Architect result after the human-facing summary has selected evidenced findings."""
    if blueprint.recommended_pages:
        text = (f"O dashboard pode ser organizado em {len(blueprint.recommended_pages)} página(s), "
                f"com {len(blueprint.kpis)} indicador(es) priorizado(s).")
    else:
        text = "Ainda não há evidência suficiente para recomendar páginas de dashboard com segurança."
    return summary.model_copy(update={"dashboard_summary": text})
