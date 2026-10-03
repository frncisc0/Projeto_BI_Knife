import re
import unicodedata

import pandas as pd
from app.analyzers.statistics_analyzer import numeric_values


IDENTIFIER_TERMS = ("id", "codigo", "código", "chave", "contrato", "numero", "número", "cpf", "cnpj")
SENSITIVE_NAME_CATEGORIES = {
    "cpf": {"cpf"}, "cnpj": {"cnpj"}, "telefone": {"telefone", "celular", "phone", "mobile"},
    "email": {"email", "mail"}, "rg": {"rg"}, "documento": {"documento", "document", "national_id", "ssn"},
}


def sensitivity_details(column_name: str, series: pd.Series | None = None, physical: str | None = None,
                        inferred: str | None = None, role: str | None = None,
                        confidence: str | None = None) -> tuple[str | None, str | None, str]:
    normalized = unicodedata.normalize("NFKD", column_name.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for category, terms in SENSITIVE_NAME_CATEGORIES.items():
        if tokens & terms:
            return f"O nome da coluna identifica diretamente um dado pessoal ({category}).", category, "high"
    # Content-pattern detection is limited to e-mail text. Numeric formatting alone
    # cannot distinguish phone/document identifiers from amounts, ranks, or scores.
    if (series is not None and physical == "string" and inferred in {"categórico", "texto"}
            and role in {"text", "category", "unknown"}):
        sample = series.dropna().astype(str).str.strip().head(1000)
        if len(sample) >= 2:
            match_rate = sample.str.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", case=False).mean()
            if match_rate >= 0.8:
                pattern_confidence = "high" if match_rate >= 0.95 and len(sample) >= 5 and confidence == "high" else "medium"
                return "Os valores de texto têm formato consistente de e-mail.", "email", pattern_confidence
    return None, None, "low"


def sensitive_reason(column_name: str, series: pd.Series | None = None) -> str | None:
    return sensitivity_details(column_name, series, physical_type(series) if series is not None else None,
                               infer_type(series, column_name) if series is not None else None,
                               None, None)[0]


def infer_type(series: pd.Series, column_name: str = "") -> str:
    values = series.dropna()
    if values.empty:
        return "vazio"
    normalized_name = column_name.casefold()
    text_values = values.astype(str).str.strip()
    if text_values.str.endswith("%").mean() >= 0.8 or "percent" in normalized_name or "percentual" in normalized_name:
        return "percentual"
    if text_values.str.contains(r"R\$|\$|€|£", regex=True).mean() >= 0.5 or any(token in normalized_name for token in ("valor", "preco", "preço", "salario", "salário", "custo", "receita", "amount")):
        if pd.api.types.is_numeric_dtype(series.dtype) or numeric_values(values).notna().mean() >= 0.8:
            return "moeda"
    if pd.api.types.is_bool_dtype(series.dtype):
        return "booleano"
    if pd.api.types.is_integer_dtype(series.dtype):
        if _has_identifier_term(normalized_name) and series.nunique(dropna=True) / max(1, len(series)) >= 0.5:
            return "identificador"
        return "inteiro"
    if pd.api.types.is_numeric_dtype(series.dtype):
        return "decimal"
    numeric = numeric_values(values)
    if not numeric.empty and numeric.notna().mean() >= 0.8:
        if _has_identifier_term(normalized_name) and numeric.nunique() / max(1, len(values)) >= 0.5:
            return "identificador"
        return "numérico (texto)"
    parsed_dates = pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=True)
    if parsed_dates.notna().mean() >= 0.8:
        return "data/hora (texto)" if (parsed_dates.dt.hour != 0).any() else "data"
    if text_values.str.casefold().isin({"true", "false", "yes", "no", "sim", "não", "nao"}).mean() >= 0.8:
        return "booleano"
    return "categórico"


def type_confidence(series: pd.Series, inferred_type: str) -> str:
    if inferred_type == "vazio":
        return "low"
    if inferred_type in {"identificador", "moeda", "percentual", "numérico (texto)", "data/hora (texto)"}:
        return "medium"
    if pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype) or pd.api.types.is_datetime64_any_dtype(series.dtype):
        return "high"
    non_null = series.dropna()
    if inferred_type in {"data", "booleano"} and len(non_null) > 0:
        return "medium"
    return "medium" if len(non_null) >= 5 else "low"


def type_reason(series: pd.Series, column_name: str, inferred_type: str) -> str:
    values = series.dropna()
    if inferred_type == "vazio":
        return "A coluna não contém valores não nulos na amostra analisada."
    if inferred_type == "identificador":
        return "Tipo numérico com alta unicidade e nome compatível com identificador." \
            if _has_identifier_term(column_name.casefold()) else "Alta unicidade sugere um identificador; confirme a regra de negócio."
    if inferred_type == "moeda":
        return "Valores numéricos e/ou nome da coluna sugerem medida monetária."
    if inferred_type == "percentual":
        return "Valores ou nome da coluna sugerem percentual."
    if "numérico (texto)" == inferred_type:
        rate = numeric_values(values).notna().mean() * 100
        return f"{rate:.1f}% dos valores de texto podem ser convertidos em números."
    if "data" in inferred_type:
        rate = pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=True).notna().mean() * 100
        return f"{rate:.1f}% dos valores correspondem a datas interpretáveis."
    if inferred_type == "booleano":
        return "Os valores são booleanos ou correspondem a rótulos booleanos conhecidos."
    if inferred_type in {"inteiro", "decimal"}:
        return "O tipo numérico foi inferido pelo leitor do arquivo."
    return "Os valores não atenderam aos critérios de tipo numérico, data ou booleano; foram tratados como categoria."


def physical_type(series: pd.Series) -> str:
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_numeric_dtype(dtype):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if isinstance(dtype, pd.CategoricalDtype):
        return "category"
    if pd.api.types.is_string_dtype(dtype) or dtype == object:
        return "string"
    return "unknown"


def semantic_role(series: pd.Series, column_name: str, inferred_type: str) -> tuple[str, str]:
    """Suggest a broad column role, with confidence kept separate from type."""
    values = series.dropna()
    if values.empty:
        return "unknown", "low"
    name = column_name.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", name))
    identifier_terms = set(IDENTIFIER_TERMS) | {"sku", "code", "cod", "id"}
    code_terms = {"code", "cod", "codigo", "código", "sku", "cep", "zip"}
    if tokens & code_terms:
        return "code", "medium"
    if tokens & identifier_terms:
        return "identifier", "high" if inferred_type == "identificador" else "medium"
    if "data/hora" in inferred_type:
        return "datetime", "medium"
    if "data" in inferred_type:
        return "date", "medium"
    if inferred_type == "booleano":
        return "boolean", "medium"
    if inferred_type in {"moeda", "percentual", "inteiro", "decimal"}:
        return "measure", "medium" if len(values) >= 5 else "low"
    if inferred_type == "numérico (texto)":
        return "measure", "low"
    text = values.astype(str).str.strip()
    unique_ratio = values.nunique(dropna=True) / max(1, len(values))
    if unique_ratio <= 0.5:
        return "category", "medium" if len(values) >= 5 else "low"
    if text.str.len().median() >= 40:
        return "text", "medium"
    if unique_ratio >= 0.9 and len(values) >= 5:
        return "text", "low"
    return "unknown", "low"


def _has_identifier_term(name: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", name))
    return bool(tokens & set(IDENTIFIER_TERMS))
