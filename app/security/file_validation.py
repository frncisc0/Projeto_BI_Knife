import csv
import io
import zipfile
import xml.etree.ElementTree as ElementTree
from pathlib import PurePath

from app.core.config import get_settings
from app.core.exceptions import FileValidationError


def _reject_unsafe_xlsx_xml(archive: zipfile.ZipFile, names: list[str]) -> None:
    """Reject DTD/entity declarations before an XLSX XML parser sees them."""
    markers = (b"<!DOCTYPE", b"<!ENTITY")
    for name in names:
        if not name.casefold().endswith((".xml", ".rels")):
            continue
        carry = b""
        with archive.open(name) as xml_stream:
            while chunk := xml_stream.read(64 * 1024):
                window = carry + chunk
                upper_window = window.upper()
                if b"\x00" in window or any(marker in upper_window for marker in markers):
                    raise FileValidationError("O XLSX contém declarações XML não permitidas e não será processado.")
                carry = window[-16:]


def validate_filename(filename: str | None) -> tuple[str, str]:
    if not filename or not filename.strip():
        raise FileValidationError("Informe um arquivo para análise.")
    # Use only the basename; never use this value to create a filesystem path.
    safe_name = PurePath(filename.replace("\\", "/")).name
    extension = PurePath(safe_name).suffix.lower()
    if extension not in get_settings().allowed_extensions:
        raise FileValidationError("Formato não permitido. Envie um arquivo .xlsx, .xlsm ou .csv.")
    return safe_name, extension


def display_filename(filename: str | None) -> str:
    """Keep a sanitized relative label for UI display; never use it as a path."""
    normalized = (filename or "arquivo").replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    if parts and parts[0].endswith(":"):
        parts = parts[1:]
    return "/".join(parts) or "arquivo"


def inspect_xlsx_package(content: bytes) -> dict[str, object]:
    """Validate an OOXML package and report detectable active/external features."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise FileValidationError("O arquivo ZIP enviado não possui a estrutura de uma planilha Excel.")
            uncompressed_limit = get_settings().max_xlsx_uncompressed_mb * 1024 * 1024
            if sum(item.file_size for item in archive.infolist()) > uncompressed_limit:
                raise FileValidationError(f"O XLSX excede o limite expandido de {get_settings().max_xlsx_uncompressed_mb} MB.")
            _reject_unsafe_xlsx_xml(archive, names)

            lowered = [name.casefold() for name in names]
            content_types: set[str] = set()
            if any(name.endswith("/vbaproject.bin") or name == "xl/vbaproject.bin" for name in lowered):
                content_types.add("macro")
            if "xl/connections.xml" in lowered:
                content_types.add("connection_definition")
            if any(name.startswith("xl/externallinks/") for name in lowered):
                content_types.add("external_link")
            if any(name.startswith("xl/embeddings/") for name in lowered):
                content_types.add("embedded_object")
            if any(name.startswith("xl/activex/") for name in lowered):
                content_types.add("activeX_control")

            external_relationship_count = 0
            for name in names:
                if not name.casefold().endswith(".rels"):
                    continue
                info = archive.getinfo(name)
                if info.file_size > 1024 * 1024:
                    raise FileValidationError("O XLSX contém metadados de relacionamento inesperadamente grandes.")
                try:
                    relationship_xml = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError as exc:
                    raise FileValidationError("O arquivo Excel contém relacionamentos inválidos.") from exc
                external_relationship_count += sum(
                    element.attrib.get("TargetMode", "").casefold() == "external"
                    for element in relationship_xml.iter()
                )
            if external_relationship_count:
                content_types.add("external_relationship")
            return {
                "active_content_detected": bool(content_types),
                "active_content_types": sorted(content_types),
                "external_relationships_detected": external_relationship_count > 0,
                "external_relationship_count": external_relationship_count,
            }
    except zipfile.BadZipFile as exc:
        raise FileValidationError("O conteúdo não parece ser um arquivo Excel Open XML válido ou está corrompido.") from exc


def validate_upload_detailed(filename: str | None, content: bytes) -> tuple[str, str, str | None, dict[str, object] | None]:
    safe_name, extension = validate_filename(filename)
    settings = get_settings()
    if not content:
        raise FileValidationError("O arquivo está vazio.")
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise FileValidationError(f"O arquivo excede o limite de {settings.max_file_size_mb} MB.")
    if extension in {".xlsx", ".xlsm"}:
        security = inspect_xlsx_package(content)
        return safe_name, extension[1:], None, security
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
    return safe_name, "csv", encoding, None


def validate_upload(filename: str | None, content: bytes) -> tuple[str, str, str | None]:
    """Compatibility wrapper for callers that need only file type and encoding."""
    safe_name, file_type, encoding, _ = validate_upload_detailed(filename, content)
    return safe_name, file_type, encoding


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
