"""Single place for interpreting date text.

ISO values (YYYY-MM-DD, optionally with time) are always year-month-day.
Other textual dates follow the Brazilian day-first convention (dd/mm/aaaa).
Mixing both rules in one ``pd.to_datetime(..., dayfirst=True)`` call swaps
day and month of ISO dates whose day is <= 12, so each family is parsed
separately.
"""
import pandas as pd

_ISO_DATE = r"\d{4}-\d{1,2}-\d{1,2}(?:[T ].*)?"


def parse_dates(values: pd.Series) -> pd.Series:
    """Return datetimes (NaT when invalid) aligned with ``values``."""
    if values.empty:
        return pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    if pd.api.types.is_datetime64_any_dtype(values.dtype):
        return values
    text = values.astype(str).str.strip()
    iso = text.str.fullmatch(_ISO_DATE).fillna(False)
    result = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    if iso.any():
        result.loc[iso] = pd.to_datetime(text[iso], errors="coerce", format="ISO8601")
    others = ~iso
    if others.any():
        non_text = values[others].map(lambda value: not isinstance(value, str))
        if non_text.any():
            idx = non_text[non_text].index
            result.loc[idx] = pd.to_datetime(values.loc[idx], errors="coerce")
        text_idx = non_text[~non_text].index
        if len(text_idx):
            result.loc[text_idx] = pd.to_datetime(text.loc[text_idx], errors="coerce", format="mixed", dayfirst=True)
    return result
