"""Primary-key candidates: single columns and column pairs."""
from typing import Any

import pandas as pd

from app.core.text import tokens

KEY_NAME_TERMS = ("id", "codigo", "chave", "contrato", "numero", "matricula", "registro", "sku", "pedido", "processo")


def key_candidate_info(name: str, complete_pct: float, unique_pct: float, sampled: bool,
              inferred: str, role: str, table_name: str) -> tuple[bool, str | None, list[str], str]:
    reasons: list[str] = []
    if complete_pct < 95 or unique_pct < 95:
        return False, None, reasons, "not_candidate"
    reasons.append(f"{complete_pct:.1f}% preenchida")
    reasons.append(f"{unique_pct:.1f}% única")
    name_tokens = tokens(name)
    name_match = bool(name_tokens & set(KEY_NAME_TERMS)) or role in {"identifier", "code"}
    table_tokens = tokens(table_name)
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


def composite_keys(frame: pd.DataFrame, single_keys: set[str], sampled: bool) -> list[dict[str, Any]]:
    candidates = []
    if len(frame.columns) < 2 or frame.empty:
        return candidates
    eligible = []
    for name in frame.columns:
        series = frame[name]
        if tokens(str(name)) & {"custo", "cost", "risco", "risk", "valor", "value", "amount", "preco", "price",
                     "salario", "salary", "receita", "revenue", "margem", "margin", "rescisao",
                     "despesa", "expense", "faturamento", "rank", "ranking", "score", "point", "points",
                     "pontos", "nota", "total", "average", "avg", "media", "quantity", "quantidade",
                     "count", "percent", "percentage", "percentual", "rate", "taxa", "indice", "date",
                     "data", "datetime", "month", "ano", "year", "day"}:
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
                    "assessment": "possible_identifier",
                    "uniqueness_pct": round(unique_pct, 1),
                    "reasons": ["A combinação é altamente única na amostra avaliada; isso, isoladamente, não confirma uma chave.",
                                "Confirme a semântica e a regra de negócio antes de usá-la como identificador.",
                                "Avaliada sobre uma amostra." if sampled else "Sem nulos na combinação."],
                })
                if len(candidates) >= 5:
                    return candidates
    return candidates
