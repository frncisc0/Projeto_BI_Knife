"""Weighted data-quality score and alerts for a table or a whole file."""
from app.core.config import get_settings
from app.models.analysis_models import QualityAnalysis


def classify_quality(score: float, excellent: float, good: float, attention: float) -> str:
    """Map a 0-100 score to the classification shown to the user."""
    return ("Excelente" if score >= excellent else "Boa" if score >= good
            else "Atenção" if score >= attention else "Baixa")


def quality_score(rows: int, columns: int, null_count: int, invalid_count: int, duplicate_rows: int,
             cells_override: int | None = None, inconsistent_columns: int = 0,
             integrity_pct: float | None = None, affected_null_columns: list[str] | None = None,
             affected_invalid_columns: list[str] | None = None) -> QualityAnalysis:
    settings = get_settings()
    cells = max(1, cells_override if cells_override is not None else rows * columns)
    no_structure = rows == 0 or columns == 0
    completeness = 0.0 if no_structure else max(0.0, 100 - null_count / cells * 100)
    uniqueness = max(0.0, 100 - duplicate_rows / max(1, rows) * 100)
    validity = max(0.0, 100 - invalid_count / max(1, cells - null_count) * 100)
    consistency = max(0.0, 100 - inconsistent_columns / max(1, columns) * 100)
    dimensions = {
        "completeness": (completeness, settings.quality_completeness_weight),
        "uniqueness": (uniqueness, settings.quality_uniqueness_weight),
        "consistency": (consistency, settings.quality_consistency_weight),
        "validity": (validity, settings.quality_validity_weight),
    }
    if integrity_pct is not None:
        dimensions["integrity"] = (integrity_pct, settings.quality_integrity_weight)
    total_weight = sum(weight for _, weight in dimensions.values()) or 1
    score = round(sum(value * weight for value, weight in dimensions.values()) / total_weight, 1)
    score = max(0.0, min(100.0, score))
    classification = "Atenção" if no_structure else classify_quality(
        score, settings.quality_excellent_threshold, settings.quality_good_threshold,
        settings.quality_attention_threshold)
    alerts: list[dict[str, str | int | float]] = []
    if null_count:
        alerts.append({"severity": "information", "count": null_count,
                       "message": f"{null_count} valores ausentes ({100 - completeness:.1f}%); avalie se a ausência é esperada para estas colunas.",
                       "affected_columns": ", ".join(affected_null_columns or []),
                       "recommendation": "Confirme se a ausência é esperada para o processo e para as colunas indicadas."})
    if duplicate_rows:
        alerts.append({"severity": "attention", "count": duplicate_rows,
                       "message": f"{duplicate_rows} linhas repetidas foram encontradas.",
                       "recommendation": "Verifique se as repetições são esperadas antes de removê-las."})
    if invalid_count:
        alert_columns = affected_invalid_columns or []
        alerts.append({"severity": "attention", "count": invalid_count,
                       "message": f"{invalid_count} valores diferem do tipo inferido em {len(alert_columns)} coluna(s); verifique o padrão identificado.",
                       "affected_columns": ", ".join(alert_columns),
                       "recommendation": "Revise as colunas indicadas; a diferença pode ser legítima ou decorrer da inferência de tipo."})
    if inconsistent_columns:
        alerts.append({"severity": "attention", "count": inconsistent_columns,
                       "message": f"{inconsistent_columns} colunas apresentam mistura de tipos ou valores incompatíveis.",
                       "recommendation": "Confira as colunas e confirme se os diferentes formatos são válidos para o processo."})
    if integrity_pct is not None and integrity_pct < 95:
        alerts.append({"severity": "attention", "count": round(100 - integrity_pct, 1),
                       "message": f"Candidatos a relacionamento apresentam {100 - integrity_pct:.1f}% de valores sem correspondência estimada."})
    if not alerts and not no_structure:
        alerts.append({"severity": "ok", "count": 0, "message": "Nenhum alerta básico foi identificado pelas regras atuais."})
    if no_structure:
        alerts.append({"severity": "attention", "count": 0, "message": "A tabela não possui estrutura de dados para avaliação.",
                       "recommendation": "Confirme se a aba é intencionalmente vazia, auxiliar ou destinada a preenchimento futuro."})
    return QualityAnalysis(score=score, classification=classification, completeness_pct=round(completeness, 1),
                           uniqueness_pct=round(uniqueness, 1), consistency_pct=round(consistency, 1),
                           validity_pct=round(validity, 1), integrity_pct=round(integrity_pct, 1) if integrity_pct is not None else None,
                           integrity_assessed=integrity_pct is not None, alerts=alerts)
