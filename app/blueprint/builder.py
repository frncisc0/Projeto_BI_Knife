from __future__ import annotations

from app.models.discovery_models import DashboardBlueprint, InsightsBlock, KpisBlock, SemanticModel


def build_dashboard_blueprint(semantic: SemanticModel, insights: InsightsBlock, kpis: KpisBlock) -> DashboardBlueprint:
    eligible = [item for item in insights.items if item.priority in {"high", "medium"}]
    eligible.sort(key=lambda item: (-item.relevance_score, item.id))
    high = [item for item in eligible if item.priority == "high"]
    executive = high[:8] + [item for item in eligible if item.priority == "medium"][:4]
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
                "visuals": [item.model_dump(mode="json") for item in table_insights[:8]],
            })
    filters = []
    for field in semantic.dimensions:
        if field.confidence != "low" and len(filters) < 12:
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
                    key=lambda item: (-item.get("relevance_score", 0), item.get("name", "")))[:8],
        insights=[item.id for item in executive], filters=filters,
        dimensions=[{"table": item.table, "name": item.name, "confidence": item.confidence} for item in semantic.dimensions],
        measures=[{"table": item.table, "name": item.name, "format": item.format or "number",
                   "confidence": item.confidence} for item in semantic.measures],
        warnings=list(dict.fromkeys(warnings)),
    )
