import math
from typing import Any

import pandas as pd

from app.analyzers.date_parsing import parse_dates
from app.core.config import get_settings


# A cell is numeric only when, apart from an optional currency symbol, sign,
# percent sign and accounting parentheses, it contains digits and separators.
# Letters or other punctuation (P12, AB-1001, 10/01/2024, 12345-6) mean the
# value is a code or a date, never a number.
_NUMERIC_PATTERN = (
    r"\(?\s*[-+]?\s*(?:R\$|US\$|\$|€|£)?\s*[-+]?\s*"
    r"(?:\d{1,3}(?:[.,\s]\d{3})+|\d+)(?:[.,]\d+)?\s*%?\s*\)?"
)
_BR_THOUSANDS_ONLY = r"[-+]?\d{1,3}(?:\.\d{3})+"


def numeric_values(series: pd.Series) -> pd.Series:
    raw = series.astype(str).str.strip()
    valid = raw.str.fullmatch(_NUMERIC_PATTERN, case=False)
    text = raw.str.replace(r"[^\d,.-]", "", regex=True)
    text = text.where(valid.fillna(False), "")
    both_separators = text.str.contains(",", regex=False) & text.str.contains(".", regex=False)
    comma_is_decimal = both_separators & (text.str.rfind(",") > text.str.rfind("."))
    # Column-level locale evidence: Brazilian currency, decimal comma or a
    # repeated dot ("1.234.567") mean dots in this column are thousands.
    brazilian = bool(
        raw.str.contains("R$", regex=False).any()
        or comma_is_decimal.any()
        or text.str.fullmatch(r"[-+]?\d+,\d{1,2}").any()
        or text.str.count(r"\.").gt(1).any()
    )
    text.loc[comma_is_decimal] = text.loc[comma_is_decimal].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    comma_is_thousands = both_separators & ~comma_is_decimal
    text.loc[comma_is_thousands] = text.loc[comma_is_thousands].str.replace(",", "", regex=False)
    only_comma = text.str.contains(",", regex=False) & ~both_separators
    text.loc[only_comma] = text.loc[only_comma].str.replace(",", ".", regex=False)
    if brazilian:
        thousands_only = text.str.fullmatch(_BR_THOUSANDS_ONLY) & ~both_separators & ~only_comma
        text.loc[thousands_only] = text.loc[thousands_only].str.replace(".", "", regex=False)
    negative_parentheses = raw.str.match(r"^\(.*\)$") & valid.fillna(False)
    numbers = pd.to_numeric(text.replace("", None), errors="coerce")
    return numbers.where(~negative_parentheses, -numbers.abs())


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
        dates = parse_dates(values).dropna()
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
