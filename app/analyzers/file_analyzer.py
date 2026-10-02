import csv
from io import BytesIO, StringIO
import re
import time
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from app.analyzers.statistics_analyzer import numeric_values
from app.core.config import get_settings
from app.core.exceptions import AnalysisError


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


def _read_xlsx(content: bytes, settings: Any, deadline: float) -> dict[str, pd.DataFrame]:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
    try:
        output: dict[str, pd.DataFrame] = {}
        worksheets = workbook.worksheets
        for worksheet in worksheets[:settings.max_tables_to_analyze]:
            max_columns_total = worksheet.max_column or 0
            max_columns = min(max_columns_total, settings.max_columns_to_analyze)
            total_rows = max(0, (worksheet.max_row or 0) - 1)
            row_limit = _row_limit(max_columns)
            rows = worksheet.iter_rows(
                min_row=1,
                max_row=min(worksheet.max_row or 0, row_limit + 1),
                max_col=max_columns,
                values_only=True,
            )
            values = list(rows)
            if time.monotonic() > deadline:
                raise AnalysisError("A análise excedeu o tempo máximo configurado.")
            if values:
                headers = [str(value).strip() if value is not None else "" for value in values[0]]
                frame = pd.DataFrame(values[1:], columns=headers)
            else:
                frame = pd.DataFrame()
            frame.attrs.update({"total_rows": total_rows, "rows_analyzed": len(frame),
                                "sampled": total_rows > len(frame), "columns_total": max_columns_total,
                                "columns_analyzed": max_columns, "tables_total": len(worksheets),
                                "import_settings": {"reader": "openpyxl", "formulas": "cached-values-only"}})
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
) -> dict[str, pd.DataFrame]:
    settings = get_settings()
    deadline = time.monotonic() + settings.analysis_timeout_seconds
    try:
        if file_type == "xlsx":
            return _read_xlsx(content, settings, deadline)

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
        for chunk in pd.read_csv(BytesIO(content), chunksize=50000, **read_options):
            if time.monotonic() > deadline:
                raise AnalysisError("A análise excedeu o tempo máximo configurado.")
            total_rows += len(chunk)
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
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError("O arquivo foi validado, mas não pôde ser analisado. Verifique a estrutura e tente novamente.") from exc
