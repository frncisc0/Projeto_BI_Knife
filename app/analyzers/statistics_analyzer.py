import math
from typing import Any

import pandas as pd
from app.core.config import get_settings


def numeric_values(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip().str.replace(r"[^\d,.-]", "", regex=True)
    both_separators = text.str.contains(",", regex=False) & text.str.contains(".", regex=False)
    comma_is_decimal = both_separators & (text.str.rfind(",") > text.str.rfind("."))
    text.loc[comma_is_decimal] = text.loc[comma_is_decimal].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    comma_is_thousands = both_separators & ~comma_is_decimal
    text.loc[comma_is_thousands] = text.loc[comma_is_thousands].str.replace(",", "", regex=False)
    only_comma = text.str.contains(",", regex=False) & ~both_separators
    text.loc[only_comma] = text.loc[only_comma].str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce")


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
    if inferred_type in {"inteiro", "decimal", "identificador", "moeda", "percentual", "numérico (texto)"} and not values.empty:
        numeric = numeric_values(values).dropna()
        if numeric.empty:
            return {}
        result = {key: _clean(val) for key, val in {
            "min": numeric.min(), "max": numeric.max(), "mean": numeric.mean(), "median": numeric.median(),
            "std_dev": numeric.std(), "q1": numeric.quantile(0.25), "q3": numeric.quantile(0.75),
            "zero_count": int((numeric == 0).sum()), "negative_count": int((numeric < 0).sum()),
        }.items()}
        for percentile in get_settings().percentiles:
            bounded = min(100.0, max(0.0, percentile))
            result[f"p{bounded:g}"] = _clean(numeric.quantile(bounded / 100))
        return result
    if "data" in inferred_type and not values.empty:
        dates = pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=True).dropna()
        if not dates.empty:
            years = dates.dt.year.value_counts().sort_index()
            months = dates.dt.to_period("M").value_counts().sort_index()
            return {"min": _clean(dates.min()), "max": _clean(dates.max()), "periods": int(months.size),
                    "by_year": {str(key): int(value) for key, value in years.items()},
                    "by_month": {str(key): int(value) for key, value in months.items()},
                    "apparent_month_gaps": _date_gaps(dates)}
    if not values.empty:
        frequencies = values.astype(str).value_counts()
        return {"category_count": int(frequencies.size), "most_frequent_count": int(frequencies.iloc[0]),
                "most_frequent_pct": round(float(frequencies.iloc[0] / len(values) * 100), 2),
                "top_category_concentration_pct": round(float(frequencies.head(3).sum() / len(values) * 100), 2)}
    return {}


def _date_gaps(dates: pd.Series) -> int:
    periods = dates.dt.to_period("M").drop_duplicates().sort_values()
    return max(0, len(pd.period_range(periods.iloc[0], periods.iloc[-1], freq="M")) - len(periods)) if not periods.empty else 0
