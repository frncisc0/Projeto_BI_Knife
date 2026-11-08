"""Single place for interpreting date text.

ISO values (YYYY-MM-DD, optionally with time) are always year-month-day.
Other textual dates follow the Brazilian day-first convention (dd/mm/aaaa).
Mixing both rules in one ``pd.to_datetime(..., dayfirst=True)`` call swaps
day and month of ISO dates whose day is <= 12, so each family is parsed
separately.

Values that parse to a year outside pandas' nanosecond range (for example a
code such as "00123", read as year 123) are treated as invalid dates instead
of aborting the analysis.
"""
import pandas as pd

_ISO_DATE = r"\d{4}-\d{1,2}-\d{1,2}(?:[T ].*)?"
_MIN_YEAR, _MAX_YEAR = 1678, 2261  # inside datetime64[ns] bounds


def _bounded(parsed: pd.Series) -> pd.Series:
    """Return ``parsed`` as datetime64[ns], with out-of-range values as NaT."""
    parsed = pd.to_datetime(parsed, errors="coerce")
    if parsed.empty:
        return parsed.astype("datetime64[ns]")
    in_range = parsed.dt.year.between(_MIN_YEAR, _MAX_YEAR)
    return parsed.where(in_range).astype("datetime64[ns]")


def parse_dates(values: pd.Series) -> pd.Series:
    """Return datetimes (NaT when invalid) aligned with ``values``."""
    result = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    if values.empty:
        return result
    if pd.api.types.is_datetime64_any_dtype(values.dtype):
        return _bounded(values)
    text = values.astype(str).str.strip()
    iso = text.str.fullmatch(_ISO_DATE).fillna(False).astype(bool)
    if iso.any():
        result.loc[iso] = _bounded(pd.to_datetime(text[iso], errors="coerce", format="ISO8601"))
    others = ~iso
    if others.any():
        non_text = values[others].map(lambda value: not isinstance(value, str)).astype(bool)
        native_idx = non_text[non_text].index
        if len(native_idx):
            result.loc[native_idx] = _bounded(pd.to_datetime(values.loc[native_idx], errors="coerce"))
        text_idx = non_text[~non_text].index
        if len(text_idx):
            result.loc[text_idx] = _bounded(
                pd.to_datetime(text.loc[text_idx], errors="coerce", format="mixed", dayfirst=True))
    return result
