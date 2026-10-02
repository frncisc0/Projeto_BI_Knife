import pandas as pd

from app.models.analysis_models import RelationshipCandidate, TableAnalysis


def suggest_relationships(frames: dict[str, pd.DataFrame], tables: list[TableAnalysis]) -> list[RelationshipCandidate]:
    candidates: list[RelationshipCandidate] = []
    names = list(frames)
    table_by_name = {table.name: table for table in tables}
    for source_name in names:
        for target_name in names:
            if source_name == target_name:
                continue
            source = frames[source_name]
            target = frames[target_name]
            source_columns = {str(c).strip().casefold(): c for c in source.columns}
            target_info = {str(c).strip().casefold(): c for c in target.columns}
            for normalized, source_col in source_columns.items():
                if normalized not in target_info or not normalized:
                    continue
                target_col = target_info[normalized]
                source_values = source[source_col].dropna()
                target_values = target[target_col].dropna()
                if source_values.empty or target_values.empty:
                    continue
                target_unique = target_values.nunique() == len(target_values)
                if not target_unique:
                    continue
                coverage = source_values.isin(target_values).mean() * 100
                if coverage >= 70:
                    candidates.append(RelationshipCandidate(
                        source_table=source_name, source_column=str(source_col),
                        target_table=target_name, target_column=str(target_col),
                        coverage_pct=round(float(coverage), 1),
                        confidence="high" if coverage >= 95 else "medium",
                        reason="Colunas com o mesmo nome; o destino é único e cobre os valores da origem.",
                    ))
    return candidates
