"""Heuristic classification of a table as fact, dimension or reference."""
import pandas as pd


def table_kind(name: str, frame: pd.DataFrame) -> tuple[str, str, str]:
    normalized = name.casefold()
    if any(word in normalized for word in ("venda", "pedido", "transa", "movimento", "fato", "order", "sale")):
        return "provável tabela fato/transacional", "medium", "O nome da aba sugere eventos ou transações."
    if any(word in normalized for word in ("cliente", "produto", "fornecedor", "cadastro", "dimens", "reference", "ref_")):
        return "provável dimensão/cadastro", "medium", "O nome da aba sugere cadastro ou entidade de referência."
    if len(frame) and len(frame.columns) <= 5 and all(frame[column].nunique(dropna=True) / max(1, len(frame)) > 0.8 for column in frame.columns):
        return "possível tabela de referência", "low", "A tabela é compacta e possui alta unicidade por coluna."
    return "tipo indeterminado", "low", "Não há evidência suficiente para classificar esta tabela."
