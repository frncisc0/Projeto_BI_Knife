from datetime import datetime
from hashlib import sha256
import re
import time
import unicodedata
import uuid
from typing import Any, Callable

import pandas as pd

from app.analyzers.file_analyzer import read_tables
from app.analyzers.quality_analyzer import (
    duplicate_row_count,
    inconsistent_value_count,
    invalid_date_count,
    null_band,
    numeric_anomalies,
)
from app.analyzers.relationship_analyzer import suggest_relationships
from app.analyzers.schema_analyzer import infer_type, physical_type, sensitivity_details, semantic_role, type_confidence, type_reason
from app.analyzers.statistics_analyzer import statistics
from app.core.config import get_settings
from app.core.exceptions import AnalysisError
from app.models.analysis_models import Anomaly, AnalysisReport, ColumnAnalysis, FileSecurityAnalysis, QualityAnalysis, StatisticsAnalysis, TableAnalysis
from app.security.file_validation import inspect_xlsx_package


KEY_NAME_TERMS = ("id", "codigo", "chave", "contrato", "numero", "matricula", "registro", "sku", "pedido", "processo")


def _name_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return set(re.findall(r"[a-z0-9]+", normalized))


def _clean(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not pd.notna(value):
        return None
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def _cardinality(distinct: int, count: int) -> str:
    if count == 0 or distinct <= 1:
        return "constante"
    ratio = distinct / count
    return "baixa" if ratio <= 0.05 else "média" if ratio <= 0.5 else "alta"


def _key_info(name: str, complete_pct: float, unique_pct: float, sampled: bool,
              inferred: str, role: str, table_name: str) -> tuple[bool, str | None, list[str], str]:
    reasons: list[str] = []
    if complete_pct < 95 or unique_pct < 95:
        return False, None, reasons, "not_candidate"
    reasons.append(f"{complete_pct:.1f}% preenchida")
    reasons.append(f"{unique_pct:.1f}% única")
    tokens = _name_tokens(name)
    name_match = bool(tokens & set(KEY_NAME_TERMS)) or role in {"identifier", "code"}
    table_tokens = _name_tokens(table_name)
    entity_context = table_tokens & {"contrato", "cliente", "fornecedor", "colaborador", "funcionario",
                                     "processo", "pedido", "fatura"}
    if role == "measure" or inferred in {"moeda", "percentual"}:
        reasons.append("coluna com natureza de medida; unicidade não comprova identificador")
        return False, None, reasons, "high_uniqueness_measure"
    if not name_match:
        reasons.append("alta unicidade sem evidência semântica de identificador")
        return False, None, reasons, "high_uniqueness_unconfirmed"
    reasons.append("nome ou papel semântico compatível com identificador")
    if entity_context:
        reasons.append("contexto da aba indica entidade ou processo identificável")
    strong = complete_pct == 100 and unique_pct == 100 and not sampled
    confidence = "low" if sampled else "high" if strong else "medium"
    return True, confidence, reasons, "strong_candidate" if strong else "possible_identifier"


def _composite_keys(frame: pd.DataFrame, single_keys: set[str], sampled: bool) -> list[dict[str, Any]]:
    candidates = []
    if len(frame.columns) < 2 or frame.empty:
        return candidates
    eligible = []
    for name in frame.columns:
        series = frame[name]
        tokens = _name_tokens(str(name))
        if tokens & {"custo", "risco", "valor", "preco", "salario",
                     "receita", "margem", "rescisao", "despesa", "faturamento"}:
            continue
        if series.notna().all() and series.nunique() / len(frame) >= 0.5:
            eligible.append(name)
    eligible = eligible[:12]
    for index, first in enumerate(eligible):
        if first in single_keys:
            continue
        for second in eligible[index + 1:]:
            if second in single_keys:
                continue
            pair = frame[[first, second]]
            unique_pct = pair.drop_duplicates().shape[0] / len(pair) * 100
            if unique_pct >= 98 and frame[first].nunique() < len(frame) and frame[second].nunique() < len(frame):
                candidates.append({
                    "columns": [str(first), str(second)], "confidence": "medium" if not sampled else "low",
                    "uniqueness_pct": round(unique_pct, 1),
                    "reasons": ["A combinação é mais única do que cada coluna isolada.",
                                "Avaliada sobre uma amostra." if sampled else "Sem nulos na combinação."],
                })
                if len(candidates) >= 5:
                    return candidates
    return candidates


def _table_kind(name: str, frame: pd.DataFrame) -> tuple[str, str, str]:
    normalized = name.casefold()
    if any(word in normalized for word in ("venda", "pedido", "transa", "movimento", "fato", "order", "sale")):
        return "provável tabela fato/transacional", "medium", "O nome da aba sugere eventos ou transações."
    if any(word in normalized for word in ("cliente", "produto", "fornecedor", "cadastro", "dimens", "reference", "ref_")):
        return "provável dimensão/cadastro", "medium", "O nome da aba sugere cadastro ou entidade de referência."
    if len(frame) and len(frame.columns) <= 5 and all(frame[column].nunique(dropna=True) / max(1, len(frame)) > 0.8 for column in frame.columns):
        return "possível tabela de referência", "low", "A tabela é compacta e possui alta unicidade por coluna."
    return "tipo indeterminado", "low", "Não há evidência suficiente para classificar esta tabela."


def _quality(rows: int, columns: int, null_count: int, invalid_count: int, duplicate_rows: int,
             cells_override: int | None = None, inconsistent_columns: int = 0,
             integrity_pct: float | None = None) -> QualityAnalysis:
    settings = get_settings()
    cells = max(1, cells_override if cells_override is not None else rows * columns)
    no_structure = rows == 0 or columns == 0
    completeness = 0.0 if no_structure else max(0.0, 100 - null_count / cells * 100)
    uniqueness = max(0.0, 100 - duplicate_rows / max(1, rows) * 100)
    validity = max(0.0, 100 - invalid_count / max(1, cells - null_count) * 100)
    consistency = max(0.0, 100 - inconsistent_columns / max(1, columns) * 100)
    dimensions = {
        "completeness": (completeness, settings.quality_completeness_weight),
        "uniqueness": (uniqueness, settings.quality_uniqueness_weight),
        "consistency": (consistency, settings.quality_consistency_weight),
        "validity": (validity, settings.quality_validity_weight),
    }
    if integrity_pct is not None:
        dimensions["integrity"] = (integrity_pct, settings.quality_integrity_weight)
    total_weight = sum(weight for _, weight in dimensions.values()) or 1
    score = round(sum(value * weight for value, weight in dimensions.values()) / total_weight, 1)
    score = max(0.0, min(100.0, score))
    classification = ("Crítica" if no_structure else "Excelente" if score >= settings.quality_excellent_threshold
                      else "Boa" if score >= settings.quality_good_threshold
                      else "Atenção" if score >= settings.quality_attention_threshold else "Crítica")
    alerts: list[dict[str, str | int | float]] = []
    if null_count:
        alerts.append({"severity": "information", "count": null_count,
                       "message": f"{null_count} valores ausentes ({100 - completeness:.1f}%); avalie se a ausência é esperada para estas colunas."})
    if duplicate_rows:
        alerts.append({"severity": "attention", "count": duplicate_rows, "message": f"{duplicate_rows} linhas repetidas foram encontradas."})
    if invalid_count:
        alerts.append({"severity": "critical", "count": invalid_count, "message": f"{invalid_count} valores não correspondem ao tipo inferido."})
    if inconsistent_columns:
        alerts.append({"severity": "attention", "count": inconsistent_columns,
                       "message": f"{inconsistent_columns} colunas apresentam mistura de tipos ou valores incompatíveis."})
    if integrity_pct is not None and integrity_pct < 95:
        alerts.append({"severity": "attention", "count": round(100 - integrity_pct, 1),
                       "message": f"Candidatos a relacionamento apresentam {100 - integrity_pct:.1f}% de valores sem correspondência estimada."})
    if not alerts and not no_structure:
        alerts.append({"severity": "ok", "count": 0, "message": "Nenhum alerta básico foi identificado pelas regras atuais."})
    if no_structure:
        alerts.append({"severity": "critical", "count": 0, "message": "A tabela não possui estrutura de dados para avaliação."})
    return QualityAnalysis(score=score, classification=classification, completeness_pct=round(completeness, 1),
                           uniqueness_pct=round(uniqueness, 1), consistency_pct=round(consistency, 1),
                           validity_pct=round(validity, 1), integrity_pct=round(integrity_pct, 1) if integrity_pct is not None else None,
                           integrity_assessed=integrity_pct is not None, alerts=alerts)


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
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> AnalysisReport:
    started = time.monotonic()
    if file_type in {"xlsx", "xlsm"} and security_metadata is None:
        security_metadata = inspect_xlsx_package(content)
    if progress_callback:
        progress_callback({"stage": "opening_workbook" if file_type in {"xlsx", "xlsm"} else "file_reading",
                           "message": "Abrindo arquivo para leitura segura"})
    frames = read_tables(content, file_type, csv_encoding, csv_delimiter, decimal_separator, header_mode,
                         security_metadata=security_metadata, on_progress=progress_callback)
    settings = get_settings()
    tables: list[TableAnalysis] = []
    warnings: list[str] = []
    all_anomalies: list[Anomaly] = []
    total_nulls = total_invalid = total_duplicates = total_rows = total_profiled_rows = total_profiled_columns = total_profiled_cells = 0

    for table_name, frame in frames.items():
        if time.monotonic() - started > settings.analysis_timeout_seconds:
            raise AnalysisError("A análise excedeu o tempo máximo configurado.")
        metadata = dict(frame.attrs)
        if metadata.get("worksheet_status") in {"failed", "error", "skipped"}:
            reason = str(metadata.get("worksheet_error") or "Esta aba não pôde ser lida.")
            table_status = metadata.get("worksheet_status", "error")
            tables.append(TableAnalysis(
                name=table_name, status=table_status, error_message=reason,
                rows=int(metadata.get("rows_available", 0)), rows_available=int(metadata.get("rows_available", 0)),
                rows_analyzed=0, sampled=False, columns=int(metadata.get("columns_total", 0)),
                columns_analyzed=0, header_row_used=metadata.get("header_row_used"),
                header_detection=metadata.get("header_detection", {}),
                rows_empty=int(metadata.get("rows_empty", 0)),
                trailing_empty_rows=int(metadata.get("trailing_empty_rows", 0)), sampling_method="none",
                empty_rows=0, empty_columns=0, duplicate_rows=0,
                table_type="não analisada", table_type_confidence="low",
                table_type_reason="A leitura desta aba falhou; nenhuma conclusão estrutural foi produzida.",
                key_candidates=[], quality=_quality(0, 0, 0, 0, 0), column_analyses=[],
            ))
            warnings.append(f"A aba '{table_name}' não foi processada: {reason}")
            continue
        if len(frame.columns) > settings.max_columns_to_analyze:
            frame = frame.iloc[:, :settings.max_columns_to_analyze]
        original_column_names = list(frame.columns)
        normalized_names = [str(column).strip() or f"Coluna {index + 1}" for index, column in enumerate(original_column_names)]
        if len(set(normalized_names)) != len(normalized_names):
            repeated: dict[str, int] = {}
            normalized_names = []
            for column in original_column_names:
                label = str(column).strip() or f"Coluna {len(normalized_names) + 1}"
                repeated[label] = repeated.get(label, 0) + 1
                normalized_names.append(label if repeated[label] == 1 else f"{label} ({repeated[label]})")
        frame.columns = normalized_names
        rows_analyzed = len(frame)
        rows_total = int(metadata.get("rows_available", metadata.get("total_rows", rows_analyzed)))
        sampled = bool(metadata.get("sampled", rows_total > rows_analyzed))
        columns_total = int(metadata.get("columns_total", len(original_column_names)))
        empty_row_mask = frame.isna().all(axis=1) if len(frame.columns) else pd.Series(False, index=frame.index)
        empty_rows = int(metadata.get("rows_empty", empty_row_mask.sum()))
        empty_columns = int(sum(frame[column].isna().all() or frame[column].astype(str).str.strip().eq("").all() for column in frame.columns))
        duplicate_rows = duplicate_row_count(frame)
        column_analyses: list[ColumnAnalysis] = []
        key_candidates: list[dict[str, Any]] = []
        single_keys: set[str] = set()
        table_nulls = table_invalid = 0

        for column_name in frame.columns:
            if time.monotonic() - started > settings.analysis_timeout_seconds:
                raise AnalysisError("A análise excedeu o tempo máximo configurado.")
            series = frame[column_name]
            count = int(series.count())
            null_count = int(series.isna().sum())
            distinct_count = int(series.nunique(dropna=True))
            null_pct = round(null_count / rows_analyzed * 100, 2) if rows_analyzed else 0.0
            distinct_pct = round(distinct_count / max(1, count) * 100, 2) if count else 0.0
            inferred = infer_type(series, str(column_name))
            role, role_confidence = semantic_role(series, str(column_name), inferred)
            invalid_count = inconsistent_value_count(series, inferred)
            confidence = type_confidence(series, inferred)
            private_reason, sensitivity_category, sensitivity_confidence = sensitivity_details(
                str(column_name), series, physical_type(series), inferred, role, confidence)
            candidate, key_confidence, key_reasons, key_assessment = _key_info(
                str(column_name), 100 - null_pct, distinct_pct, sampled, inferred, role, str(table_name))
            null_label = null_band(null_pct)
            anomalies = [] if private_reason else numeric_anomalies(series, inferred, str(column_name))
            column_stats = {} if private_reason else statistics(series, inferred)
            zero_count = int(column_stats.get("zero_count", 0))
            negative_count = int(column_stats.get("negative_count", 0))
            # Category labels and cell examples are intentionally omitted from the report.
            frequencies = series.dropna().astype(str).value_counts()
            top_values = [{"count": int(freq), "percent": round(float(freq / max(1, count) * 100), 2)}
                          for freq in frequencies.head(3).tolist()]
            column = ColumnAnalysis(
                name=str(column_name), original_type=str(series.dtype), physical_type=physical_type(series), inferred_type=inferred,
                semantic_role=role, semantic_role_confidence=role_confidence,
                confidence=confidence, type_reason=type_reason(series, str(column_name), inferred),
                sensitive=bool(private_reason), sensitivity_reason=private_reason,
                sensitivity_category=sensitivity_category, sensitivity_confidence=sensitivity_confidence,
                value_count=count, null_count=null_count, null_pct=null_pct,
                completeness_pct=round(100 - null_pct, 2), distinct_count=distinct_count,
                distinct_pct=distinct_pct, cardinality=_cardinality(distinct_count, count),
                duplicate_count=max(0, count - distinct_count), empty=bool(series.isna().all() or series.astype(str).str.strip().eq("").all()),
                key_candidate=candidate, key_assessment=key_assessment,
                key_confidence=key_confidence, key_reasons=key_reasons,
                inconsistent_values=invalid_count, invalid_dates=invalid_date_count(series, inferred),
                zero_count=zero_count if not private_reason else None,
                negative_count=negative_count if not private_reason else None,
                statistics=StatisticsAnalysis(**column_stats),
                top_values=[] if private_reason else top_values, null_classification=null_label,
                anomalies=anomalies,
            )
            column_analyses.append(column)
            table_nulls += null_count
            table_invalid += invalid_count
            if candidate:
                single_keys.add(column_name)
                key_candidates.append({"columns": [column_name], "confidence": key_confidence,
                                       "uniqueness_pct": distinct_pct, "completeness_pct": 100 - null_pct,
                                       "assessment": key_assessment, "reasons": key_reasons})
            all_anomalies.extend(anomalies)

        key_candidates.extend(_composite_keys(frame, single_keys, sampled))
        key_candidates = key_candidates[:settings.max_key_candidates]
        inconsistent_columns = sum(column.inconsistent_values > 0 for column in column_analyses)
        quality = _quality(rows_analyzed, len(frame.columns), table_nulls, table_invalid, duplicate_rows,
                           rows_analyzed * len(frame.columns), inconsistent_columns)
        kind, kind_confidence, kind_reason = _table_kind(table_name, frame)
        if sampled:
            warnings.append(f"A tabela '{table_name}' foi amostrada: {rows_analyzed:,} de {rows_total:,} linhas foram perfiladas.")
        if rows_total == 0 or columns_total == 0:
            warnings.append(f"A tabela '{table_name}' não contém linhas ou colunas para perfilar.")
        if columns_total > len(frame.columns):
            warnings.append(f"A tabela '{table_name}' tem {columns_total} colunas; somente {len(frame.columns)} foram perfiladas.")
        import_settings = metadata.get("import_settings", {})
        if metadata.get("tables_total", len(frames)) > settings.max_tables_to_analyze:
            warnings.append(f"O arquivo contém {metadata['tables_total']} abas; somente {settings.max_tables_to_analyze} foram analisadas.")
        if import_settings.get("delimiter_ambiguous"):
            warnings.append(f"O delimitador de '{table_name}' não foi identificado com segurança; foi usado {repr(import_settings.get('delimiter'))}.")
        if import_settings.get("header_ambiguous") and header_mode == "auto":
            warnings.append(f"A presença de cabeçalho em '{table_name}' é ambígua; a primeira linha foi tratada como dados e foram usados nomes genéricos para evitar expor possíveis valores no relatório.")
        worksheet_status = metadata.get("worksheet_status", "completed")
        if worksheet_status == "completed_empty":
            table_status = "completed_empty"
        elif rows_analyzed == 0 and rows_total > 0:
            table_status = "skipped"
        else:
            table_status = "completed"
        tables.append(TableAnalysis(
            name=table_name,
            status=table_status,
            header_row_used=metadata.get("header_row_used", 1 if import_settings.get("header") else None),
            header_detection=metadata.get("header_detection", {}),
            rows=rows_total, rows_available=rows_total, rows_analyzed=rows_analyzed, sampled=sampled,
            sampling_method=metadata.get("sampling_method", "none"),
            rows_empty=empty_rows, trailing_empty_rows=int(metadata.get("trailing_empty_rows", 0)),
            columns=columns_total, columns_analyzed=len(frame.columns), empty_rows=empty_rows,
            empty_columns=empty_columns, duplicate_rows=duplicate_rows,
            table_type=kind, table_type_confidence=kind_confidence, table_type_reason=kind_reason,
            key_candidates=key_candidates, quality=quality, column_analyses=column_analyses,
        ))
        total_nulls += table_nulls
        total_invalid += table_invalid
        total_duplicates += duplicate_rows
        total_rows += rows_total
        total_profiled_rows += rows_analyzed
        total_profiled_columns += len(frame.columns)
        total_profiled_cells += rows_analyzed * len(frame.columns)
        if progress_callback:
            progress_callback({"stage": "quality_analysis", "current_sheet": len(tables),
                               "total_sheets": len(frames), "current_sheet_name": table_name,
                               "message": f"Qualidade da aba '{table_name}' calculada"})

    if relationship_frames is not None and relationship_budget is not None and file_type == "csv":
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
            relationship_frames[f"{relationship_prefix}::{table_name}"] = relation_frame
            relationship_budget[0] -= row_count * column_count

    relationships = suggest_relationships(frames, tables)
    integrity_pct = (sum(relation.coverage_pct for relation in relationships) / len(relationships)) if relationships else None
    for table in tables:
        table_relations = [relation for relation in relationships if table.name in {relation.source_table, relation.target_table}]
        table_integrity = sum(relation.coverage_pct for relation in table_relations) / len(table_relations) if table_relations else None
        table_nulls = sum(column.null_count for column in table.column_analyses)
        table_invalid = sum(column.inconsistent_values for column in table.column_analyses)
        table_inconsistent_columns = sum(column.inconsistent_values > 0 for column in table.column_analyses)
        table.quality = _quality(table.rows_analyzed, table.columns_analyzed, table_nulls, table_invalid,
                                 table.duplicate_rows, table.rows_analyzed * table.columns_analyzed,
                                 table_inconsistent_columns, table_integrity)
    overall_quality = _quality(total_profiled_rows, max(1, total_profiled_columns), total_nulls,
                               total_invalid, total_duplicates, total_profiled_cells,
                               sum(column.inconsistent_values > 0 for table in tables for column in table.column_analyses),
                               integrity_pct)
    failed_tables = sum(table.status in {"failed", "error", "skipped", "partial"} for table in tables)
    successful_tables = sum(table.status in {"completed", "completed_empty"} for table in tables)
    tables_omitted = any(int(frame.attrs.get("tables_total", len(frames))) > len(frames) for frame in frames.values())
    report_status = "failed" if not successful_tables else "partial" if failed_tables or tables_omitted else "completed"
    csv_settings = frames[next(iter(frames))].attrs.get("import_settings", {}) if frames else {}
    actual_settings = {
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
        actual_settings["worksheets_analyzed"] = len(frames)
        actual_settings["worksheets_total"] = max(
            (int(frame.attrs.get("tables_total", len(frames))) for frame in frames.values()), default=0
        )
    file_security = None
    if file_type in {"xlsx", "xlsm"}:
        security_metadata = security_metadata or {}
        active_types = list(security_metadata.get("active_content_types", []))
        file_security = FileSecurityAnalysis(
            active_content_detected=bool(security_metadata.get("active_content_detected", False)),
            active_content_types=active_types,
            external_relationships_detected=bool(security_metadata.get("external_relationships_detected", False)),
            external_relationship_count=int(security_metadata.get("external_relationship_count", 0)),
            formulas_action="cached_values_only",
        )
        safety_warnings = ["As abas legíveis foram abertas em modo somente leitura; macros, fórmulas e objetos não foram executados."]
        if active_types:
            safety_warnings.append(f"Conteúdo potencialmente ativo detectado ({', '.join(active_types)}); não foi executado.")
        if file_security.external_relationships_detected:
            safety_warnings.append("Relações externas foram detectadas, mas não foram seguidas nem atualizadas.")
        safety_warnings.append("Fórmulas não são recalculadas; somente valores armazenados em cache podem ser lidos.")
    else:
        safety_warnings = ["O arquivo foi lido localmente como texto; nenhum conteúdo foi executado."]
    report = AnalysisReport(
        analysis_id=str(uuid.uuid4()), analyzed_at=datetime.now().astimezone(),
        processing_time_ms=int((time.monotonic() - started) * 1000), filename=filename,
        file_type=file_type, file_size_bytes=len(content), file_sha256=sha256(content).hexdigest(),
        status=report_status, settings=actual_settings, security_warnings=safety_warnings,
        security=file_security,
        tables=tables, relationships=relationships, anomalies=all_anomalies,
        quality=overall_quality, warnings=list(dict.fromkeys(warnings)),
    )
    if progress_callback:
        progress_callback({"stage": "consolidating_results", "current_sheet": len(frames),
                           "total_sheets": len(frames), "message": "Consolidando relatório"})
    return report


def _cardinality(distinct: int, count: int) -> str:
    if count == 0 or distinct <= 1:
        return "constante"
    ratio = distinct / count
    return "baixa" if ratio <= 0.05 else "média" if ratio <= 0.5 else "alta"
