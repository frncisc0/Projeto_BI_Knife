"""Executive PDF export from the finished report payload; never reads source files."""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any


def _safe(value: Any, fallback: str = "—") -> str:
    return escape(str(value if value is not None else fallback)).replace("\n", "<br/>")


def _reports(batch: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(str(item.get("filename") or item.get("analysis", {}).get("filename") or "Arquivo"), item["analysis"])
            for item in batch.get("results", []) if isinstance(item.get("analysis"), dict)]


def _status(value: Any) -> str:
    return {"completed": "Concluída", "partial": "Parcial", "failed": "Falha"}.get(str(value), str(value or "—"))


def _duration(value: Any) -> str:
    try:
        seconds = max(0, int(value)) / 1000
    except (TypeError, ValueError):
        seconds = 0
    if seconds >= 60:
        return f"{int(seconds // 60):02d}:{int(seconds % 60):02d} min"
    return f"{seconds:.1f} s".replace(".", ",")


def render_pdf_report(batch: dict[str, Any]) -> bytes:
    """Build a compact executive PDF from existing JSON fields only."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    green = colors.HexColor("#176B3D")
    pale = colors.HexColor("#EEF6F0")
    ink = colors.HexColor("#17231D")
    muted = colors.HexColor("#617168")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=24, leading=29, textColor=ink, alignment=TA_LEFT, spaceAfter=4))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=15, leading=19, textColor=green, spaceBefore=13, spaceAfter=8,
                              keepWithNext=True))
    styles.add(ParagraphStyle(name="SmallText", parent=styles["BodyText"], fontSize=8.5,
                              leading=12, textColor=muted))
    styles.add(ParagraphStyle(name="TableText", parent=styles["BodyText"], fontSize=8,
                              leading=10, textColor=ink, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="AlertText", parent=styles["BodyText"], fontSize=9,
                              leading=13, textColor=ink, spaceAfter=3))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
                            topMargin=19 * mm, bottomMargin=17 * mm,
                            title="Relatório de Diagnóstico de Dados - BI Swiss Knife",
                            author="BI Swiss Knife")
    story: list[Any] = []
    reports = _reports(batch)
    total_sheets = sum(len(report.get("tables", [])) for _, report in reports)
    total_rows = sum(int(table.get("rows_analyzed", 0) or 0)
                     for _, report in reports for table in report.get("tables", []))
    total_columns = sum(int(table.get("columns", 0) or 0)
                        for _, report in reports for table in report.get("tables", []))
    all_alerts = [(table, alert) for _, report in reports for table in report.get("tables", [])
                  for alert in table.get("quality", {}).get("alerts", []) if alert.get("severity") != "ok"]

    story.extend([Paragraph("BI SWISS KNIFE", styles["SmallText"]), Spacer(1, 3 * mm),
                  Paragraph("Relatório de Diagnóstico de Dados", styles["ReportTitle"]),
                  Paragraph("Resumo executivo gerado localmente a partir do resultado da análise.", styles["SmallText"]),
                  Spacer(1, 6 * mm)])
    for filename, report in reports:
        story.extend([Paragraph(f"Arquivo: {_safe(filename)}", styles["Heading3"]),
                      Paragraph(f"Data da análise: {_safe(report.get('analyzed_at'))} &nbsp; | &nbsp; "
                                f"Tempo: {_safe(_duration(report.get('processing_time_ms', 0)))} &nbsp; | &nbsp; "
                                f"Status: {_safe(_status(report.get('status')))}", styles["SmallText"])])
    story.extend([Paragraph("1. Resumo", styles["Section"]),
                  _metric_table([("Abas", total_sheets), ("Registros analisados", total_rows),
                                 ("Colunas", total_columns), ("Alertas", len(all_alerts))], Table, TableStyle, colors, pale, styles),
                  Paragraph("2. Qualidade dos dados", styles["Section"])])
    for filename, report in reports:
        quality = report.get("quality", {})
        score = _safe(quality.get("score", "—"))
        story.append(Paragraph(f"{_safe(filename)} — {score}/100 · {_safe(quality.get('classification'))}", styles["Heading4"]))
        dimensions = [("Dimensão", "Resultado"),
                      ("Completude", f"{_safe(quality.get('completeness_pct'))}%"),
                      ("Unicidade", f"{_safe(quality.get('uniqueness_pct'))}%"),
                      ("Consistência", f"{_safe(quality.get('consistency_pct'))}%"),
                      ("Validade", f"{_safe(quality.get('validity_pct'))}%")]
        if quality.get("integrity_assessed"):
            dimensions.append(("Integridade", f"{_safe(quality.get('integrity_pct'))}%"))
        story.append(_simple_table(dimensions, Table, TableStyle, Paragraph, styles, [67 * mm, 70 * mm]))

    story.append(Paragraph("3. Principais pontos de atenção", styles["Section"]))
    severity_names = {"critical": "Crítico", "attention": "Atenção", "information": "Informação"}
    if all_alerts:
        for table, alert in all_alerts[:30]:
            count = alert.get("count")
            count_text = f" — {int(count):,} ocorrência(s)".replace(",", ".") if isinstance(count, (int, float)) and count else ""
            message = _safe(alert.get("message", "Ponto para revisão"))
            title = severity_names.get(alert.get("severity"), "Informação")
            paragraph = Paragraph(f"<b>{title}{count_text}</b> · {message}<br/>Aba: {_safe(table.get('name'))}. "
                                  "Revise o contexto antes de interpretar como problema.", styles["AlertText"])
            story.append(KeepTogether([paragraph, Spacer(1, 2 * mm)]))
    else:
        story.append(Paragraph("Nenhum alerta de qualidade foi registrado.", styles["BodyText"]))

    story.append(Paragraph("4. Abas analisadas", styles["Section"]))
    sheet_rows = [["Arquivo / aba", "Linhas", "Colunas", "Qualidade", "Alertas"]]
    for filename, report in reports:
        for table in report.get("tables", []):
            alerts = sum(1 for alert in table.get("quality", {}).get("alerts", []) if alert.get("severity") != "ok")
            sheet_rows.append([f"{filename} / {table.get('name', '—')}",
                               str(table.get("rows_analyzed", 0)), str(table.get("columns", 0)),
                               f"{table.get('quality', {}).get('classification', '—')} ({table.get('quality', {}).get('score', 0)}/100)",
                               str(alerts)])
    story.append(_simple_table(sheet_rows, LongTable, TableStyle, Paragraph, styles,
                               [76 * mm, 25 * mm, 19 * mm, 39 * mm, 17 * mm], repeat_rows=1))

    story.append(Paragraph("5. Estrutura das colunas", styles["Section"]))
    column_rows = [["Arquivo / aba / coluna", "Tipo físico", "Tipo inferido", "Papel", "Nulos"]]
    key_labels = {"strong_candidate": "Candidato forte", "possible_identifier": "Possível identificador",
                  "high_uniqueness_measure": "Medida única; não chave",
                  "high_uniqueness_unconfirmed": "Unicidade sem evidência", "not_candidate": "—"}
    for filename, report in reports:
        for table in report.get("tables", []):
            for column in table.get("column_analyses", []):
                label = f"{filename} / {table.get('name', '—')} / {column.get('name', '—')}"
                role = f"{column.get('semantic_role', '—')}\n{key_labels.get(column.get('key_assessment', 'not_candidate'), '—')}"
                column_rows.append([label, column.get("physical_type") or column.get("original_type", "—"),
                                    column.get("inferred_type", "—"), role,
                                    f"{column.get('null_count', 0)} ({column.get('null_pct', 0)}%)"])
    story.append(_simple_table(column_rows, LongTable, TableStyle, Paragraph, styles,
                               [61 * mm, 25 * mm, 37 * mm, 31 * mm, 22 * mm], repeat_rows=1))

    story.append(Paragraph("6. Segurança", styles["Section"]))
    checks = []
    for filename, report in reports:
        security = report.get("security") or {}
        formula_action = {"cached_values_only": "valores armazenados em cache; sem recálculo",
                          "not_applicable": "não aplicável"}.get(str(security.get("formulas_action")),
                                                                      str(security.get("formulas_action") or "não informado"))
        checks.append([filename,
                       "Arquivo original não alterado · Processado localmente · Macros: não executadas · Objetos: não executados · Relações externas: não seguidas · "
                       "Conexões: não acessadas/atualizadas · Fórmulas: "
                       f"{formula_action}.",
                       "Conteúdo potencialmente ativo detectado, mas não executado." if security.get("active_content_detected")
                       else "Nenhum conteúdo potencialmente ativo detectado."])
    story.append(_simple_table([["Arquivo", "Proteções", "Observação"], *checks], LongTable, TableStyle, Paragraph,
                               styles, [48 * mm, 81 * mm, 47 * mm], repeat_rows=1))
    story.append(Paragraph("7. Observações", styles["Section"]))
    story.append(Paragraph("Os resultados são heurísticos e podem refletir amostragem. Valores fora da faixa de 1,5 × IQR "
                           "podem ser legítimos e não representam necessariamente erros. Verifique as regras de negócio "
                           "antes de usar candidatos a identificador ou relacionamentos.", styles["BodyText"]))
    for _, report in reports:
        for warning in [*report.get("warnings", []), *report.get("security_warnings", [])][:30]:
            story.append(Paragraph("• " + _safe(warning), styles["SmallText"]))

    def page_chrome(canvas: Any, doc_obj: Any) -> None:
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(colors.HexColor("#DBE4DD"))
        canvas.line(17 * mm, 13 * mm, width - 17 * mm, 13 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(muted)
        canvas.drawString(17 * mm, 8 * mm, "BI Swiss Knife · relatório local")
        canvas.drawRightString(width - 17 * mm, 8 * mm, f"Página {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)
    return buffer.getvalue()


def _metric_table(metrics: list[tuple[str, Any]], table_cls: Any, style_cls: Any,
                  colors: Any, pale: Any, styles: Any) -> Any:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph

    data = [[Paragraph(f"<font color='#176B3D'><b>{_safe(value)}</b></font><br/><font size='8'>{_safe(label)}</font>",
                       styles["BodyText"]) for label, value in metrics]]
    table = table_cls(data, colWidths=[(A4[0] - 34 * mm) / len(metrics)] * len(metrics))
    table.setStyle(style_cls([("BACKGROUND", (0, 0), (-1, -1), pale), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#DBE4DD")),
                              ("INNERGRID", (0, 0), (-1, -1), .5, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                              ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    return table


def _simple_table(data: list[list[Any]], table_cls: Any, style_cls: Any, paragraph_cls: Any,
                  styles: Any, widths: list[float], repeat_rows: int = 0) -> Any:
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph

    rows = []
    for row_index, row in enumerate(data):
        rows.append([Paragraph("<b>" + _safe(cell) + "</b>", styles["TableText"]) if row_index == 0
                     else Paragraph(_safe(cell), styles["TableText"]) for cell in row])
    table = table_cls(rows, colWidths=widths, repeatRows=repeat_rows)
    table.setStyle(style_cls([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF6F0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#176B3D")),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#DBE4DD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFCFA")]),
    ]))
    return table
