import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.exceptions import AnalysisError, FileValidationError
from app.security.file_validation import display_filename, validate_upload
from app.services.analysis_service import analyze_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "privacy": "local-only"}


@router.post("/analyze")
async def analyze(upload: UploadFile = File(...)) -> dict:
    try:
        max_bytes = get_settings().max_file_size_mb * 1024 * 1024
        chunks: list[bytes] = []
        total = 0
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise FileValidationError(f"O arquivo excede o limite de {get_settings().max_file_size_mb} MB.")
            chunks.append(chunk)
        content = b"".join(chunks)
        filename, file_type, encoding = validate_upload(upload.filename, content)
        return analyze_file(filename, file_type, content, encoding).model_dump(mode="json")
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected analysis failure")
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


@router.post("/analyze-batch")
async def analyze_batch(uploads: list[UploadFile] = File(...)) -> dict:
    """Analyze multiple local uploads independently and retain per-file errors."""
    settings = get_settings()
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
    over_batch_limit = False
    try:
        for upload in uploads:
            filename = display_filename(upload.filename)
            if over_batch_limit:
                results.append({"filename": filename, "analysis": None,
                                "error": f"A seleção excedeu o limite total de {settings.max_batch_size_mb} MB."})
                continue
            try:
                content = await _read_upload(upload, file_limit, batch_limit - batch_bytes, settings.max_batch_size_mb)
                batch_bytes += len(content)
                safe_name, file_type, encoding = validate_upload(upload.filename, content)
                analysis = analyze_file(filename or safe_name, file_type, content, encoding)
                results.append({"filename": filename or safe_name, "analysis": analysis.model_dump(mode="json"), "error": None})
            except FileValidationError as exc:
                results.append({"filename": filename, "analysis": None, "error": str(exc)})
                if "limite total" in str(exc):
                    over_batch_limit = True
            except AnalysisError as exc:
                results.append({"filename": filename, "analysis": None, "error": str(exc)})
            except Exception:
                logger.exception("Unexpected failure analyzing batch file")
                results.append({"filename": filename, "analysis": None,
                                "error": "Não foi possível analisar este arquivo. Verifique-o e tente novamente."})
            finally:
                await upload.close()
    finally:
        for upload in uploads:
            await upload.close()
    return {"results": results, "file_count": len(results), "total_bytes": batch_bytes}
