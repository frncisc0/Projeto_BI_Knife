"""Analysis use case: read a file and build its ``AnalysisReport``.

``analyze_file`` is an orchestrator of small, named steps:

1. read the tables (``read_tables``);
2. profile each table and each column (``_profile_table`` / ``_profile_column``);
3. hand CSV samples to the batch relationship matcher (``_collect_relationship_frames``);
4. suggest relationships and recompute quality with integrity (``_apply_relationship_quality``);
5. assemble settings, security notes and the final report.

The decomposition is behaviour-preserving: tests/characterization keeps the full
report byte-identical to the version before the refactoring.
"""
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any

import pandas as pd

from app.analyzers.file_analyzer import read_tables
from app.analyzers.keys import composite_keys, key_candidate_info
from app.analyzers.quality_analyzer import (
    duplicate_row_count,
    inconsistent_value_count,
    invalid_date_count,
    null_band,
    numeric_anomalies,
)
from app.analyzers.quality_score import quality_score
from app.analyzers.relationship_analyzer import suggest_relationships
from app.analyzers.schema_analyzer import (
    infer_type,
    physical_type,
    semantic_role,
    sensitivity_details,
    type_confidence,
    type_reason,
)
from app.analyzers.statistics_analyzer import statistics
from app.analyzers.table_kind import table_kind
from app.core.config import get_settings
from app.core.exceptions import AnalysisError
from app.models.analysis_models import (
    AnalysisReport,
    Anomaly,
    ColumnAnalysis,
    FileSecurityAnalysis,
    StatisticsAnalysis,
    TableAnalysis,
)
from app.security.file_validation import inspect_xlsx_package

ProgressCallback = Callable[[dict[str, Any]], None]
_TIMEOUT_MESSAGE = "A análise excedeu o tempo máximo configurado."


@dataclass
class _Totals:
    """Running totals across tables, used for the file-level quality score."""

    nulls: int = 0
    invalid: int = 0
    duplicates: int = 0
    rows: int = 0
    profiled_rows: int = 0
    profiled_columns: int = 0
    profiled_cells: int = 0


@dataclass
class _Context:
    """Per-call parameters shared by the steps."""

    file_type: str
    header_mode: str
    started: float
    settings: Any
    warnings: list[str] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    totals: _Totals = field(default_factory=_Totals)

    def check_timeout(self) -> None:
        if time.monotonic() - self.started > self.settings.analysis_timeout_seconds:
            raise AnalysisError(_TIMEOUT_MESSAGE)


def _cardinality(distinct: int, count: int) -> str:
    if count == 0 or distinct <= 1:
        return "constante"
    ratio = distinct / count
    return "baixa" if ratio <= 0.05 else "média" if ratio <= 0.5 else "alta"


# --- Step 2a: tables that could not be read ----------------------------------

def _failed_table(table_name: str, metadata: dict[str, Any], ctx: _Context) -> TableAnalysis:
    reason = str(metadata.get("worksheet_error") or "Esta aba não pôde ser lida.")
    ctx.warnings.append(f"A aba '{table_name}' não foi processada: {reason}")
    return TableAnalysis(
        name=table_name, status=metadata.get("worksheet_status", "error"), error_message=reason,
        rows=int(metadata.get("rows_available", 0)), rows_available=int(metadata.get("rows_available", 0)),
        rows_analyzed=0, sampled=False, columns=int(metadata.get("columns_total", 0)),
        columns_analyzed=0, header_row_used=metadata.get("header_row_used"),
        header_detection=metadata.get("header_detection", {}),
        rows_empty=int(metadata.get("rows_empty", 0)),
        trailing_empty_rows=int(metadata.get("trailing_empty_rows", 0)), sampling_method="none",
        empty_rows=0, empty_columns=0, duplicate_rows=0,
        table_type="não analisada", table_type_confidence="low",
        table_type_reason="A leitura desta aba falhou; nenhuma conclusão estrutural foi produzida.",
        key_candidates=[], quality=quality_score(0, 0, 0, 0, 0), column_analyses=[],
    )


