import pandas as pd

from app.analyzers.date_parsing import parse_dates
from app.core.config import get_settings
from app.models.analysis_models import Anomaly
from app.analyzers.statistics_analyzer import numeric_values


def duplicate_row_count(frame: pd.DataFrame) -> int:
    return int(frame.duplicated().sum())


def invalid_date_count(series: pd.Series, inferred_type: str) -> int:
    if "data" not in inferred_type:
        return 0
    values = series.dropna()
    if values.empty:
        return 0
    return int(parse_dates(values).isna().sum())


def inconsistent_value_count(series: pd.Series, inferred_type: str) -> int:
    values = series.dropna()
    if values.empty:
        return 0
    if inferred_type in {"inteiro", "decimal", "identificador", "moeda", "percentual", "numérico (texto)"}:
        parsed = numeric_values(values)
        return int(parsed.isna().sum())
    if "data" in inferred_type:
        return invalid_date_count(series, inferred_type)
    return 0


def null_band(null_pct: float) -> str:
    settings = get_settings()
    if null_pct == 0:
        return "sem valores ausentes"
    if null_pct <= settings.null_attention_threshold_pct:
        return "ausência baixa (limite configurado)"
    if null_pct <= settings.null_moderate_threshold_pct:
        return "ausência moderada (limite configurado)"
    return "ausência alta (limite configurado)" if null_pct > settings.null_critical_threshold_pct else "ausência moderada (limite configurado)"


def numeric_anomalies(series: pd.Series, inferred_type: str, column_name: str) -> list[Anomaly]:
    if inferred_type not in {"inteiro", "decimal", "numérico (texto)", "moeda", "percentual"}:
        return []
    values = numeric_values(series).dropna()
    if len(values) < 8:
        return []
    q1, q3 = values.quantile([0.25, 0.75])
    spread = q3 - q1
    if spread == 0:
        return []
    outliers = int(((values < q1 - 1.5 * spread) | (values > q3 + 1.5 * spread)).sum())
    if not outliers:
        return []
    return [Anomaly(column=column_name, method="IQR", count=outliers, severity="information",
                    description="Há valores fora da faixa de 1,5 × IQR. Isso pode ser legítimo e não significa necessariamente erro.")]
