import math
from typing import Any

import pandas as pd


def _clean(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def statistics(series: pd.Series, inferred_type: str) -> dict[str, Any]:
    values = series.dropna()
    if inferred_type in {"inteiro", "decimal", "numérico (texto)"} and not values.empty:
        numeric = pd.to_numeric(values.astype(str).str.replace(",", ".", regex=False), errors="coerce").dropna()
        if numeric.empty:
            return {}
        return {key: _clean(val) for key, val in {
            "min": numeric.min(), "max": numeric.max(), "mean": numeric.mean(), "median": numeric.median(),
            "std_dev": numeric.std(),
        }.items()}
    if "data/hora" in inferred_type and not values.empty:
        dates = pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=True).dropna()
        if not dates.empty:
            return {"min": _clean(dates.min()), "max": _clean(dates.max())}
    if not values.empty:
        lengths = values.astype(str).str.len()
        return {"min_length": int(lengths.min()), "max_length": int(lengths.max())}
    return {}
