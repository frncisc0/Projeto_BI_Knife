"""Executive PDF export from the finished report payload; never reads source files."""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any


def _safe(value: Any, fallback: str = "-") -> str:
    return escape(str(value if value is not None else fallback)).replace("\n", "<br/>")


def _reports(batch: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(str(item.get("filename") or item.get("analysis", {}).get("filename") or "Arquivo"), item["analysis"])
            for item in batch.get("results", []) if isinstance(item.get("analysis"), dict)]


def _status(value: Any) -> str:
    return {"completed": "Concluída", "partial": "Parcial", "failed": "Falha"}.get(str(value), str(value or "-"))


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
    severity_labels = {"critical": "Problema crítico", "attention": "Atenção", "information": "Informação"}
    type_labels = {"ranking": "Ranking", "comparison": "Comparação", "trend": "Evolução",
                   "kpi": "Indicador", "coverage": "Indicador derivado", "distribution": "Distribuição",
                   "outlier": "Ponto fora do padrão", "segmentation": "Segmentação", "detail_table": "Detalhamento"}
    for filename, report in reports:
        human = report.get("human_summary") or {}
        quality = report.get("quality", {})
        story.append(Paragraph("Resumo Executivo", styles["Section"]))
        story.append(Paragraph(_safe(human.get("executive_summary", f"Análise do arquivo {filename}.")), styles["BodyText"]))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Qualidade dos dados", styles["Heading3"]))
        story.append(Paragraph(_safe(human.get("data_quality_summary", quality.get("classification", "Qualidade não informada."))), styles["BodyText"]))
        components = human.get("quality_components", [])
        if components:
            component_rows = [["Aspecto", "Resultado", "O que significa"]]
            component_rows.extend([[item.get("name", "-"), f"{item.get('value', '-') }%", item.get("description", "-")]
                                   for item in components])
            story.append(_simple_table(component_rows, LongTable, TableStyle, Paragraph, styles,
                                       [37 * mm, 26 * mm, 100 * mm], repeat_rows=1))
        else:
            story.append(Paragraph(f"Qualidade geral: {_safe(quality.get('score', '-'))}/100 · "
                                   f"{_safe(quality.get('classification', '-'))}.", styles["SmallText"]))

        story.append(Paragraph("Principais descobertas", styles["Heading3"]))
        findings = human.get("key_findings", [])
        if findings:
            for item in findings[:6]:
                story.append(KeepTogether([Paragraph(
                    f"<b>{_safe(item.get('title'))}</b> · {_safe(item.get('importance'))} · {_safe(item.get('type'))}<br/>"
                    f"{_safe(item.get('description'))}<br/><font color='#617168'>Por que: {_safe(item.get('why'))}</font>",
                    styles["AlertText"]), Spacer(1, 2 * mm)]))
        else:
            story.append(Paragraph("Não há análises prioritárias com evidência suficiente para destacar.", styles["SmallText"]))

        story.append(Paragraph("Pontos de atenção", styles["Heading3"]))
        attention = human.get("attention_points", [])
        if attention:
            for point in attention[:12]:
                story.append(Paragraph(f"<b>{_safe(severity_labels.get(point.get('severity'), 'Informação'))}</b> · "
                                       f"{_safe(point.get('message'))}", styles["AlertText"]))
        else:
            story.append(Paragraph("Nenhum ponto de atenção foi registrado.", styles["SmallText"]))

        story.append(Paragraph("O que pode ser analisado", styles["Heading3"]))
        opportunities = human.get("analysis_opportunities", [])
        if opportunities:
            for group in opportunities:
                questions = group.get("questions", [])[:6]
                story.append(Paragraph(f"<b>{_safe(group.get('category'))}</b>: "
                                       f"{_safe(' · '.join(str(question) for question in questions))}", styles["SmallText"]))
        else:
            story.append(Paragraph("Não foram encontradas oportunidades com evidência suficiente.", styles["SmallText"]))

        story.append(Paragraph("Dashboard recomendado", styles["Heading3"]))
        blueprint = report.get("dashboard_blueprint") or {}
        story.append(Paragraph(_safe(human.get("dashboard_summary", blueprint.get("objective", "Não há recomendação de dashboard."))), styles["BodyText"]))
        if blueprint.get("audience"):
            story.append(Paragraph(f"Público: {_safe(blueprint.get('audience'))}", styles["SmallText"]))
        for page in blueprint.get("recommended_pages", [])[:5]:
            story.append(Paragraph(f"<b>{_safe(page.get('name'))}</b> — {_safe(page.get('purpose'))}", styles["SmallText"]))
        kpi_names = [item.get("name", "") for item in blueprint.get("kpis", [])[:6]]
        if kpi_names:
            story.append(Paragraph(f"Indicadores priorizados: {_safe(', '.join(kpi_names))}", styles["SmallText"]))
    story.append(PageBreak())
    story.append(Paragraph("Detalhes técnicos", styles["Section"]))
    story.append(Paragraph("A partir desta seção, o relatório apresenta estrutura, métricas, evidências e informações de segurança para revisão técnica.", styles["SmallText"]))
    story.extend([Paragraph("1. Resumo", styles["Section"]),
                  _metric_table([("Abas", total_sheets), ("Registros avaliados", total_rows),
                                 ("Colunas", total_columns), ("Tipos de pontos de atenção", len(all_alerts))], Table, TableStyle, colors, pale, styles),
                  Paragraph("O score resume regras heurísticas. Uma aba auxiliar, template ou destinada a preenchimento pode ter score baixo sem representar erro; interprete as dimensões e os alertas no contexto.", styles["SmallText"]),
                  Paragraph("2. Qualidade dos dados", styles["Section"])])
    for filename, report in reports:
        quality = report.get("quality", {})
        score = _safe(quality.get("score", "-"))
        story.append(Paragraph(f"{_safe(filename)} - {score}/100 · {_safe(quality.get('classification'))}", styles["Heading4"]))
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
            count_text = f" - {int(count):,} ocorrência(s)".replace(",", ".") if isinstance(count, (int, float)) and count else ""
            message = _safe(alert.get("message", "Ponto para revisão"))
            title = severity_names.get(alert.get("severity"), "Informação")
            affected = (f"<br/>Colunas afetadas: {_safe(alert.get('affected_columns'))}."
                        if alert.get("affected_columns") else "")
            recommendation = _safe(alert.get("recommendation", "Revise o contexto antes de interpretar como problema."))
            paragraph = Paragraph(f"<b>{title}{count_text}</b> · {message}{affected}<br/>Aba: {_safe(table.get('name'))}. "
                                  f"{recommendation}", styles["AlertText"])
            story.append(KeepTogether([paragraph, Spacer(1, 2 * mm)]))
    else:
        story.append(Paragraph("Nenhum alerta de qualidade foi registrado.", styles["BodyText"]))

    story.append(Paragraph("4. Abas analisadas", styles["Section"]))
    sheet_rows = [["Arquivo / aba", "Linhas disponíveis / avaliadas", "Colunas", "Qualidade", "Pontos de atenção"]]
    for filename, report in reports:
        for table in report.get("tables", []):
            alerts = sum(1 for alert in table.get("quality", {}).get("alerts", []) if alert.get("severity") != "ok")
            sheet_rows.append([f"{filename} / {table.get('name', '-')}",
                               f"{table.get('rows_available', table.get('rows', 0))} / {table.get('rows_analyzed', 0)}",
                               str(table.get("columns", 0)),
                               f"{table.get('quality', {}).get('classification', '-')} ({table.get('quality', {}).get('score', 0)}/100)",
                               str(alerts)])
    story.append(_simple_table(sheet_rows, LongTable, TableStyle, Paragraph, styles,
                               [55 * mm, 38 * mm, 17 * mm, 39 * mm, 27 * mm], repeat_rows=1))

    story.append(Paragraph("5. Estrutura das colunas", styles["Section"]))
    column_rows = [["Arquivo / aba / coluna", "Tipo físico", "Tipo inferido", "Papel", "Nulos"]]
    key_labels = {"strong_candidate": "Candidato forte", "possible_identifier": "Possível identificador",
                  "high_uniqueness_measure": "Medida única; não chave",
                  "high_uniqueness_unconfirmed": "Unicidade sem evidência", "not_candidate": "-"}
    for filename, report in reports:
        for table in report.get("tables", []):
            for column in table.get("column_analyses", []):
                label = f"{filename} / {table.get('name', '-')} / {column.get('name', '-')}"
                role = f"{column.get('semantic_role', '-')}\n{key_labels.get(column.get('key_assessment', 'not_candidate'), '-')}"
                column_rows.append([label, column.get("physical_type") or column.get("original_type", "-"),
                                    column.get("inferred_type", "-"), role,
                                    f"{column.get('null_count', 0)} ({column.get('null_pct', 0)}%)"])
    story.append(_simple_table(column_rows, LongTable, TableStyle, Paragraph, styles,
                               [61 * mm, 25 * mm, 37 * mm, 31 * mm, 22 * mm], repeat_rows=1))
    for filename, report in reports:
        for table in report.get("tables", []):
            for candidate in table.get("key_candidates", []):
                labels = " + ".join(str(name) for name in candidate.get("columns", []))
                reasons = "; ".join(candidate.get("reasons", []))
                story.append(Paragraph(f"Possível identificador em {_safe(filename)} / {_safe(table.get('name'))}: "
                                       f"{_safe(labels)} · {_safe(candidate.get('assessment', 'possible_identifier'))} · "
                                       f"{_safe(candidate.get('uniqueness_pct', '-'))}% único. {_safe(reasons)}",
                                       styles["SmallText"]))

    story.append(Paragraph("6. Relações potenciais", styles["Section"]))
    relationships = [(filename, relationship) for filename, report in reports
                     for relationship in report.get("relationships", [])]
    if relationships:
        relation_rows = [["Arquivo", "Origem", "Destino", "Correspondência", "Evidência"]]
        for filename, relationship in relationships:
            relation_rows.append([filename,
                                  f"{relationship.get('source_table')}.{relationship.get('source_column')}",
                                  f"{relationship.get('target_table')}.{relationship.get('target_column')}",
                                  f"{relationship.get('coverage_pct')}% · {relationship.get('cardinality')}",
                                  relationship.get("reason", "Possível relação; confirme a regra de negócio.")])
        story.append(_simple_table(relation_rows, LongTable, TableStyle, Paragraph, styles,
                                   [30 * mm, 35 * mm, 35 * mm, 29 * mm, 47 * mm], repeat_rows=1))
    else:
        story.append(Paragraph("Nenhuma relação com evidência suficiente foi sugerida.", styles["BodyText"]))

    story.append(Paragraph("7. Principais oportunidades de análise", styles["Section"]))
    for filename, report in reports:
        candidates = (report.get("insights") or {}).get("items", [])
        candidates = [item for item in candidates if item.get("priority") in {"high", "medium"}]
        candidates.sort(key=lambda item: (0 if item.get("priority") == "high" else 1, item.get("type", ""), item.get("title", "")))
        if not candidates:
            story.append(Paragraph(f"{_safe(filename)}: não há sugestões com evidência suficiente.", styles["SmallText"]))
            continue
        story.append(Paragraph(_safe(filename), styles["Heading4"]))
        for item in candidates[:8]:
            refs = [*item.get("dimensions", []), *item.get("measures", []), *item.get("dates", [])]
            fields = ", ".join(f"{ref.get('table')}.{ref.get('column')}" for ref in refs)
            story.append(KeepTogether([Paragraph(
                f"<b>{_safe(item.get('title'))}</b> · {_safe(item.get('priority'))} · confiança {_safe(item.get('confidence'))}<br/>"
                f"Pergunta: {_safe(item.get('business_question'))}<br/>Campos: {_safe(fields)}<br/>"
                f"Visual: {_safe(item.get('visual'))}<br/>Por que: {_safe(item.get('reason'))}", styles["AlertText"]),
                Spacer(1, 2 * mm)]))
        blueprint = report.get("dashboard_blueprint") or {}
        story.append(Paragraph("Blueprint sugerido de dashboard", styles["Heading4"]))
        for page in blueprint.get("recommended_pages", [])[:4]:
            story.append(Paragraph(f"• <b>{_safe(page.get('name'))}</b>: {_safe(page.get('purpose'))}", styles["SmallText"]))
        kpis = (report.get("kpis") or {}).get("suggested", [])
        kpi_names = [item.get("name", "") for item in kpis if item.get("priority") in {"high", "medium"}][:8]
        if kpi_names:
            story.append(Paragraph(f"KPIs candidatos: {_safe(', '.join(kpi_names))}", styles["SmallText"]))

    story.append(Paragraph("8. Segurança", styles["Section"]))
    checks = []
    for filename, report in reports:
        security = report.get("security") or {}
        formula_action = {"cached_values_only": "valores armazenados em cache; sem recálculo",
                          "not_applicable": "não aplicável"}.get(str(security.get("formulas_action")),
                                                                      str(security.get("formulas_action") or "não informado"))
        checks.append([filename,
                       "Arquivo original não alterado · Processado localmente · Macros: não executadas · Objetos: não executados · Relações externas: não seguidas · "
                       "Conexões: não acessadas/atualizadas · Fórmulas: "
                       f"{formula_action} · Relações externas detectadas: {int(security.get('external_relationship_count', 0) or 0)}.",
                       "Conteúdo potencialmente ativo detectado, mas não executado." if security.get("active_content_detected")
                       else "Nenhum conteúdo potencialmente ativo detectado."])
    story.append(_simple_table([["Arquivo", "Proteções", "Observação"], *checks], LongTable, TableStyle, Paragraph,
                               styles, [48 * mm, 81 * mm, 47 * mm], repeat_rows=1))
    story.append(Paragraph("9. Observações", styles["Section"]))
    story.append(Paragraph("Os resultados são heurísticos e podem refletir amostragem. Valores fora da faixa de 1,5 × IQR "
                           "podem ser legítimos e não representam necessariamente erros. Verifique as regras de negócio "
                           "antes de usar candidatos a identificador ou relacionamentos.", styles["BodyText"]))
    for _, report in reports:
        for warning in [*report.get("warnings", []), *report.get("security_warnings", [])][:30]:
            story.append(Paragraph("• " + _safe(warning), styles["SmallText"]))

    story.append(Paragraph("10. Anomalias", styles["Section"]))
    anomaly_rows = [["Arquivo", "Coluna", "Método", "Ocorrências", "Gravidade", "Descrição"]]
    for filename, report in reports:
        for anomaly in report.get("anomalies", []):
            anomaly_rows.append([filename, anomaly.get("column", "-"), anomaly.get("method", "-"),
                                 str(anomaly.get("count", 0)),
                                 severity_names.get(anomaly.get("severity"), "Informação"),
                                 anomaly.get("description", "Anomalia identificada.")])
    if len(anomaly_rows) == 1:
        story.append(Paragraph("Nenhuma anomalia foi registrada.", styles["BodyText"]))
    else:
        story.append(_simple_table(anomaly_rows, LongTable, TableStyle, Paragraph, styles,
                                   [30 * mm, 30 * mm, 29 * mm, 19 * mm, 21 * mm, 47 * mm], repeat_rows=1))

    story.append(Paragraph("11. Detalhes técnicos", styles["Section"]))
    technical_rows = [["Arquivo", "Tipo", "Tamanho", "Linhas analisadas / disponíveis", "Colunas", "Amostragem"]]
    for filename, report in reports:
        tables = report.get("tables", [])
        analyzed_rows = sum(int(table.get("rows_analyzed", 0) or 0) for table in tables)
        available_rows = sum(int(table.get("rows_available", table.get("rows", 0)) or 0) for table in tables)
        columns = sum(int(table.get("columns_analyzed", table.get("columns", 0)) or 0) for table in tables)
        sampled_tables = [table for table in tables if table.get("sampled")]
        sampling = (", ".join(sorted({str(table.get("sampling_method", "amostragem"))
                                     for table in sampled_tables})) if sampled_tables else "Não")
        technical_rows.append([filename, report.get("file_type", "-"),
                               f"{int(report.get('file_size_bytes', 0) or 0) / (1024 * 1024):.2f} MB",
                               f"{analyzed_rows} / {available_rows}", str(columns), sampling])
    story.append(_simple_table(technical_rows, LongTable, TableStyle, Paragraph, styles,
                               [43 * mm, 17 * mm, 22 * mm, 42 * mm, 17 * mm, 35 * mm], repeat_rows=1))
    for filename, report in reports:
        story.append(Paragraph(f"{_safe(filename)} - identificador da análise: {_safe(report.get('analysis_id'))}; "
                               f"duração: {_safe(_duration(report.get('processing_time_ms', 0)))}; "
                               f"abas registradas: {len(report.get('tables', []))}.", styles["SmallText"]))

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
