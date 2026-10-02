import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.exceptions import AnalysisError, FileValidationError
from app.security.file_validation import validate_upload
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
