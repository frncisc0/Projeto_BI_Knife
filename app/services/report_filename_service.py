from __future__ import annotations

import re
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Any

_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                           *(f"LPT{i}" for i in range(1, 10))}


def _safe_base_name(source_name: str | None) -> str:
    basename = PureWindowsPath(str(source_name or "arquivo").replace("/", "\\")).name
    stem = PureWindowsPath(basename).stem
    stem = _INVALID_WINDOWS_CHARS.sub("_", stem).rstrip(" .")
    if not stem:
        stem = "arquivo"
    if stem.split(".", 1)[0].upper() in _RESERVED_WINDOWS_NAMES:
        stem = f"_{stem}"
    return stem


def _analysis_datetime(payload: dict[str, Any], now: datetime | None = None) -> datetime:
    timestamps = []
    for item in payload.get("results", []):
        analysis = item.get("analysis") if isinstance(item, dict) else None
        value = analysis.get("analyzed_at") if isinstance(analysis, dict) else None
        if value:
            try:
                timestamps.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
            except ValueError:
                continue
    return max(timestamps, key=lambda value: value.timestamp()) if timestamps else (now or datetime.now().astimezone())


def report_filename(payload: dict[str, Any], extension: str, *, now: datetime | None = None) -> str:
    """Build a safe, contextual download name without touching the Downloads folder."""
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    timestamp = _analysis_datetime(payload, now).strftime("%Y-%m-%d_%H-%M-%S")
    if len(results) > 1:
        stem = f"BI-Swiss-Knife_analise-combinada_{timestamp}"
    else:
        result = results[0] if results and isinstance(results[0], dict) else {}
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        source = analysis.get("filename") or result.get("filename") or "arquivo"
        stem = f"{_safe_base_name(source)}_{timestamp}_BI-Swiss-Knife"
    suffix = str(extension or "").lstrip(".")
    if not suffix or not re.fullmatch(r"[A-Za-z0-9]+", suffix):
        raise ValueError("A extensão do relatório é inválida.")
    return f"{stem}.{suffix}"


def content_disposition(filename: str) -> str:
    """Return an RFC 5987 attachment header safe for Unicode filenames."""
    safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$&+-.^_`|~"
    encoded = "".join(chr(byte) if byte in safe else f"%{byte:02X}" for byte in filename.encode("utf-8"))
    return f"attachment; filename*=UTF-8''{encoded}"