# --- Step 2b: column names ---------------------------------------------------

def _normalized_column_names(original_names: list[Any]) -> list[str]:
    """Strip names, name blanks 'Coluna N' and suffix repeated names with ' (n)'."""
    names = [str(column).strip() or f"Coluna {index + 1}" for index, column in enumerate(original_names)]
    if len(set(names)) == len(names):
        return names
    repeated: dict[str, int] = {}
    names = []
    for column in original_names:
        label = str(column).strip() or f"Coluna {len(names) + 1}"
        repeated[label] = repeated.get(label, 0) + 1
        names.append(label if repeated[label] == 1 else f"{label} ({repeated[label]})")
    return names


# --- Step 2c: one column -----------------------------------------------------

@dataclass
class _ColumnResult:
    analysis: ColumnAnalysis
    key_candidate: dict[str, Any] | None


def _profile_column(series: pd.Series, column_name: str, table_name: str, rows_analyzed: int,
                    sampled: bool) -> _ColumnResult:
    count = int(series.count())
    null_count = int(series.isna().sum())
    distinct_count = int(series.nunique(dropna=True))
    null_pct = round(null_count / rows_analyzed * 100, 2) if rows_analyzed else 0.0
    distinct_pct = round(distinct_count / max(1, count) * 100, 2) if count else 0.0
    inferred = infer_type(series, column_name)
    role, role_confidence = semantic_role(series, column_name, inferred)
    invalid_count = inconsistent_value_count(series, inferred)
    confidence = type_confidence(series, inferred)
    private_reason, sensitivity_category, sensitivity_confidence = sensitivity_details(
        column_name, series, physical_type(series), inferred, role, confidence)
    candidate, key_confidence, key_reasons, key_assessment = key_candidate_info(
        column_name, 100 - null_pct, distinct_pct, sampled, inferred, role, table_name)
    anomalies = [] if private_reason else numeric_anomalies(series, inferred, column_name)
    column_stats = {} if private_reason else statistics(series, inferred)
    # Category labels and cell examples are intentionally omitted from the report.
    frequencies = series.dropna().astype(str).value_counts()
    top_values = [{"count": int(freq), "percent": round(float(freq / max(1, count) * 100), 2)}
                  for freq in frequencies.head(3).tolist()]
    analysis = ColumnAnalysis(
        name=column_name, original_type=str(series.dtype), physical_type=physical_type(series),
        inferred_type=inferred, semantic_role=role, semantic_role_confidence=role_confidence,
        confidence=confidence, type_reason=type_reason(series, column_name, inferred),
        sensitive=bool(private_reason), sensitivity_reason=private_reason,
        sensitivity_category=sensitivity_category, sensitivity_confidence=sensitivity_confidence,
        value_count=count, null_count=null_count, null_pct=null_pct,
        completeness_pct=round(100 - null_pct, 2), distinct_count=distinct_count,
        distinct_pct=distinct_pct, cardinality=_cardinality(distinct_count, count),
        duplicate_count=max(0, count - distinct_count),
        empty=bool(series.isna().all() or series.astype(str).str.strip().eq("").all()),
        key_candidate=candidate, key_assessment=key_assessment,
        key_confidence=key_confidence, key_reasons=key_reasons,
        inconsistent_values=invalid_count, invalid_dates=invalid_date_count(series, inferred),
        zero_count=int(column_stats.get("zero_count", 0)) if not private_reason else None,
        negative_count=int(column_stats.get("negative_count", 0)) if not private_reason else None,
        statistics=StatisticsAnalysis(**column_stats),
        top_values=[] if private_reason else top_values, null_classification=null_band(null_pct),
        anomalies=anomalies,
    )
    key = None
    if candidate:
        key = {"columns": [column_name], "confidence": key_confidence, "uniqueness_pct": distinct_pct,
               "completeness_pct": 100 - null_pct, "assessment": key_assessment, "reasons": key_reasons}
    return _ColumnResult(analysis, key)


# --- Step 2d: one table ------------------------------------------------------

