import pandas as pd


def infer_type(series: pd.Series) -> str:
    values = series.dropna()
    if values.empty:
        return "vazio"
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "booleano"
    if pd.api.types.is_integer_dtype(dtype):
        return "inteiro"
    if pd.api.types.is_numeric_dtype(dtype):
        return "decimal"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "data/hora"
    text = values.astype(str).str.strip()
    numeric = pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce")
    if not numeric.empty and numeric.notna().mean() >= 0.8:
        return "numérico (texto)"
    parsed_dates = pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=True)
    if parsed_dates.notna().mean() >= 0.8:
        return "data/hora (texto)"
    return "categórico"
