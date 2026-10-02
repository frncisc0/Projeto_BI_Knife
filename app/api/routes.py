import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.exceptions import AnalysisError, FileValidationError
from app.analyzers.relationship_analyzer import suggest_relationships
from app.security.file_validation import display_filename, validate_upload_detailed
from app.services.analysis_service import analyze_file
from app.services.report_service import report_payload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


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
                safe_name, file_type, encoding, security = validate_upload_detailed(upload.filename, content)
                analysis = analyze_file(filename or safe_name, file_type, content, encoding,
                                        csv_delimiter, decimal_separator, header_mode,
                                        relationship_frames=relationship_frames,
                                        relationship_budget=file_relationship_budget,
                                        relationship_prefix=f"{upload_index}:{filename or safe_name}",
                                        security_metadata=security)
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
    return {"results": results, "file_count": len(results), "total_bytes": batch_bytes,
            "relationships": [
                {**relation.model_dump(mode="json"),
                 "source_table": relation.source_table.split(":", 1)[1],
                 "target_table": relation.target_table.split(":", 1)[1]}
                for relation in relationships
            ]}
