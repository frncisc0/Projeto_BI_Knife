import asyncio
import json
from io import BytesIO
import logging

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.exceptions import AnalysisError, FileValidationError
from app.analyzers.relationship_analyzer import suggest_relationships
from app.security.file_validation import display_filename, validate_upload_detailed
from app.services.analysis_service import analyze_file
from app.services.report_service import report_payload
from app.services.html_report_service import render_html_report
from app.services.pdf_report_service import render_pdf_report
from app.services.progress_tracker import create_analysis_job, get_analysis_job
from starlette.datastructures import UploadFile as StoredUploadFile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _validate_report_payload(payload: dict) -> None:
    """Bound local report generation and require the existing batch-result shape."""
    try:
        encoded_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Formato do relatório inválido.") from exc
    max_bytes = min(50 * 1024 * 1024, get_settings().report_max_bytes * max(1, get_settings().max_files_per_batch))
    if encoded_size > max_bytes:
        raise HTTPException(status_code=413, detail="O relatório é grande demais para exportação.")
    if not isinstance(payload.get("results"), list):
        raise HTTPException(status_code=400, detail="O resultado da análise não possui formato reconhecido.")


@router.post("/report-html")
def export_html_report(payload: dict = Body(...)) -> Response:
    _validate_report_payload(payload)
    content = render_html_report(payload)
    return Response(content=content, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="bi-swiss-knife-relatorio.html"',
                             "Cache-Control": "no-store"})


@router.post("/report-pdf")
def export_pdf_report(payload: dict = Body(...)) -> Response:
    _validate_report_payload(payload)
    try:
        content = render_pdf_report(payload)
    except ModuleNotFoundError as exc:
        if exc.name == "reportlab" or (exc.name and exc.name.startswith("reportlab.")):
            logger.error("PDF export dependency unavailable; dependency=%s", exc.name)
            raise HTTPException(
                status_code=503,
                detail="Dependência ReportLab ausente. Execute 'python -m pip install -r requirements.txt' no ambiente virtual.",
            ) from exc
        logger.error("PDF export import failure; error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Falha interna ao carregar a exportação PDF.") from exc
    except ImportError as exc:
        logger.error("PDF export import failure; error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Falha interna ao carregar a exportação PDF.") from exc
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="bi-swiss-knife-relatorio-executivo.pdf"',
                             "Cache-Control": "no-store"})


def _validate_csv_options(delimiter: str, decimal_separator: str, header_mode: str) -> None:
    if delimiter not in {"auto", ",", ";", "\t", "|"}:
        raise FileValidationError("Delimitador CSV inválido.")
    if decimal_separator not in {"auto", ".", ","}:
        raise FileValidationError("Separador decimal inválido.")
    if header_mode not in {"auto", "true", "false"}:
        raise FileValidationError("Configuração de cabeçalho inválida.")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "privacy": "local-only"}


@router.post("/analyze")
async def analyze(
    upload: UploadFile = File(...),
    csv_delimiter: str = Form("auto"),
    decimal_separator: str = Form("auto"),
    header_mode: str = Form("auto"),
) -> dict:
    try:
        _validate_csv_options(csv_delimiter, decimal_separator, header_mode)
        max_bytes = get_settings().max_file_size_mb * 1024 * 1024
        chunks: list[bytes] = []
        total = 0
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise FileValidationError(f"O arquivo excede o limite de {get_settings().max_file_size_mb} MB.")
            chunks.append(chunk)
        content = b"".join(chunks)
        chunks.clear()
        filename, file_type, encoding, security = validate_upload_detailed(upload.filename, content)
        return report_payload(analyze_file(filename, file_type, content, encoding, csv_delimiter,
                                           decimal_separator, header_mode, security_metadata=security))
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unexpected analysis failure; error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Não foi possível concluir a análise. Verifique o arquivo e tente novamente.") from exc
    finally:
        await upload.close()


