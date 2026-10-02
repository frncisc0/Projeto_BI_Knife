import pandas as pd


def duplicate_row_count(frame: pd.DataFrame) -> int:
    return int(frame.duplicated().sum())


def invalid_date_count(series: pd.Series, inferred_type: str) -> int:
    if "data/hora" not in inferred_type:
        return 0
    values = series.dropna()
    if values.empty:
        return 0
    return int(pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=True).isna().sum())


def inconsistent_value_count(series: pd.Series, inferred_type: str) -> int:
    values = series.dropna()
    if values.empty:
        return 0
    if "numérico" in inferred_type:
        parsed = pd.to_numeric(values.astype(str).str.replace(",", ".", regex=False), errors="coerce")
        return int(parsed.isna().sum())
    if "data/hora" in inferred_type:
        return invalid_date_count(series, inferred_type)
    return 0
