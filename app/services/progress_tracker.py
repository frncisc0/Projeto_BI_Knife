from concurrent.futures import ThreadPoolExecutor
import threading
import time
import uuid
from typing import Any, Callable


class ProgressTracker:
    """Thread-safe progress state driven only by completed backend work."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = 0.0
        self._progress = 0
        self._state: dict[str, Any] = {}

    def start(self, filename: str = "", total_files: int = 1) -> dict[str, Any]:
        with self._lock:
            self._started = time.monotonic()
            self._progress = 0
            self._state = {"progress": 0, "stage": "initializing", "message": "Inicializando análise",
                           "current_sheet": 0, "total_sheets": 0, "current_sheet_name": None,
                           "filename": filename, "current_file": 1, "total_files": total_files,
                           "elapsed_seconds": 0.0, "estimated_remaining_seconds": None, "status": "running"}
            return dict(self._state)

    @staticmethod
    def _file_fraction(event: dict[str, Any]) -> float:
        stage = event.get("stage", "")
        sheet = int(event.get("current_sheet", 0) or 0)
        total = max(1, int(event.get("total_sheets", 0) or 0))
        sheet_fraction = max(0.0, min(1.0, float(event.get("sheet_progress", 0.0) or 0.0)))
        if stage == "validating":
            return 0.03
        if stage == "security":
            return 0.08
        if stage in {"opening_workbook", "file_reading"}:
            return 0.15
        if stage == "csv_reading":
            fraction = max(0.0, min(1.0, float(event.get("stage_progress", 0.0) or 0.0)))
            return 0.15 + 0.63 * fraction
        if stage == "worksheet_detection":
            return 0.18
        if stage in {"header_detection", "worksheet_analysis"}:
            return 0.20 + 0.58 * ((max(0, sheet - 1) + sheet_fraction) / total)
        if stage == "quality_analysis":
            return 0.80 + 0.13 * (min(total, max(0, sheet)) / total)
        if stage == "consolidating_results":
            return 0.96
        if stage == "finalizing":
            return 0.99
        return 0.10

    def update(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not self._state or self._state.get("status") != "running":
                return dict(self._state)
            current_file = max(1, int(event.get("current_file", self._state.get("current_file", 1))))
            total_files = max(1, int(event.get("total_files", self._state.get("total_files", 1))))
            within_file = self._file_fraction(event)
            calculated = int(5 + 90 * ((current_file - 1 + within_file) / total_files))
            self._progress = max(self._progress, min(99, calculated))
            elapsed = max(0.0, time.monotonic() - self._started)
            remaining = None
            if self._progress >= 15 and elapsed >= 2:
                remaining = round(elapsed * (100 - self._progress) / max(1, self._progress), 1)
            self._state.update({key: value for key, value in event.items()
                                if key not in {"sheet_progress", "scanned_rows"}})
            self._state.update({"progress": self._progress, "current_file": current_file,
                                "total_files": total_files, "elapsed_seconds": round(elapsed, 1),
                                "estimated_remaining_seconds": remaining, "status": "running"})
            return dict(self._state)

    def complete(self) -> dict[str, Any]:
        with self._lock:
            elapsed = max(0.0, time.monotonic() - self._started)
            self._progress = 100
            self._state.update({"progress": 100, "stage": "completed", "message": "Análise concluída",
                                "elapsed_seconds": round(elapsed, 1), "estimated_remaining_seconds": 0,
                                "status": "completed"})
            return dict(self._state)

    def fail(self, message: str = "Não foi possível concluir a análise.") -> dict[str, Any]:
        with self._lock:
            elapsed = max(0.0, time.monotonic() - self._started)
            self._state.update({"progress": self._progress, "stage": self._state.get("stage", "error"),
                                "message": message, "elapsed_seconds": round(elapsed, 1),
                                "estimated_remaining_seconds": None, "status": "error"})
            return dict(self._state)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            elapsed = max(0.0, time.monotonic() - self._started) if self._started else 0.0
            result = dict(self._state)
            result["elapsed_seconds"] = round(elapsed, 1)
            if result.get("status") == "running" and self._progress >= 15 and elapsed >= 2:
                result["estimated_remaining_seconds"] = round(
                    elapsed * (100 - self._progress) / max(1, self._progress), 1)
            return result


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bi-analysis")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def create_analysis_job(filename: str, total_files: int,
                        worker: Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]]) -> str:
    job_id = str(uuid.uuid4())
    tracker = ProgressTracker()
    tracker.start(filename, total_files)
    with _jobs_lock:
        # Keep the in-memory job registry bounded; old finished reports are disposable.
        finished = [key for key, value in _jobs.items() if value["progress"].snapshot().get("status") != "running"]
        for old_job in finished[:-19]:
            _jobs.pop(old_job, None)
        _jobs[job_id] = {"progress": tracker, "result": None}

    def run() -> None:
        try:
            result = worker(tracker.update)
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["result"] = result
            tracker.complete()
        except Exception as exc:
            # Error text may contain parser context or user data; expose only the exception class.
            tracker.fail(f"A análise falhou ({type(exc).__name__}).")

    _executor.submit(run)
    return job_id


def get_analysis_job(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        progress = job["progress"].snapshot()
        result = job["result"] if progress.get("status") == "completed" else None
        return {"job_id": job_id, **progress, "result": result}