async def _read_upload(upload: UploadFile, file_limit: int, batch_remaining: int, batch_limit_mb: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > file_limit:
            raise FileValidationError("O arquivo excede o limite individual configurado.")
        if total > batch_remaining:
            raise FileValidationError(f"A seleção excedeu o limite total de {batch_limit_mb} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def _apply_integrity_quality(quality: dict, report_settings: dict, integrity_pct: float) -> None:
    """Recalculate the existing weighted score after batch relationships are known."""
    weights = report_settings.get("quality_weights", {})
    dimensions = {
        "completeness": quality["completeness_pct"],
        "uniqueness": quality["uniqueness_pct"],
        "consistency": quality["consistency_pct"],
        "validity": quality["validity_pct"],
        "integrity": integrity_pct,
    }
    total_weight = sum(weights.get(name, 0) for name in dimensions)
    if not total_weight:
        return
    score = round(sum(dimensions[name] * weights.get(name, 0) for name in dimensions) / total_weight, 1)
    thresholds = report_settings.get("quality_thresholds", {})
    quality["score"] = score
    quality["classification"] = (
        "Excelente" if score >= thresholds.get("excellent", 95)
        else "Boa" if score >= thresholds.get("good", 85)
        else "Atenção" if score >= thresholds.get("attention", 65)
        else "Crítica"
    )
    quality["integrity_pct"] = round(integrity_pct, 1)
    quality["integrity_assessed"] = True
    if integrity_pct < 95:
        quality.setdefault("alerts", []).append({
            "severity": "attention", "count": round(100 - integrity_pct, 1),
            "message": f"Candidatos a relacionamento apresentam {100 - integrity_pct:.1f}% de valores sem correspondência estimada.",
        })


@router.post("/analyze-batch")
async def analyze_batch(
    uploads: list[UploadFile] = File(...),
    csv_delimiter: str = Form("auto"),
    decimal_separator: str = Form("auto"),
    header_mode: str = Form("auto"),
) -> dict:
    """Analyze multiple local uploads independently and retain per-file errors."""
    return await _analyze_batch_impl(uploads, csv_delimiter, decimal_separator, header_mode)


async def _analyze_batch_impl(
    uploads: list[UploadFile],
    csv_delimiter: str,
    decimal_separator: str,
    header_mode: str,
    progress_callback=None,
) -> dict:
    """Shared batch implementation for synchronous and progress-job routes."""
    settings = get_settings()
    try:
        _validate_csv_options(csv_delimiter, decimal_separator, header_mode)
    except FileValidationError as exc:
        for upload in uploads:
            await upload.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not uploads:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um arquivo.")
    if len(uploads) > settings.max_files_per_batch:
        for upload in uploads:
            await upload.close()
        raise HTTPException(status_code=400, detail=f"Selecione no máximo {settings.max_files_per_batch} arquivos por vez.")

    batch_limit = settings.max_batch_size_mb * 1024 * 1024
    file_limit = settings.max_file_size_mb * 1024 * 1024
    batch_bytes = 0
    results: list[dict] = []
    relationship_frames: dict = {}
    relationship_remaining = settings.max_batch_relationship_cells
    csv_uploads_remaining = sum((upload.filename or "").casefold().endswith(".csv") for upload in uploads)
    over_batch_limit = False
    try:
        for upload_index, upload in enumerate(uploads):
            filename = display_filename(upload.filename)
            if progress_callback:
                progress_callback({"stage": "validating", "current_file": upload_index + 1,
                                   "total_files": len(uploads), "filename": filename,
                                   "message": f"Validando arquivo {upload_index + 1} de {len(uploads)}"})
            is_csv_upload = (upload.filename or "").casefold().endswith(".csv")
            budget_share = relationship_remaining // max(1, csv_uploads_remaining) if is_csv_upload else 0
            file_relationship_budget = [budget_share] if is_csv_upload else None
            if is_csv_upload:
                csv_uploads_remaining -= 1
            if over_batch_limit:
                results.append({"filename": filename, "analysis": None,
                                "error": f"A seleção excedeu o limite total de {settings.max_batch_size_mb} MB."})
                continue
            try:
                content = await _read_upload(upload, file_limit, batch_limit - batch_bytes, settings.max_batch_size_mb)
                batch_bytes += len(content)
                if progress_callback:
                    progress_callback({"stage": "security", "current_file": upload_index + 1,
                                       "total_files": len(uploads), "filename": filename,
                                       "message": "Verificando a segurança do arquivo"})
                safe_name, file_type, encoding, security = validate_upload_detailed(upload.filename, content)
                def report_progress(event: dict) -> None:
                    if progress_callback:
                        progress_callback({**event, "current_file": upload_index + 1,
                                           "total_files": len(uploads), "filename": filename,
                                           "file_type": file_type})
                analysis = analyze_file(filename or safe_name, file_type, content, encoding,
                                        csv_delimiter, decimal_separator, header_mode,
                                        relationship_frames=relationship_frames,
                                        relationship_budget=file_relationship_budget,
                                        relationship_prefix=f"{upload_index}:{filename or safe_name}",
                                        security_metadata=security, progress_callback=report_progress)
                results.append({"filename": filename or safe_name, "analysis": report_payload(analysis), "error": None})
            except FileValidationError as exc:
                results.append({"filename": filename, "analysis": None, "error": str(exc)})
                if "limite total" in str(exc):
                    over_batch_limit = True
            except AnalysisError as exc:
                results.append({"filename": filename, "analysis": None, "error": str(exc)})
            except Exception as exc:
                logger.error("Unexpected batch analysis failure; error_type=%s", type(exc).__name__)
                results.append({"filename": filename, "analysis": None,
                                "error": "Não foi possível analisar este arquivo. Verifique-o e tente novamente."})
            finally:
                if file_relationship_budget is not None:
                    relationship_remaining -= budget_share - file_relationship_budget[0]
                await upload.close()
    finally:
        for upload in uploads:
            await upload.close()
    relationships = suggest_relationships(relationship_frames, []) if len(relationship_frames) > 1 else []
    relationships_by_file: dict[int, list] = {}
    for relation in relationships:
        relation_payload = relation.model_dump(mode="json")
        try:
            source_index = int(relation.source_table.split(":", 1)[0])
            target_index = int(relation.target_table.split(":", 1)[0])
        except (ValueError, IndexError):
            continue
        relation_payload["source_table"] = relation.source_table.split(":", 1)[1]
        relation_payload["target_table"] = relation.target_table.split(":", 1)[1]
        for result_index in {source_index, target_index}:
            if 0 <= result_index < len(results) and results[result_index].get("analysis"):
                report = results[result_index]["analysis"]
                report["relationships"].append(relation_payload)
                relationships_by_file.setdefault(result_index, []).append(relation)
    for result_index, report_relations in relationships_by_file.items():
        report = results[result_index]["analysis"]
        integrity = sum(item.coverage_pct for item in report_relations) / len(report_relations)
        _apply_integrity_quality(report["quality"], report["settings"], integrity)
        for table in report["tables"]:
            _apply_integrity_quality(table["quality"], report["settings"], integrity)
    relationship_frames.clear()
    if progress_callback:
        progress_callback({"stage": "finalizing", "current_file": len(uploads),
                           "total_files": len(uploads), "message": "Finalizando relatório e relacionamentos"})
    return {"results": results, "file_count": len(results), "total_bytes": batch_bytes,
            "relationships": [
                {**relation.model_dump(mode="json"),
                 "source_table": relation.source_table.split(":", 1)[1],
                 "target_table": relation.target_table.split(":", 1)[1]}
                for relation in relationships
            ]}


@router.post("/analyze-progress")
async def start_analysis_with_progress(
    uploads: list[UploadFile] = File(...),
    csv_delimiter: str = Form("auto"),
    decimal_separator: str = Form("auto"),
    header_mode: str = Form("auto"),
) -> dict[str, str]:
    """Accept local uploads and start a background job whose polling state follows backend work."""
    settings = get_settings()
    try:
        _validate_csv_options(csv_delimiter, decimal_separator, header_mode)
    except FileValidationError as exc:
        for upload in uploads:
            await upload.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not uploads:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um arquivo.")
    if len(uploads) > settings.max_files_per_batch:
        for upload in uploads:
            await upload.close()
        raise HTTPException(status_code=400, detail=f"Selecione no máximo {settings.max_files_per_batch} arquivos por vez.")
    batch_limit = settings.max_batch_size_mb * 1024 * 1024
    file_limit = settings.max_file_size_mb * 1024 * 1024
    stored_files: list[tuple[str, bytes]] = []
    total_bytes = 0
    try:
        for upload in uploads:
            content = await _read_upload(upload, file_limit, batch_limit - total_bytes, settings.max_batch_size_mb)
            total_bytes += len(content)
            stored_files.append((upload.filename or "arquivo", content))
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        for upload in uploads:
            await upload.close()

    async def run_batch(progress_callback):
        stored_uploads = [StoredUploadFile(filename=name, file=BytesIO(content)) for name, content in stored_files]
        return await _analyze_batch_impl(stored_uploads, csv_delimiter, decimal_separator, header_mode,
                                         progress_callback=progress_callback)

    def worker(progress_callback):
        return asyncio.run(run_batch(progress_callback))

    job_id = create_analysis_job(display_filename(uploads[0].filename) if uploads else "",
                                 len(stored_files), worker)
    return {"job_id": job_id, "status": "running"}


@router.get("/analyze-jobs/{job_id}/progress")
def analysis_progress(job_id: str) -> dict:
    job = get_analysis_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Análise não encontrada ou expirada.")
    return job
