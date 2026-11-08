"""Characterization tests: freeze the full report produced today.

These tests do not claim the output is *correct* (that is the job of
tests/golden); they guarantee that a refactoring does not change it.
The v3.1.0 decomposition of ``analyze_file`` must keep every snapshot equal.

When a change is *intended* to alter the report, regenerate deliberately and
review the diff in the pull request:

    BI_UPDATE_SNAPSHOTS=1 python -m pytest tests/characterization
"""
import difflib
import json
import os
from pathlib import Path

import pytest

from app.security.file_validation import validate_upload_detailed
from app.services.analysis_service import analyze_file
from app.services.report_service import report_payload

INPUTS = Path(__file__).parents[1] / "golden" / "inputs"
SNAPSHOTS = Path(__file__).parent / "snapshots"
VOLATILE_KEYS = {"analysis_id", "analyzed_at", "processing_time_ms"}
UPDATE = os.getenv("BI_UPDATE_SNAPSHOTS") == "1"


def _normalize(value):
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items() if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)  # protect against last-digit differences between platforms
    return value


def _report(name: str) -> str:
    content = (INPUTS / name).read_bytes()
    safe_name, file_type, encoding, security = validate_upload_detailed(name, content)
    report = report_payload(analyze_file(safe_name, file_type, content, encoding, security_metadata=security))
    return json.dumps(_normalize(report), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name", sorted(path.name for path in INPUTS.iterdir() if path.suffix in {".csv", ".xlsx"}))
def test_report_matches_snapshot(name):
    actual = _report(name)
    snapshot = SNAPSHOTS / f"{name}.json"
    if UPDATE or not snapshot.exists():
        snapshot.write_text(actual, encoding="utf-8")
        pytest.skip(f"snapshot gravado: {snapshot.name}")
    expected = snapshot.read_text(encoding="utf-8")
    if actual != expected:
        diff = "\n".join(list(difflib.unified_diff(expected.splitlines(), actual.splitlines(),
                                                   "snapshot", "atual", lineterm=""))[:60])
        pytest.fail(f"O relatório de {name} mudou. Se a mudança for intencional, regenere com "
                    f"BI_UPDATE_SNAPSHOTS=1 e revise o diff no PR.\n{diff}")
