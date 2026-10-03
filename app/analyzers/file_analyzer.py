import csv
from io import BytesIO, StringIO
import random
import re
import time
from typing import Any, Callable

import pandas as pd
from openpyxl import load_workbook

from app.analyzers.statistics_analyzer import numeric_values
from app.core.config import get_settings
from app.core.exceptions import AnalysisError, FileValidationError


_HEADER_TERMS = {
    "id", "key", "chave", "code", "cod", "codigo", "código", "name", "nome", "email", "e-mail",
    "phone", "telefone", "celular", "date", "data", "dt", "valor", "value", "amount", "price",
    "preco", "preço", "salary", "salario", "salário", "category", "categoria", "client", "cliente",
    "customer", "product", "produto", "order", "pedido", "total", "count", "quantity", "quantidade",
    "status", "type", "tipo", "region", "regiao", "região", "description", "descricao", "descrição",
    "cpf", "cnpj", "birth", "nascimento", "month", "year", "ano", "mes", "mês", "blank",
    "revenue", "faturamento", "sales", "venda", "discount", "desconto", "profit", "lucro",
    "cost", "custo", "score", "rating", "age", "idade", "city", "cidade", "state", "estado",
    "country", "pais", "país",
}


def _row_limit(total_columns: int) -> int:
    settings = get_settings()
    configured = min(settings.max_rows_to_analyze, settings.sample_size) if settings.enable_sampling else settings.max_rows_to_analyze
    return max(1, min(configured, settings.max_cells_to_analyze // max(1, min(total_columns, settings.max_columns_to_analyze))))


def _csv_dialect(text: str) -> tuple[str, bool]:
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter, False
    except csv.Error:
        counts = {char: sample.count(char) for char in (",", ";", "\t", "|")}
        delimiter = max(counts, key=counts.get)
        return delimiter if counts[delimiter] else ",", True


def _guess_header(text: str, delimiter: str) -> tuple[bool, bool]:
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    first = next(reader, [])
    second = next(reader, [])
    if not first or not second or len(first) != len(second):
        return False, True
    def numeric(value: str) -> bool:
        return bool(numeric_values(pd.Series([value])).notna().iloc[0])
    third = next(reader, [])
    transitions = sum(not numeric(left) and numeric(right) for left, right in zip(first, second))
    if len(third) == len(first):
        stable_data_types = sum(numeric(second_value) == numeric(third_value)
                                for second_value, third_value in zip(second, third))
    else:
        stable_data_types = 0
    def field_name_signal(value: str) -> bool:
        tokens = set(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE))
        snake_case = bool(re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", value.strip()))
        return snake_case or bool(tokens & _HEADER_TERMS)

    nonempty_first = [value for value in first if value.strip()]
    if nonempty_first and all(field_name_signal(value) for value in nonempty_first):
        return True, False
    # Multiple independent type transitions plus stable types in following rows
    # are stronger evidence than a single string-to-number transition.
    if transitions >= 2 and stable_data_types >= max(2, len(first) - 1):
        return True, False
    # An unresolved first row is never silently promoted to schema: the UI asks
    # the user whether it is a header or data before finalizing the report.
    return False, True


def detect_csv_options(content: bytes, encoding: str) -> dict[str, Any]:
    text = content.decode(encoding)
    delimiter, ambiguous_delimiter = _csv_dialect(text)
    has_header, ambiguous_header = _guess_header(text, delimiter)
    # Decimal comma is inferred only when a non-comma delimiter is used and sampled cells match it.
    decimal = "," if delimiter != "," and any(
        "," in cell and cell.rsplit(",", 1)[-1].isdigit()
        for row in list(csv.reader(StringIO(text[:65536]), delimiter=delimiter))[:20]
        for cell in row
    ) else "."
    return {"delimiter": delimiter, "decimal": decimal, "has_header": has_header,
            "ambiguous_delimiter": ambiguous_delimiter, "ambiguous_header": ambiguous_header}


def _nonempty_row(values: tuple[Any, ...]) -> bool:
    return any(value is not None and (not isinstance(value, str) or value.strip()) for value in values)


def _header_score(row: tuple[Any, ...], following_rows: list[tuple[Any, ...]]) -> float:
    populated = [value for value in row if value is not None and str(value).strip()]
    if not populated:
        return 0.0
    labels = [str(value).strip() for value in populated]
    text_ratio = sum(isinstance(value, str) and bool(value.strip()) for value in populated) / len(populated)
    unique_ratio = len({label.casefold() for label in labels}) / len(labels)
    density = len(populated) / max(1, len(row))
    tokens = {token for label in labels for token in re.findall(r"[^\W_]+", label.casefold(), flags=re.UNICODE)}
    term_ratio = min(1.0, len(tokens & _HEADER_TERMS) / max(1, len(populated)))
    field_name_ratio = sum(bool(re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", label.casefold()))
                           for label in labels) / len(labels)
    transition_count = 0
    compared = 0
    for column_index, candidate in enumerate(row):
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        samples = [values[column_index] for values in following_rows
                   if column_index < len(values) and values[column_index] is not None]
        if samples:
            compared += 1
            if any(not isinstance(value, str) or bool(numeric_values(pd.Series([value])).notna().iloc[0])
                   for value in samples):
                transition_count += 1
    transition_ratio = transition_count / max(1, compared)
    return (text_ratio * 2.2 + unique_ratio * 1.2 + density * 1.2 + term_ratio * 2.4 + field_name_ratio * 2.0
            + transition_ratio * 1.6 + min(len(populated), 5) * 0.12)


def detect_data_bounds(worksheet: Any, max_columns: int, on_progress: Callable[[dict[str, Any]], None] | None = None,
                       current_sheet: int = 1, total_sheets: int = 1) -> dict[str, Any]:
    """Find non-empty worksheet bounds and a likely header without trusting used-range dimensions."""
    dimension_rows = max(1, int(worksheet.max_row or 1))
    nonempty_candidates: list[tuple[int, tuple[Any, ...]]] = []
    last_nonempty_row = 0
    actual_columns = 0
    for row_number, values in enumerate(worksheet.iter_rows(min_row=1, max_row=dimension_rows,
                                                              max_col=max_columns, values_only=True), start=1):
        if _nonempty_row(values):
            last_nonempty_row = row_number
            actual_columns = max(actual_columns, max((i + 1 for i, value in enumerate(values)
                                                       if value is not None and (not isinstance(value, str) or value.strip())), default=0))
            if len(nonempty_candidates) < 20:
                nonempty_candidates.append((row_number, values))
        if on_progress and row_number % 2000 == 0:
            on_progress({"stage": "header_detection", "current_sheet": current_sheet,
                         "total_sheets": total_sheets, "current_sheet_name": worksheet.title,
                         "sheet_progress": min(0.4, 0.4 * row_number / dimension_rows), "scanned_rows": row_number})

    if not last_nonempty_row:
        return {"header_row": None, "data_start_row": None, "data_end_row": None,
                "rows_available": 0, "rows_empty": 0, "trailing_empty_rows": dimension_rows,
                "columns_total": 0, "header_detection": {"status": "generated", "header_row_used": None,
                "header_source": "generated", "reason": "A worksheet não contém células preenchidas."}}

    candidates = []
    for number, values in nonempty_candidates:
        if number > 20:
            break
        following = [next_values for next_number, next_values in nonempty_candidates
                     if number < next_number <= number + 5]
        populated = [value for value in values if value is not None and str(value).strip()]
        if len(populated) < 1:
            continue
        score = _header_score(values, following)
        if len(populated) == 1 and not (set(re.findall(r"[^\W_]+", str(populated[0]).casefold())) & _HEADER_TERMS) \
                and not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", str(populated[0]).casefold()):
            score -= 1.5
        candidates.append((score, number, values))
    best = max(candidates, default=(0.0, 0, tuple()), key=lambda candidate: candidate[0])
    has_header = best[0] >= 5.7
    header_row = best[1] if has_header else None
    data_start = header_row + 1 if header_row else nonempty_candidates[0][0]
    data_end = last_nonempty_row
    # Internal blank positions stay visible as a quality metric, but are excluded from records and sampling.
    candidate_end = max((number for number, _ in nonempty_candidates), default=0)
    count_within_bounds = sum(number >= data_start for number, _ in nonempty_candidates)
    # Count the remainder in a bounded second pass without retaining cell contents.
    count_start = max(data_start, candidate_end + 1)
    if count_start <= data_end:
        for row_number, row in enumerate(worksheet.iter_rows(min_row=count_start, max_row=data_end,
                                                               max_col=max_columns, values_only=True), start=count_start):
            count_within_bounds += int(_nonempty_row(row))
            if on_progress and row_number % 2000 == 0:
                fraction = (row_number - count_start + 1) / max(1, data_end - count_start + 1)
                on_progress({"stage": "header_detection", "current_sheet": current_sheet,
                             "total_sheets": total_sheets, "current_sheet_name": worksheet.title,
                             "sheet_progress": 0.4 + 0.3 * min(1.0, fraction), "scanned_rows": row_number})
    rows_empty = max(0, (data_end - data_start + 1) - count_within_bounds)
    trailing_empty_rows = max(0, dimension_rows - data_end)
    if has_header:
        labels = [str(value).strip() if value is not None and str(value).strip() else f"Coluna {index + 1}"
                  for index, value in enumerate(best[2][:actual_columns])]
        header_detection = {"status": "detected", "header_row_used": header_row,
                            "header_source": "worksheet", "reason": "Linha identificada por preenchimento, texto, unicidade e evidência nas linhas seguintes."}
    else:
        labels = [f"Coluna {index + 1}" for index in range(actual_columns)]
        header_detection = {"status": "generated", "header_row_used": None, "header_source": "generated",
                            "reason": "Nenhum cabeçalho confiável foi identificado."}
    # Remove duplicate labels deterministically while preserving the original names.
    seen: dict[str, int] = {}
    for index, label in enumerate(labels):
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            labels[index] = f"{label} ({seen[label]})"
    return {"header_row": header_row, "data_start_row": data_start, "data_end_row": data_end,
            "rows_available": count_within_bounds, "rows_empty": rows_empty,
            "trailing_empty_rows": trailing_empty_rows, "columns_total": actual_columns,
            "header_labels": labels, "header_detection": header_detection}


def _read_xlsx(content: bytes, settings: Any, deadline: float,
               on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, pd.DataFrame]:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False, keep_vba=False)
    try:
        output: dict[str, pd.DataFrame] = {}
        worksheets = workbook.worksheets
        if on_progress:
            on_progress({"stage": "worksheet_detection", "current_sheet": 0,
                         "total_sheets": len(worksheets), "message": f"{len(worksheets)} worksheet(s) detectada(s)"})
        remaining_cells = settings.max_xlsx_profile_cells
        selected_worksheets = worksheets[:settings.max_tables_to_analyze]
        for sheet_index, worksheet in enumerate(selected_worksheets, start=1):
            try:
                if on_progress:
                    on_progress({"stage": "worksheet_analysis", "current_sheet": sheet_index,
                                 "total_sheets": len(worksheets), "current_sheet_name": worksheet.title,
                                 "message": f"Detectando cabeçalho e limites da aba '{worksheet.title}'"})
                max_columns_total = min(worksheet.max_column or 0, settings.max_columns_to_analyze)
                bounds = detect_data_bounds(worksheet, max(1, max_columns_total), on_progress,
                                            sheet_index, len(worksheets))
                if on_progress:
                    on_progress({"stage": "worksheet_analysis", "current_sheet": sheet_index,
                                 "total_sheets": len(worksheets), "current_sheet_name": worksheet.title,
                                 "sheet_progress": 0.7,
                                 "rows_available": bounds["rows_available"],
                                 "message": f"Aba '{worksheet.title}': {bounds['rows_available']} linhas disponíveis"})
                if time.monotonic() > deadline:
                    raise AnalysisError("A análise excedeu o tempo máximo configurado.")
                columns_total = bounds["columns_total"]
                columns_analyzed = min(columns_total, settings.max_columns_to_analyze)
                row_limit = min(_row_limit(columns_analyzed), remaining_cells // max(1, columns_analyzed))
                target = min(int(bounds["rows_available"]), row_limit)
                reservoir: list[tuple[Any, ...]] = []
                rng = random.Random(0)
                seen_rows = 0
                if bounds["data_start_row"] is not None:
                    for row_number, values in enumerate(worksheet.iter_rows(
                        min_row=bounds["data_start_row"], max_row=bounds["data_end_row"],
                        max_col=max(1, columns_analyzed), values_only=True), start=bounds["data_start_row"]):
                        if not _nonempty_row(values):
                            continue
                        seen_rows += 1
                        if len(reservoir) < target:
                            reservoir.append(values)
                        elif target:
                            replacement = rng.randrange(seen_rows)
                            if replacement < target:
                                reservoir[replacement] = values
                        if on_progress and row_number % 2000 == 0:
                            fraction = (row_number - bounds["data_start_row"] + 1) / max(
                                1, bounds["data_end_row"] - bounds["data_start_row"] + 1)
                            on_progress({"stage": "worksheet_analysis", "current_sheet": sheet_index,
                                         "total_sheets": len(worksheets), "current_sheet_name": worksheet.title,
                                         "sheet_progress": 0.7 + 0.3 * min(1.0, fraction),
                                         "scanned_rows": row_number})
                headers = bounds.get("header_labels") or [f"Coluna {index + 1}" for index in range(columns_analyzed)]
                headers = headers[:columns_analyzed]
                if reservoir and headers:
                    frame = pd.DataFrame(reservoir, columns=headers)
                else:
                    frame = pd.DataFrame(columns=headers)
                sampled = int(bounds["rows_available"]) > len(frame)
                remaining_cells = max(0, remaining_cells - len(frame) * columns_analyzed)
                worksheet_status = "completed_empty" if not bounds["rows_available"] else "completed" if len(frame) else "skipped"
                frame.attrs.update({"total_rows": int(bounds["rows_available"]), "rows_available": int(bounds["rows_available"]),
                                    "rows_analyzed": len(frame), "sampled": sampled,
                                    "sampling_method": "uniform_reservoir" if sampled else "none",
                                    "columns_total": columns_total, "columns_analyzed": columns_analyzed,
                                    "tables_total": len(worksheets), "worksheet_status": worksheet_status,
                                    "header_row_used": bounds["header_row"],
                                    "header_detection": bounds["header_detection"],
                                    "rows_empty": bounds["rows_empty"],
                                    "trailing_empty_rows": bounds["trailing_empty_rows"],
                                    "worksheet_error": "O limite combinado de células impediu a análise desta aba." if worksheet_status == "skipped" else None,
                                    "import_settings": {"reader": "openpyxl-read-only", "formulas": "cached-values-only"}})
                if on_progress:
                    on_progress({"stage": "worksheet_analysis", "current_sheet": sheet_index,
                                 "total_sheets": len(worksheets), "current_sheet_name": worksheet.title,
                                 "sheet_progress": 1.0, "message": f"Aba '{worksheet.title}' lida"})
            except AnalysisError:
                raise
            except Exception as exc:
                frame = pd.DataFrame()
                frame.attrs.update({"total_rows": 0, "rows_available": 0, "rows_analyzed": 0, "sampled": False,
                                    "columns_total": 0, "columns_analyzed": 0,
                                    "tables_total": len(worksheets), "worksheet_status": "failed",
                                    "header_detection": {"status": "generated", "header_row_used": None,
                                                         "header_source": "generated", "reason": "A leitura da aba falhou."},
                                    "rows_empty": 0, "trailing_empty_rows": 0,
                                    "worksheet_error": f"Falha de leitura da aba ({type(exc).__name__})."})
            output[worksheet.title] = frame
        return output
    finally:
        workbook.close()


def read_tables(
    content: bytes,
    file_type: str,
    csv_encoding: str | None,
    csv_delimiter: str = "auto",
    decimal_separator: str = "auto",
    header_mode: str = "auto",
    security_metadata: dict[str, Any] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, pd.DataFrame]:
    settings = get_settings()
    deadline = time.monotonic() + settings.analysis_timeout_seconds
    try:
        if file_type in {"xlsx", "xlsm"}:
            if security_metadata is None:
                from app.security.file_validation import inspect_xlsx_package
                inspect_xlsx_package(content)
            return _read_xlsx(content, settings, deadline, on_progress)

        options = detect_csv_options(content, csv_encoding or "utf-8")
        delimiter = options["delimiter"] if csv_delimiter == "auto" else csv_delimiter
        decimal = options["decimal"] if decimal_separator == "auto" else decimal_separator
        has_header = options["has_header"] if header_mode == "auto" else header_mode == "true"
        header_arg: int | None = 0 if has_header else None
        read_options = {"encoding": csv_encoding or "utf-8", "sep": delimiter, "decimal": decimal,
                        "thousands": "." if decimal == "," else None,
                        "header": header_arg, "engine": "python", "on_bad_lines": "error", "skip_blank_lines": False}
        header_frame = pd.read_csv(BytesIO(content), nrows=0 if has_header else 1, **read_options)
        total_columns = len(header_frame.columns)
        selected_columns = list(header_frame.columns[:settings.max_columns_to_analyze])
        # Count rows in bounded chunks, then load only the configured profile sample.
        total_rows = 0
        reader = pd.read_csv(BytesIO(content), chunksize=50000, **read_options)
        try:
            for chunk in reader:
                if time.monotonic() > deadline:
                    raise AnalysisError("A análise excedeu o tempo máximo configurado.")
                total_rows += len(chunk)
                if on_progress:
                    processed = reader.handles.handle.tell()
                    on_progress({"stage": "csv_reading", "stage_progress": min(1.0, processed / max(1, len(content))),
                                 "records_scanned": total_rows, "current_sheet": 1, "total_sheets": 1,
                                 "message": f"Contando registros CSV: {total_rows:,}"})
        finally:
            reader.close()
        row_limit = _row_limit(total_columns)
        frame = pd.read_csv(BytesIO(content), nrows=row_limit,
                            usecols=selected_columns, **read_options)
        if time.monotonic() > deadline:
            raise AnalysisError("A análise excedeu o tempo máximo configurado.")
        frame.attrs.update({"total_rows": total_rows, "rows_analyzed": len(frame),
                            "sampled": total_rows > len(frame), "columns_total": total_columns,
                            "columns_analyzed": len(frame.columns),
                            "import_settings": {"encoding": csv_encoding or "utf-8", "delimiter": delimiter,
                                                "decimal_separator": decimal, "header": has_header,
                                                "header_mode": header_mode, "delimiter_ambiguous": options["ambiguous_delimiter"],
                                                "header_ambiguous": options["ambiguous_header"]}})
        return {"Dados": frame}
    except (AnalysisError, FileValidationError):
        raise
    except Exception as exc:
        raise AnalysisError("O arquivo foi validado, mas não pôde ser analisado. Verifique a estrutura e tente novamente.") from exc