def _table_quality(rows: int, columns: int, duplicate_rows: int, column_analyses: list[ColumnAnalysis],
                   integrity_pct: float | None = None):
    return quality_score(
        rows, columns,
        sum(column.null_count for column in column_analyses),
        sum(column.inconsistent_values for column in column_analyses),
        duplicate_rows, rows * columns,
        sum(column.inconsistent_values > 0 for column in column_analyses),
        integrity_pct,
        [column.name for column in column_analyses if column.null_count],
        [column.name for column in column_analyses if column.inconsistent_values],
    )


def _table_warnings(table_name: str, metadata: dict[str, Any], rows_total: int, rows_analyzed: int,
                    columns_total: int, columns_profiled: int, frames_count: int, ctx: _Context) -> None:
    settings = ctx.settings
    import_settings = metadata.get("import_settings", {})
    if bool(metadata.get("sampled", rows_total > rows_analyzed)):
        ctx.warnings.append(f"A tabela '{table_name}' foi amostrada: {rows_analyzed:,} de {rows_total:,} linhas foram perfiladas.")
    if rows_total == 0 or columns_total == 0:
        ctx.warnings.append(f"A tabela '{table_name}' não contém linhas ou colunas para perfilar.")
    if columns_total > columns_profiled:
        ctx.warnings.append(f"A tabela '{table_name}' tem {columns_total} colunas; somente {columns_profiled} foram perfiladas.")
    if metadata.get("tables_total", frames_count) > settings.max_tables_to_analyze:
        ctx.warnings.append(f"O arquivo contém {metadata['tables_total']} abas; somente {settings.max_tables_to_analyze} foram analisadas.")
    if import_settings.get("delimiter_ambiguous"):
        ctx.warnings.append(f"O delimitador de '{table_name}' não foi identificado com segurança; foi usado {import_settings.get('delimiter')!r}.")
    if ctx.file_type == "csv" and columns_total == 1:
        ctx.warnings.append(f"O arquivo '{table_name}' possui apenas uma coluna. Verifique se o delimitador foi identificado corretamente.")
    if import_settings.get("header_ambiguous") and ctx.header_mode == "auto":
        ctx.warnings.append(f"A presença de cabeçalho em '{table_name}' é ambígua; a primeira linha foi tratada como dados e foram usados nomes genéricos para evitar expor possíveis valores no relatório.")


def _table_status(metadata: dict[str, Any], rows_analyzed: int, rows_total: int) -> str:
    if metadata.get("worksheet_status", "completed") == "completed_empty":
        return "completed_empty"
    if rows_analyzed == 0 and rows_total > 0:
        return "skipped"
    return "completed"


