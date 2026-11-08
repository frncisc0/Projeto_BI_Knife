"""Text normalization shared by analyzers and discovery layers."""
import re
import unicodedata


def fold(value: object) -> str:
    """Casefold and strip accents: 'Preço Médio' -> 'preco medio'."""
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def tokens(value: object) -> set[str]:
    """Alphanumeric tokens of a folded name: 'Nome_Cliente' -> {'nome', 'cliente'}."""
    return set(re.findall(r"[a-z0-9]+", fold(value)))
