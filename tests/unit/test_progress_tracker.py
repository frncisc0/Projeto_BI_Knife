import asyncio
from io import BytesIO
import time

from openpyxl import Workbook
from starlette.datastructures import UploadFile

from app.api.routes import analysis_progress, start_analysis_with_progress
from app.main import app
from app.services.analysis_service import analyze_file
from app.services.progress_tracker import ProgressTracker


def test_progress_tracker_uses_work_events_and_is_monotonic():
    tracker = ProgressTracker()
    initial = tracker.start("book.xlsx", total_files=1)
    assert initial["progress"] == 0
    assert initial["status"] == "running"

    tracker._started = time.monotonic() - 3
    state = tracker.update({"stage": "worksheet_analysis", "current_sheet": 6,
                            "total_sheets": 8, "sheet_progress": 0.5,
                            "current_sheet_name": "Processos"})
    assert 0 < state["progress"] < 100
    assert state["estimated_remaining_seconds"] is not None
    assert state["current_sheet"] == 6
    previous = state["progress"]
    state = tracker.update({"stage": "validating", "current_sheet": 1, "total_sheets": 8})
    assert state["progress"] >= previous
    completed = tracker.complete()
    assert completed["progress"] == 100
    assert completed["estimated_remaining_seconds"] == 0
    assert completed["status"] == "completed"


def test_progress_tracker_failure_preserves_actual_progress():
    tracker = ProgressTracker()
    tracker.start("data.csv")
    current = tracker.update({"stage": "security"})
    failed = tracker.fail("Falha controlada")
    assert failed["status"] == "error"
    assert failed["progress"] == current["progress"]
    assert failed["estimated_remaining_seconds"] is None


def test_csv_backend_emits_parse_and_quality_progress_events():
    events = []
    analyze_file("small.csv", "csv", b"id,valor\n1,10\n2,20\n", "utf-8",
                 progress_callback=events.append)
    assert any(event["stage"] == "csv_reading" for event in events)
    assert any(event["stage"] == "quality_analysis" for event in events)


def test_progress_api_routes_are_registered_without_changing_batch_query_contract():
    paths = app.openapi()["paths"]
    assert "/api/analyze-progress" in paths
    assert "/api/analyze-jobs/{job_id}/progress" in paths
    parameters = paths["/api/analyze-batch"]["post"].get("parameters", [])
    assert not any(parameter["name"] == "progress_callback" for parameter in parameters)


def test_progress_api_returns_job_and_final_batch_report():
    workbook = Workbook()
    for index in range(8):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = "Aba" + str(index + 1)
        sheet.append(["id", "valor"])
        sheet.append([index + 1, (index + 1) * 20])
    buffer = BytesIO()
    workbook.save(buffer)
    upload = UploadFile(filename="sample.xlsx", file=BytesIO(buffer.getvalue()))
    started = asyncio.run(start_analysis_with_progress([upload], "auto", "auto", "auto"))
    assert started["job_id"]
    deadline = time.monotonic() + 10
    state = None
    while time.monotonic() < deadline:
        state = analysis_progress(started["job_id"])
        if state["status"] in {"completed", "error"}:
            break
        time.sleep(0.01)

    assert state is not None
    assert state["status"] == "completed"
    assert state["progress"] == 100
    assert len(state["result"]["results"][0]["analysis"]["tables"]) == 8
    assert state["result"]["results"][0]["analysis"]["settings"]["worksheets_total"] == 8
