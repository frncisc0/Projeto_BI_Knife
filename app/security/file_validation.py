import csv
import io
import zipfile
from pathlib import PurePath

from app.core.config import get_settings
from app.core.exceptions import FileValidationError


def validate_filename(filename: str | None) -> tuple[str, str]:
    if not filename or not filename.strip():
        raise FileValidationError("Informe um arquivo para análise.")
    # Use only the basename; never use this value to create a filesystem path.
    safe_name = PurePath(filename.replace("\\", "/")).name
    extension = PurePath(safe_name).suffix.lower()
    if extension not in get_settings().allowed_extensions:
        raise FileValidationError("Formato não permitido. Envie um arquivo .xlsx ou .csv.")
    return safe_name, extension


def display_filename(filename: str | None) -> str:
    """Keep a sanitized relative label for UI display; never use it as a path."""
    normalized = (filename or "arquivo").replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    if parts and parts[0].endswith(":"):
        parts = parts[1:]
    return "/".join(parts) or "arquivo"


def validate_upload(filename: str | None, content: bytes) -> tuple[str, str, str | None]:
    safe_name, extension = validate_filename(filename)
    settings = get_settings()
    if not content:
        raise FileValidationError("O arquivo está vazio.")
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise FileValidationError(f"O arquivo excede o limite de {settings.max_file_size_mb} MB.")
    if extension == ".xlsx":
        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise FileValidationError("O conteúdo não parece ser um arquivo XLSX válido.")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = archive.namelist()
                if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                    raise FileValidationError("O arquivo ZIP enviado não possui a estrutura de um XLSX.")
                if any(name.startswith("xl/externalLinks/") for name in names):
                    raise FileValidationError("Arquivos XLSX com vínculos externos não são aceitos.")
        except zipfile.BadZipFile as exc:
            raise FileValidationError("O arquivo XLSX está corrompido.") from exc
        return safe_name, "xlsx", None
    text, encoding = _decode_csv(content)
    try:
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if text.count(";") > text.count(",") else ","
    try:
        rows = csv.reader(io.StringIO(text), delimiter=delimiter)
        header = next(rows, None)
        if not header or not any(cell.strip() for cell in header):
            raise FileValidationError("O CSV não contém um cabeçalho válido.")
    except csv.Error as exc:
        raise FileValidationError("Não foi possível ler a estrutura do CSV.") from exc
    return safe_name, "csv", encoding


def _decode_csv(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            decoded = content.decode(encoding)
            if "\x00" in decoded:
                raise FileValidationError("O arquivo não parece ser um CSV de texto válido.")
            return decoded, encoding
        except UnicodeDecodeError:
            continue
    raise FileValidationError("Não foi possível identificar a codificação do CSV.")