def _profile_table(table_name: str, frame: pd.DataFrame, metadata: dict[str, Any], frames_count: int,
                   ctx: _Context) -> TableAnalysis:
    settings = ctx.settings
    if len(frame.columns) > settings.max_columns_to_analyze:
        frame = frame.iloc[:, :settings.max_columns_to_analyze]
    original_column_names = list(frame.columns)
    frame.columns = _normalized_column_names(original_column_names)
    rows_analyzed = len(frame)
    rows_total = int(metadata.get("rows_available", metadata.get("total_rows", rows_analyzed)))
    sampled = bool(metadata.get("sampled", rows_total > rows_analyzed))
    columns_total = int(metadata.get("columns_total", len(original_column_names)))
    empty_row_mask = frame.isna().all(axis=1) if len(frame.columns) else pd.Series(False, index=frame.index)
    empty_rows = int(metadata.get("rows_empty", empty_row_mask.sum()))
    empty_columns = int(sum(frame[column].isna().all() or frame[column].astype(str).str.strip().eq("").all()
                            for column in frame.columns))
    duplicate_rows = duplicate_row_count(frame)

    column_analyses: list[ColumnAnalysis] = []
    key_candidates: list[dict[str, Any]] = []
    single_keys: set[str] = set()
    for column_name in frame.columns:
        ctx.check_timeout()
        result = _profile_column(frame[column_name], str(column_name), str(table_name), rows_analyzed, sampled)
        column_analyses.append(result.analysis)
        if result.key_candidate:
            single_keys.add(column_name)
            key_candidates.append(result.key_candidate)
        ctx.anomalies.extend(result.analysis.anomalies)

    key_candidates.extend(composite_keys(frame, single_keys, sampled))
    key_candidates = key_candidates[:settings.max_key_candidates]
    kind, kind_confidence, kind_reason = table_kind(table_name, frame)
    _table_warnings(table_name, metadata, rows_total, rows_analyzed, columns_total, len(frame.columns),
                    frames_count, ctx)
    import_settings = metadata.get("import_settings", {})
    table = TableAnalysis(
        name=table_name,
        status=_table_status(metadata, rows_analyzed, rows_total),
        header_row_used=metadata.get("header_row_used", 1 if import_settings.get("header") else None),
        header_detection=metadata.get("header_detection", {}),
        rows=rows_total, rows_available=rows_total, rows_analyzed=rows_analyzed, sampled=sampled,
        sampling_method=metadata.get("sampling_method", "none"),
        rows_empty=empty_rows, trailing_empty_rows=int(metadata.get("trailing_empty_rows", 0)),
        columns=columns_total, columns_analyzed=len(frame.columns), empty_rows=empty_rows,
        empty_columns=empty_columns, duplicate_rows=duplicate_rows,
        table_type=kind, table_type_confidence=kind_confidence, table_type_reason=kind_reason,
        key_candidates=key_candidates,
        quality=_table_quality(rows_analyzed, len(frame.columns), duplicate_rows, column_analyses),
        column_analyses=column_analyses,
    )
    totals = ctx.totals
    totals.nulls += sum(column.null_count for column in column_analyses)
    totals.invalid += sum(column.inconsistent_values for column in column_analyses)
    totals.duplicates += duplicate_rows
    totals.rows += rows_total
    totals.profiled_rows += rows_analyzed
    totals.profiled_columns += len(frame.columns)
    totals.profiled_cells += rows_analyzed * len(frame.columns)
    return table


# --- Step 3: batch relationship samples (CSV only) ---------------------------

