from typing import Any

import pandas as pd

from app.analyzers.file_analyzer import read_tables
from app.analyzers.quality_analyzer import duplicate_row_count, inconsistent_value_count, invalid_date_count
from app.analyzers.relationship_analyzer import suggest_relationships
from app.analyzers.schema_analyzer import infer_type
from app.analyzers.statistics_analyzer import statistics
from app.core.config import get_settings
from app.models.analysis_models import ColumnAnalysis, FileAnalysis, TableAnalysis


def _safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def analyze_file(filename: str, file_type: str, content: bytes, csv_encoding: str | None = None) -> FileAnalysis:
    frames = read_tables(content, file_type, csv_encoding)
    tables: list[TableAnalysis] = []
    settings = get_settings()
    warnings: list[str] = []
    for table_name, frame in frames.items():
        frame.columns = [str(column).strip() or f"Coluna {index + 1}" for index, column in enumerate(frame.columns)]
        if frame.columns.duplicated().any():
            counts: dict[str, int] = {}
            columns = []
            for column in frame.columns:
                counts[column] = counts.get(column, 0) + 1
                columns.append(column if counts[column] == 1 else f"{column} ({counts[column]})")
            frame.columns = columns
        total_rows = len(frame)
        columns: list[ColumnAnalysis] = []
        for column_name in frame.columns:
            series = frame[column_name]
            null_count = int(series.isna().sum())
            distinct_count = int(series.nunique(dropna=True))
            inferred = infer_type(series)
            frequencies = series.dropna().astype(str).value_counts().head(settings.max_category_display)
            columns.append(ColumnAnalysis(
                name=str(column_name), inferred_type=inferred, null_count=null_count,
                null_pct=round(null_count / total_rows * 100, 2) if total_rows else 0,
                distinct_count=distinct_count,
                distinct_pct=round(distinct_count / total_rows * 100, 2) if total_rows else 0,
                duplicate_count=max(0, int(series.count()) - distinct_count),
                empty=series.isna().all() or (series.dtype == object and series.fillna("").astype(str).str.strip().eq("").all()),
                key_candidate=total_rows > 0 and null_count == 0 and distinct_count == total_rows,
                inconsistent_values=inconsistent_value_count(series, inferred),
                invalid_dates=invalid_date_count(series, inferred),
                statistics=statistics(series, inferred),
                top_values=[{"value": value, "count": int(count)} for value, count in frequencies.items()],
            ))
        if total_rows > 500_000:
            warnings.append(f"A tabela '{table_name}' contém muitas linhas; esta versão processa a tabela integralmente em memória.")
        preview = [{str(k): _safe(v) for k, v in row.items()} for row in frame.head(settings.max_rows_to_preview).to_dict(orient="records")]
        tables.append(TableAnalysis(name=table_name, rows=total_rows, columns=len(frame.columns),
                                    duplicate_rows=duplicate_row_count(frame), preview=preview, column_analyses=columns))
    relationships = suggest_relationships(frames, tables)
    return FileAnalysis(filename=filename, file_type=file_type, file_size_bytes=len(content), tables=tables,
                        relationships=relationships, warnings=warnings)
