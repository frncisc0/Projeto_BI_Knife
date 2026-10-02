import re
from difflib import SequenceMatcher

import pandas as pd

from app.core.config import get_settings
from app.models.analysis_models import RelationshipCandidate, TableAnalysis


def _normalized_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _name_similarity(left: str, right: str) -> float:
    left_norm, right_norm = _normalized_name(left), _normalized_name(right)
    if left_norm == right_norm:
        return 1.0
    left_tokens, right_tokens = set(re.findall(r"[a-z0-9]+", left.casefold())), set(re.findall(r"[a-z0-9]+", right.casefold()))
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return max(SequenceMatcher(None, left_norm, right_norm).ratio(), overlap)


def _compatible_types(left: pd.Series, right: pd.Series) -> bool:
    left_numeric = pd.api.types.is_numeric_dtype(left.dtype)
    right_numeric = pd.api.types.is_numeric_dtype(right.dtype)
    left_date = pd.api.types.is_datetime64_any_dtype(left.dtype)
    right_date = pd.api.types.is_datetime64_any_dtype(right.dtype)
    return left_numeric == right_numeric and left_date == right_date


def suggest_relationships(frames: dict[str, pd.DataFrame], tables: list[TableAnalysis]) -> list[RelationshipCandidate]:
    candidates: list[RelationshipCandidate] = []
    settings = get_settings()
    table_sampling = {table.name: table.sampled for table in tables}
    table_sampling.update({name: bool(frame.attrs.get("sampled", False)) for name, frame in frames.items()})
    limited_frames = dict(list(frames.items())[:settings.max_tables_to_analyze])
    for parent_name, parent in limited_frames.items():
        for child_name, child in limited_frames.items():
            if parent_name == child_name:
                continue
            for parent_col in parent.columns:
                parent_values = parent[parent_col].dropna()
                if parent_values.empty or parent_values.nunique() != len(parent_values):
                    continue
                for child_col in child.columns:
                    child_complete = child[child_col].dropna()
                    if (parent_values.nunique() == len(parent_values)
                            and child_complete.nunique() == len(child_complete)
                            and parent_name > child_name):
                        continue
                    similarity = _name_similarity(str(parent_col), str(child_col))
                    if similarity < 0.72 or not _compatible_types(parent[parent_col], child[child_col]):
                        continue
                    child_values = child[child_col].dropna()
                    if child_values.empty:
                        continue
                    sampled_values = len(child_values) > settings.max_relationship_value_rows
                    if sampled_values:
                        child_values = child_values.head(settings.max_relationship_value_rows)
                    sampled_tables = table_sampling.get(parent_name, False) or table_sampling.get(child_name, False)
                    matched_mask = child_values.isin(parent_values)
                    coverage = float(matched_mask.mean() * 100)
                    matched_count = int(matched_mask.sum())
                    if coverage < 70:
                        continue
                    child_repeats = child_values.nunique() < len(child_values)
                    sampled = sampled_tables or sampled_values
                    confidence = "high" if coverage >= 95 and similarity >= 0.9 and not sampled else "medium"
                    cardinality = "1:N" if child_repeats else "1:1"
                    sample_note = " (amostra limitada)" if sampled else ""
                    candidates.append(RelationshipCandidate(
                        source_table=parent_name, source_column=str(parent_col),
                        target_table=child_name, target_column=str(child_col),
                        coverage_pct=round(coverage, 1), matched_values=matched_count,
                        unmatched_values=int((~matched_mask).sum()), cardinality=cardinality,
                        confidence=confidence,
                        reason=(f"Possível relacionamento: destino único, similaridade de nomes {similarity:.0%}, tipos compatíveis; "
                                f"{coverage:.1f}% de correspondência{sample_note} nos valores avaliados."),
                    ))
                    if len(candidates) >= settings.max_relationship_candidates:
                        return candidates
    # Keep the strongest directional candidate for each column pair.
    unique: dict[tuple[str, str, str, str], RelationshipCandidate] = {}
    for candidate in candidates:
        key = (candidate.source_table, candidate.source_column, candidate.target_table, candidate.target_column)
        if key not in unique or candidate.coverage_pct > unique[key].coverage_pct:
            unique[key] = candidate
    return list(unique.values())
