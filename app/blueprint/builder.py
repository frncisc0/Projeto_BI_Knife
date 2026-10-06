from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from app.models.discovery_models import DashboardBlueprint, HumanCenteredSummary, InsightsBlock, KpisBlock, SemanticModel


_DOMAIN_LABELS = {
    "trabalhista": "relações trabalhistas",
    "financeiro": "indicadores financeiros",
    "contratos": "contratos e fornecedores",
    "recursos humanos": "gestão de pessoas",
}


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _topic(item) -> tuple[str, str]:
    if item.dates:
        return "temporal", "Evolução ao longo do tempo"
    if item.dimensions:
        name = item.dimensions[0].get("column", "")
        if name:
            return f"dimension:{_norm(name)}", f"Análise por {name}"
    if item.measures:
        name = item.measures[0].get("column", "")
        if name:
            return f"measure:{_norm(name)}", f"Indicadores de {name}"
    return f"type:{item.type}", "Análises complementares"


def _dedupe_final(items):
    best = {}
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    for item in items:
        key = (item.type,
               tuple(sorted(_norm(ref.get("column", "")) for ref in item.dimensions)),
               tuple(sorted(_norm(ref.get("column", "")) for ref in item.measures)),
               tuple(sorted(_norm(ref.get("column", "")) for ref in item.dates)))
        current = best.get(key)
        if current is None or (item.relevance_score, -priority_rank[item.priority]) > \
                (current.relevance_score, -priority_rank[current.priority]):
            best[key] = item
    return sorted(best.values(), key=lambda item: (-item.relevance_score, item.id))


def build_dashboard_blueprint(semantic: SemanticModel, insights: InsightsBlock, kpis: KpisBlock,
                              human_summary: HumanCenteredSummary | None = None) -> DashboardBlueprint:
    """Arrange the already scored and deduplicated insights into a compact dashboard plan."""
    eligible = [item for item in _dedupe_final(insights.items) if item.priority in {"high", "medium"}]
    eligible.sort(key=lambda item: (-item.relevance_score, item.id))
    if human_summary is not None:
        summarized_ids = {item.get("insight_id") for item in human_summary.key_findings}
        executive = [item for item in eligible if item.id in summarized_ids][:5]
    else:
        executive = eligible[:5]
    kpi_candidates = sorted(
        (item for item in kpis.suggested if item.get("priority") in {"high", "medium"}),
        key=lambda item: (-item.get("relevance_score", 0), item.get("name", "")),
    )[:6]
    create_executive = bool(executive) and (len(executive) >= 2 or any(item.priority == "high" for item in executive)
                                            or bool(kpi_candidates))
    if not create_executive:
        executive = []
    placed_ids = {item.id for item in executive}
    pages: list[dict] = []

    domains = [_DOMAIN_LABELS.get(domain, domain) for domain in semantic.business_domains]
    if domains:
        objective = "Acompanhar análises relacionadas a " + ", ".join(domains) + ", conforme os sinais encontrados nos nomes e papéis dos campos."
    else:
        objective = "Acompanhar indicadores e explorar as oportunidades analíticas sustentadas pelos dados."
    if create_executive:
        pages.append({
            "name": "Visão Geral",
            "purpose": "Apresentar os principais indicadores e perguntas analíticas em uma leitura inicial.",
            "visuals": [item.model_dump(mode="json") for item in executive],
            "kpis": [],
            "insight_ids": [item.id for item in executive],
            "rationale": "Reúne as análises finais de maior relevância, sem repetir gráficos em outras páginas.",
        })

    groups: dict[str, list] = defaultdict(list)
    group_labels: dict[str, str] = {}
    for item in eligible:
        if item.id in placed_ids:
            continue
        key, label = _topic(item)
        groups[key].append(item)
        group_labels[key] = label

    topical_count = 0
    for key, items in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        # A single medium-priority chart is not enough to justify a dedicated page.
        if len(items) < 2 and not any(item.priority == "high" for item in items):
            continue
        items.sort(key=lambda item: (-item.relevance_score, item.id))
        selected = items[:6]
        page_ids = [item.id for item in selected]
        if any(page_ids.count(item_id) > 1 for item_id in page_ids):
            continue
        placed_ids.update(page_ids)
        pages.append({
            "name": group_labels[key],
            "purpose": f"Explorar análises relacionadas a {group_labels[key].removeprefix('Análise por ').removeprefix('Indicadores de ')}.",
            "visuals": [item.model_dump(mode="json") for item in selected],
            "kpis": [],
            "insight_ids": page_ids,
            "rationale": f"Os insights foram agrupados pelo tema comum: {group_labels[key]}.",
        })
        topical_count += 1
        if topical_count >= 4:
            break

    if pages and pages[0]["name"] == "Visão Geral":
        pages[0]["kpis"] = kpi_candidates

    # Filters must be relevant to a selected insight, nontechnical, and reasonably sized.
    referenced_dimensions = {
        (ref.get("table"), ref.get("column"))
        for item in eligible[:24]
        for ref in item.dimensions
    }
    filters = []
    for field in semantic.dimensions:
        if (field.table, field.name) not in referenced_dimensions:
            continue
        if field.confidence == "low" or field.distinct_count is None or not 2 <= field.distinct_count <= 100:
            continue
        if set(_norm(field.name).split()) & {"id", "identifier", "codigo", "code", "chave", "matricula", "registro"}:
            continue
        filters.append({"table": field.table, "column": field.name})
        if len(filters) == 8:
            break

    interactions = []
    seen_relationships = set()
    for relation in semantic.relationships:
        if relation.get("confidence") != "high":
            continue
        relation_key = (relation.get("source_table"), relation.get("source_column"),
                        relation.get("target_table"), relation.get("target_column"))
        if relation_key in seen_relationships:
            continue
        seen_relationships.add(relation_key)
        interactions.append({
            "type": "cross_filter",
            "source": f"{relation.get('source_table')}.{relation.get('source_column')}",
            "target": f"{relation.get('target_table')}.{relation.get('target_column')}",
            "reason": relation.get("reason", "Relação de alta confiança identificada na análise."),
        })

    warnings = list(semantic.semantic_warnings)
    if not pages:
        warnings.append("Não há insights de prioridade alta ou média suficientes para recomendar páginas.")
    warnings.append("O plano é uma proposta baseada em evidências estruturais; valide medidas, filtros e regras de negócio antes de construir o dashboard.")
    rationale = [
        "A Visão Geral reúne até cinco insights e seis KPIs priorizados.",
        "Páginas temáticas só são criadas quando há um grupo coerente de insights ou uma análise de alta prioridade.",
        "Filtros vêm de dimensões usadas nas análises e com cardinalidade adequada; identificadores técnicos são excluídos.",
    ]
    dashboard_insights = [item_id for page in pages for item_id in page.get("insight_ids", [])]
    return DashboardBlueprint(
        title="Dashboard recomendado",
        objective=objective,
        recommended_pages=pages,
        kpis=kpi_candidates,
        insights=dashboard_insights,
        filters=filters,
        dimensions=[{"table": item.table, "name": item.name, "confidence": item.confidence} for item in semantic.dimensions],
        measures=[{"table": item.table, "name": item.name, "format": item.format or "number",
                   "confidence": item.confidence} for item in semantic.measures],
        warnings=list(dict.fromkeys(warnings)),
        audience="Equipe que acompanha os dados; um público de negócio mais específico não pode ser inferido com segurança.",
        design_rationale=rationale,
        interactions=interactions,
    )