def _collect_relationship_frames(frames: dict[str, pd.DataFrame], tables: list[TableAnalysis],
                                 relationship_frames: dict[str, pd.DataFrame], relationship_budget: list[int],
                                 prefix: str, settings: Any) -> None:
    """Store a bounded, non-sensitive sample of each table for cross-file matching."""
    tables_by_name = {table.name: table for table in tables}
    for table_name, frame in frames.items():
        available = relationship_budget[0]
        sensitive_columns = {column.name for column in tables_by_name.get(table_name, tables[0]).column_analyses
                             if column.sensitive} if tables else set()
        eligible_columns = [column for column in frame.columns if str(column) not in sensitive_columns]
        column_count = min(len(eligible_columns), settings.max_columns_to_analyze, available)
        if available <= 0 or column_count == 0:
            continue
        selected_columns = eligible_columns[:column_count]
        row_count = min(len(frame), settings.max_relationship_value_rows, max(1, available // column_count))
        if row_count == 0:
            continue
        relation_frame = frame.loc[:, selected_columns].iloc[:row_count].copy()
        relation_frame.attrs["sampled"] = bool(frame.attrs.get("sampled", False) or row_count < len(frame))
        relationship_frames[f"{prefix}::{table_name}"] = relation_frame
        relationship_budget[0] -= row_count * column_count


# --- Step 4: relationships and integrity -------------------------------------

def _apply_relationship_quality(tables: list[TableAnalysis], relationships: list) -> float | None:
    """Recompute each table's quality including integrity; return file-level integrity."""
    integrity_pct = (sum(relation.coverage_pct for relation in relationships) / len(relationships)
                     if relationships else None)
    for table in tables:
        table_relations = [relation for relation in relationships
                           if table.name in {relation.source_table, relation.target_table}]
        table_integrity = (sum(relation.coverage_pct for relation in table_relations) / len(table_relations)
                           if table_relations else None)
        table.quality = _table_quality(table.rows_analyzed, table.columns_analyzed, table.duplicate_rows,
                                       table.column_analyses, table_integrity)
    return integrity_pct


def _overall_quality(tables: list[TableAnalysis], totals: _Totals, integrity_pct: float | None):
    columns = [column for table in tables for column in table.column_analyses]
    return quality_score(
        totals.profiled_rows, max(1, totals.profiled_columns), totals.nulls, totals.invalid,
        totals.duplicates, totals.profiled_cells,
        sum(column.inconsistent_values > 0 for column in columns),
        integrity_pct,
        [column.name for column in columns if column.null_count],
        [column.name for column in columns if column.inconsistent_values],
    )


# --- Step 5: report assembly -------------------------------------------------

def _report_status(tables: list[TableAnalysis], frames: dict[str, pd.DataFrame]) -> str:
    failed_tables = sum(table.status in {"failed", "error", "skipped", "partial"} for table in tables)
    successful_tables = sum(table.status in {"completed", "completed_empty"} for table in tables)
    tables_omitted = any(int(frame.attrs.get("tables_total", len(frames))) > len(frames) for frame in frames.values())
    if not successful_tables:
        return "failed"
    return "partial" if failed_tables or tables_omitted else "completed"


def _effective_settings(frames: dict[str, pd.DataFrame], tables: list[TableAnalysis], file_type: str,
                        csv_encoding: str | None, csv_delimiter: str, decimal_separator: str,
                        header_mode: str, settings: Any) -> dict[str, Any]:
    csv_settings = frames[next(iter(frames))].attrs.get("import_settings", {}) if frames else {}
    effective = {
        "csv_encoding": csv_encoding, "csv_delimiter": csv_settings.get("delimiter", csv_delimiter),
        "decimal_separator": csv_settings.get("decimal_separator", decimal_separator),
        "header_mode": header_mode, "max_rows_to_analyze": settings.max_rows_to_analyze,
        "max_columns_to_analyze": settings.max_columns_to_analyze,
        "max_cells_to_analyze": settings.max_cells_to_analyze,
        "max_xlsx_profile_cells": settings.max_xlsx_profile_cells,
        "max_tables_to_analyze": settings.max_tables_to_analyze,
        "max_relationship_value_rows": settings.max_relationship_value_rows,
        "max_batch_relationship_cells": settings.max_batch_relationship_cells,
        "sample_size": settings.sample_size, "sampling_enabled": settings.enable_sampling,
        "analysis_timeout_seconds": settings.analysis_timeout_seconds,
        "null_thresholds_pct": {"attention": settings.null_attention_threshold_pct,
                                "moderate": settings.null_moderate_threshold_pct,
                                "critical_above": settings.null_critical_threshold_pct},
        "quality_thresholds": {"excellent": settings.quality_excellent_threshold,
                               "good": settings.quality_good_threshold,
                               "attention": settings.quality_attention_threshold},
        "quality_weights": {"completeness": settings.quality_completeness_weight,
                            "uniqueness": settings.quality_uniqueness_weight,
                            "consistency": settings.quality_consistency_weight,
                            "validity": settings.quality_validity_weight,
                            "integrity": settings.quality_integrity_weight},
        "percentiles": list(settings.percentiles),
        "statistics_sampled": any(table.sampled for table in tables),
    }
    if file_type in {"xlsx", "xlsm"}:
        effective["worksheets_analyzed"] = len(frames)
        effective["worksheets_total"] = max(
            (int(frame.attrs.get("tables_total", len(frames))) for frame in frames.values()), default=0
        )
    return effective


def _security_section(file_type: str, security_metadata: dict[str, Any] | None
                      ) -> tuple[FileSecurityAnalysis | None, list[str]]:
    if file_type not in {"xlsx", "xlsm"}:
        return None, ["O arquivo foi lido localmente como texto; nenhum conteúdo foi executado."]
    security_metadata = security_metadata or {}
    active_types = list(security_metadata.get("active_content_types", []))
    file_security = FileSecurityAnalysis(
        active_content_detected=bool(security_metadata.get("active_content_detected", False)),
        active_content_types=active_types,
        external_relationships_detected=bool(security_metadata.get("external_relationships_detected", False)),
        external_relationship_count=int(security_metadata.get("external_relationship_count", 0)),
        formulas_action="cached_values_only",
    )
    notes = ["As abas legíveis foram abertas em modo somente leitura; macros, fórmulas e objetos não foram executados."]
    if active_types:
        notes.append(f"Conteúdo potencialmente ativo detectado ({', '.join(active_types)}); não foi executado.")
    if file_security.external_relationships_detected:
        notes.append("Relações externas foram detectadas, mas não foram seguidas nem atualizadas.")
    notes.append("Fórmulas não são recalculadas; somente valores armazenados em cache podem ser lidos.")
    return file_security, notes


# --- Orchestrator ------------------------------------------------------------

def analyze_file(
    filename: str,
    file_type: str,
    content: bytes,
    csv_encoding: str | None = None,
    csv_delimiter: str = "auto",
    decimal_separator: str = "auto",
    header_mode: str = "auto",
    relationship_frames: dict[str, pd.DataFrame] | None = None,
    relationship_budget: list[int] | None = None,
    relationship_prefix: str = "",
    security_metadata: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> AnalysisReport:
    ctx = _Context(file_type=file_type, header_mode=header_mode, started=time.monotonic(),
                   settings=get_settings())
    if file_type in {"xlsx", "xlsm"} and security_metadata is None:
        security_metadata = inspect_xlsx_package(content)
    if progress_callback:
        progress_callback({"stage": "opening_workbook" if file_type in {"xlsx", "xlsm"} else "file_reading",
                           "message": "Abrindo arquivo para leitura segura"})
    frames = read_tables(content, file_type, csv_encoding, csv_delimiter, decimal_separator, header_mode,
                         security_metadata=security_metadata, on_progress=progress_callback)

    tables: list[TableAnalysis] = []
    for table_name, frame in frames.items():
        ctx.check_timeout()
        metadata = dict(frame.attrs)
        if metadata.get("worksheet_status") in {"failed", "error", "skipped"}:
            tables.append(_failed_table(table_name, metadata, ctx))
            continue
        tables.append(_profile_table(table_name, frame, metadata, len(frames), ctx))
        if progress_callback:
            progress_callback({"stage": "quality_analysis", "current_sheet": len(tables),
                               "total_sheets": len(frames), "current_sheet_name": table_name,
                               "message": f"Qualidade da aba '{table_name}' calculada"})

    if relationship_frames is not None and relationship_budget is not None and file_type == "csv":
        _collect_relationship_frames(frames, tables, relationship_frames, relationship_budget,
                                     relationship_prefix, ctx.settings)

    relationships = suggest_relationships(frames, tables)
    integrity_pct = _apply_relationship_quality(tables, relationships)
    file_security, safety_warnings = _security_section(file_type, security_metadata)
    report = AnalysisReport(
        analysis_id=str(uuid.uuid4()), analyzed_at=datetime.now().astimezone(),
        processing_time_ms=int((time.monotonic() - ctx.started) * 1000), filename=filename,
        file_type=file_type, file_size_bytes=len(content), file_sha256=sha256(content).hexdigest(),
        status=_report_status(tables, frames),
        settings=_effective_settings(frames, tables, file_type, csv_encoding, csv_delimiter,
                                     decimal_separator, header_mode, ctx.settings),
        security_warnings=safety_warnings, security=file_security,
        tables=tables, relationships=relationships, anomalies=ctx.anomalies,
        quality=_overall_quality(tables, ctx.totals, integrity_pct),
        warnings=list(dict.fromkeys(ctx.warnings)),
    )
    if progress_callback:
        progress_callback({"stage": "consolidating_results", "current_sheet": len(frames),
                           "total_sheets": len(frames), "message": "Consolidando relatório"})
    return report
