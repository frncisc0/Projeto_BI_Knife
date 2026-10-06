from __future__ import annotations

from app.models.discovery_models import DashboardBlueprint, InsightsBlock, KpisBlock, SemanticModel


def build_dashboard_blueprint(semantic: SemanticModel, insights: InsightsBlock, kpis: KpisBlock) -> DashboardBlueprint:
    # InsightsBlock already contains the deduplicated, ranked final pool.
    eligible = [item for item in insights.items if item.priority in {"high", "medium"}]
    eligible.sort(key=lambda item: (-item.relevance_score, item.id))
    executive = eligible[:5]
    selected_ids = {item.id for item in executive}
    pages = []
    if executive:
        pages.append({
            "name": "Visão Executiva", "purpose": "Acompanhar indicadores e oportunidades prioritárias sustentadas pelos metadados.",
            "visuals": [item.model_dump(mode="json") for item in executive],
        })
    for table in semantic.tables:
        table_insights = [item for item in eligible if any(ref.get("table") == table.name
                                                           for ref in [*item.dimensions, *item.measures, *item.dates])]
        if table_insights:
            pages.append({
                "name": f"Análise — {table.name}",
                "purpose": f"Explorar sugestões associadas à aba {table.name}.",
                "visuals": [item.model_dump(mode="json") for item in table_insights[:5]],
            })
    filters = []
    selected_dimension_keys = {(ref.get("table"), ref.get("column")) for item in executive for ref in item.dimensions}
    for field in semantic.dimensions:
        if (field.table, field.name) in selected_dimension_keys and field.confidence != "low" and len(filters) < 8:
            filters.append({"table": field.table, "column": field.name})
    warnings = list(semantic.semantic_warnings)
    if not pages:
        warnings.append("Nenhuma página foi proposta porque não há insights com prioridade média ou alta.")
    warnings.append("Blueprint é uma especificação inicial; valide filtros, agregações e regras de negócio antes de construir visuais.")
    return DashboardBlueprint(
        title="Dashboard Blueprint — BI Swiss Knife",
        objective="Organizar KPIs e perguntas analíticas sustentadas pelas evidências do AnalysisResult.",
        recommended_pages=pages,
        kpis=sorted((item for item in kpis.suggested if item.get("priority") in {"high", "medium"}),
                    key=lambda item: (-item.get("relevance_score", 0), item.get("name", "")))[:6],
        insights=[item.id for item in executive if item.id in selected_ids], filters=filters,
        dimensions=[{"table": item.table, "name": item.name, "confidence": item.confidence} for item in semantic.dimensions],
        measures=[{"table": item.table, "name": item.name, "format": item.format or "number",
                   "confidence": item.confidence} for item in semantic.measures],
        warnings=list(dict.fromkeys(warnings)),
    )
