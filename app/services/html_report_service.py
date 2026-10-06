"""Self-contained offline HTML reports derived from existing analysis payloads."""

from __future__ import annotations

from html import escape
from typing import Any


def _text(value: Any, fallback: str = "—") -> str:
    return escape(str(value if value is not None else fallback), quote=True)


def _number(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def _status(value: Any) -> str:
    return {"completed": "Concluída", "completed_empty": "Concluída sem registros",
            "partial": "Parcial", "failed": "Falha", "error": "Erro", "skipped": "Ignorada"}.get(str(value), str(value or "—"))


def _duration(value: Any) -> str:
    try:
        seconds = max(0, int(value)) / 1000
    except (TypeError, ValueError):
        seconds = 0
    if seconds >= 60:
        return f"{int(seconds // 60):02d}:{int(seconds % 60):02d} min"
    return f"{seconds:.1f} s".replace(".", ",")


def _reports(batch: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(str(item.get("filename") or item.get("analysis", {}).get("filename") or "Arquivo"), item["analysis"])
            for item in batch.get("results", []) if isinstance(item.get("analysis"), dict)]


def _alerts(quality: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in quality.get("alerts", []) if item.get("severity") != "ok"]


def _alert_html(alert: dict[str, Any], table_name: str = "") -> str:
    severity = str(alert.get("severity", "information"))
    if severity not in {"critical", "attention", "information"}:
        severity = "information"
    labels = {"critical": "Crítico", "attention": "Atenção", "information": "Informação"}
    count = alert.get("count")
    message = _text(alert.get("message", "Ponto para revisão"))
    quantity = f"<strong>{_number(count)} ocorrências</strong>" if isinstance(count, (int, float)) and count else ""
    context = f"<span class=\"muted\">Aba: {_text(table_name)}</span>" if table_name else ""
    advice = _text(alert.get("recommendation")) if alert.get("recommendation") else "Verifique o contexto da coluna antes de usar o campo em relatórios ou relacionamentos." \
        if severity in {"critical", "attention"} else "Considere se o resultado é esperado para o processo analisado."
    affected = (_text(alert.get("affected_columns")) if alert.get("affected_columns")
                else "")
    return (f'<article class="alert {severity}"><span class="badge">{labels.get(severity, "Informação")}</span>'
            f'<div><h4>{message}</h4>{quantity}{context}'
            f'{f"<p>Colunas afetadas: {affected}</p>" if affected else ""}<p>{advice}</p></div></article>')


def _quality_bars(quality: dict[str, Any]) -> str:
    dimensions = [("Completude", quality.get("completeness_pct")),
                  ("Unicidade", quality.get("uniqueness_pct")),
                  ("Consistência", quality.get("consistency_pct")),
                  ("Validade", quality.get("validity_pct"))]
    if quality.get("integrity_assessed"):
        dimensions.append(("Integridade", quality.get("integrity_pct")))
    items = []
    for label, value in dimensions:
        try:
            percentage = max(0, min(100, float(value)))
            shown = f"{percentage:.1f}%".replace(".", ",")
        except (TypeError, ValueError):
            percentage, shown = 0, "Não avaliada"
        items.append(f'<div class="dimension"><div><span>{label}</span><strong>{shown}</strong></div>'
                     f'<progress max="100" value="{percentage:.1f}" aria-label="{label}"></progress></div>')
    return "".join(items)


def _column_rows(table: dict[str, Any]) -> str:
    assessments = {
        "strong_candidate": "Candidato forte", "possible_identifier": "Possível identificador",
        "high_uniqueness_measure": "Medida altamente única; não é chave", 
        "high_uniqueness_unconfirmed": "Alta unicidade sem evidência semântica", "not_candidate": "Não candidato",
    }
    return "".join(
        "<tr>" + "".join(f"<td>{_text(value)}</td>" for value in (
            column.get("name"), column.get("physical_type") or column.get("original_type"),
            column.get("inferred_type"), column.get("semantic_role"), _number(column.get("null_count")),
            f"{column.get('null_pct', 0)}%", column.get("cardinality"),
            assessments.get(column.get("key_assessment", "not_candidate")))) + "</tr>"
        for column in table.get("column_analyses", []))


def _key_html(table: dict[str, Any]) -> str:
    assessments = {
        "strong_candidate": "Candidato forte a identificador", "possible_identifier": "Possível identificador",
        "high_uniqueness_measure": "Medida altamente única, sem evidência de chave",
        "high_uniqueness_unconfirmed": "Alta unicidade, sem evidência semântica de chave",
    }
    columns = table.get("column_analyses", [])
    findings = [column for column in columns if column.get("key_assessment") in assessments]
    composite_findings = [candidate for candidate in table.get("key_candidates", [])
                          if len(candidate.get("columns", [])) > 1]
    if not findings and not composite_findings:
        return '<p class="muted">Nenhuma coluna atendeu aos critérios de unicidade avaliados.</p>'
    result = []
    for column in findings:
        result.append(f'<article class="alert information"><div><h4>{_text(column.get("name"))} · '
                      f'{assessments[column["key_assessment"]]}</h4><strong>{_text(column.get("distinct_pct", 0))}% única'
                      f' · {_text(column.get("completeness_pct", 0))}% preenchida</strong>'
                      f'<p>{_text("; ".join(column.get("key_reasons", [])), "Avaliação heurística.")}</p></div></article>')
    for candidate in composite_findings:
        columns_text = " + ".join(str(name) for name in candidate.get("columns", []))
        reasons = "; ".join(candidate.get("reasons", []))
        result.append(f'<article class="alert information"><div><h4>{_text(columns_text)} · possível chave composta</h4>'
                      f'<strong>{_text(candidate.get("uniqueness_pct", 0))}% de combinações únicas · '
                      f'confiança {_text(candidate.get("confidence", "low"))}</strong>'
                      f'<p>{_text(reasons)} Confirme a semântica e a regra de negócio.</p></div></article>')
    return "".join(result)


def _table_html(table: dict[str, Any], index: int) -> str:
    quality = table.get("quality", {})
    alerts = _alerts(quality)
    header = table.get("header_detection", {})
    header_info = (f"Detectado na linha {_number(table.get('header_row_used'))}" if table.get("header_row_used")
                   else _text(header.get("status", "Não informado")))
    anomaly_rows = [anomaly for column in table.get("column_analyses", []) for anomaly in column.get("anomalies", [])]
    anomaly_html = "".join(f'<article class="alert attention"><div><h4>{_text(item.get("column"))}: '
                           f'{_number(item.get("count"))} possíveis outliers</h4><p>{_text(item.get("description"))}</p></div></article>'
                           for item in anomaly_rows[:20]) or '<p class="muted">Nenhuma anomalia estatística reportada.</p>'
    columns_html = _column_rows(table) or '<tr><td colspan="8">Sem colunas analisadas.</td></tr>'
    return f'''<details class="sheet" id="sheet-{index}" open>
      <summary><span>{_text(table.get("name"))}</span><span class="badge">{_text(_status(table.get("status")))}</span>
        <span>{_number(table.get("rows_available", table.get("rows")))} linhas</span>
        <span>{_number(table.get("columns"))} colunas</span><strong>{_text(quality.get("score", 0))}/100</strong></summary>
      <div class="sheet-body"><div class="stats"><div><small>Linhas disponíveis / avaliadas</small><b>{_number(table.get("rows_available", table.get("rows")))} / {_number(table.get("rows_analyzed"))}</b></div>
        <div><small>Cabeçalho</small><b>{header_info}</b></div><div><small>Tipo provável</small><b>{_text(table.get("table_type"))} ({_text(table.get("table_type_confidence"))})</b></div>
        <div><small>Amostragem</small><b>{_text(table.get("sampling_method", "none")) if table.get("sampled") else "Não aplicada"}</b></div>
        <div><small>Qualidade</small><b>{_text(quality.get("classification"))} · {_text(quality.get("score"))}/100</b></div></div>
        <div class="dimensions">{_quality_bars(quality)}</div>
        <h4>Alertas e observações</h4>{''.join(_alert_html(alert, str(table.get('name', ''))) for alert in alerts) or '<p class="muted">Nenhum alerta de qualidade.</p>'}
        <h4>Identificadores avaliados</h4>{_key_html(table)}
        <h4>Anomalias estatísticas</h4><p class="muted">Valores fora da faixa de 1,5 × IQR podem ser legítimos e não representam necessariamente erros.</p>{anomaly_html}
        <h4>Colunas</h4><div class="table-scroll"><table><thead><tr><th>Coluna</th><th>Tipo físico</th><th>Tipo inferido</th><th>Papel</th><th>Nulos</th><th>% nulos</th><th>Cardinalidade</th><th>Identificador</th></tr></thead><tbody>{columns_html}</tbody></table></div>
      </div></details>'''


def _human_summary_html(report: dict[str, Any], index: int) -> str:
    human = report.get("human_summary") or {}
    if not human:
        return ""
    components = "".join(
        f'<div class="stats"><div><small>{_text(item.get("name"))}</small>'
        f'<b>{_text(item.get("value"))}%</b><span class="muted">{_text(item.get("description"))}</span></div></div>'
        for item in human.get("quality_components", [])
    )
    found = "".join(f"<li>{_text(item)}</li>" for item in human.get("what_was_found", []))
    findings = "".join(
        f'<article class="insight-card"><span class="badge">{_text(item.get("importance"))} · {_text(item.get("type"))}</span>'
        f'<h4>{_text(item.get("title"))}</h4><p>{_text(item.get("description"))}</p>'
        f'<details><summary>Por que sugerimos isso?</summary><p>{_text(item.get("why"))}</p></details></article>'
        for item in human.get("key_findings", [])
    ) or '<p class="muted">Não há descobertas prioritárias com evidência suficiente.</p>'
    severity = {"critical": "critical", "attention": "attention", "information": "information"}
    attention = "".join(
        f'<article class="alert {severity.get(item.get("severity"), "information")}"><div>'
        f'<strong>{_text(item.get("message"))}</strong></div></article>'
        for item in human.get("attention_points", [])
    ) or '<p class="muted">Nenhum ponto de atenção foi registrado.</p>'
    opportunities = "".join(
        f'<section><h4>{_text(group.get("category"))}</h4><ul>'
        + "".join(f"<li>{_text(question)}</li>" for question in group.get("questions", [])) + "</ul></section>"
        for group in human.get("analysis_opportunities", [])
    ) or '<p class="muted">Não há oportunidades com evidência suficiente.</p>'
    blueprint = report.get("dashboard_blueprint") or {}
    pages = "".join(f'<li><b>{_text(page.get("name"))}</b> — {_text(page.get("purpose"))}</li>'
                     for page in blueprint.get("recommended_pages", []))
    return (f'<section id="human-summary-{index}"><h3>{_text(human.get("title", "Resumo executivo"))}</h3>'
            f'<p>{_text(human.get("executive_summary"))}</p><h4>Como estão os dados?</h4>'
            f'<p>{_text(human.get("data_quality_summary"))}</p>{components}'
            f'<h4>O que encontramos</h4><ul>{found}</ul><h4 id="discoveries-{index}">Principais descobertas</h4>'
            f'<div class="insight-grid">{findings}</div><h4>Pontos de atenção</h4>{attention}'
            f'<h4 id="opportunities-{index}">O que posso analisar?</h4>{opportunities}'
            f'<h4 id="dashboard-{index}">Dashboard recomendado</h4><p>{_text(human.get("dashboard_summary"))}</p>'
            f'<ul>{pages}</ul></section>')


def render_html_report(batch: dict[str, Any]) -> str:
    """Render a self-contained, offline report without re-reading source files."""
    reports = _reports(batch)
    total_sheets = sum(len(report.get("tables", [])) for _, report in reports)
    total_rows = sum(sum(int(table.get("rows_analyzed", 0) or 0) for table in report.get("tables", [])) for _, report in reports)
    total_columns = sum(sum(int(table.get("columns", 0) or 0) for table in report.get("tables", [])) for _, report in reports)
    all_alerts = [(table, alert) for _, report in reports for table in report.get("tables", [])
                  for alert in _alerts(table.get("quality", {}))]
    overview_rows = "".join(f'<tr><td>{_text(filename)}</td><td>{_text(_status(report.get("status")))}</td>'
                            f'<td>{_number(len(report.get("tables", [])))}</td><td>{_text(report.get("quality", {}).get("classification"))} · '
                            f'{_text(report.get("quality", {}).get("score"))}/100</td></tr>' for filename, report in reports)
    report_sections = "".join(f'<section class="report-file"><h2>{_text(filename)}</h2><p class="muted">'
                               f'{_text(report.get("file_type", "arquivo")).upper()} · {_text(_status(report.get("status")))} · '
                               f'{_text(_duration(report.get("processing_time_ms", 0)))} · analisado em {_text(report.get("analyzed_at"))}</p>'
                               f'{_human_summary_html(report, report_index)}'
                               f'<h3 id="quality">Detalhes da qualidade</h3><div class="score"><strong>{_text(report.get("quality", {}).get("score"))}/100</strong>'
                               f'<span>{_text(report.get("quality", {}).get("classification"))}</span></div>'
                               f'<div class="dimensions">{_quality_bars(report.get("quality", {}))}</div>'
                               f'<h3>Pontos de atenção</h3>{"".join(_alert_html(alert) for table in report.get("tables", []) for alert in _alerts(table.get("quality", {}))) or "<p class=\"muted\">Nenhum alerta.</p>"}'
                               f'<h3 id="sheets">Abas analisadas</h3>{"".join(_table_html(table, i) for i, table in enumerate(report.get("tables", [])))}'
                               f'<h3 id="relationships">Relações potenciais</h3>{_relationships_html(report)}'
                               f'{_discovery_html(report)}'
                               f'<h3 id="security">Segurança da análise</h3>{_security_html(report.get("security"))}'
                               f'<h3>Observações</h3>{_warnings_html(report)}'
                               f'<h3>Detalhes técnicos</h3><p class="muted">ID {_text(report.get("analysis_id"))} · '
                               f'{_number(report.get("file_size_bytes"))} bytes · {_text(_duration(report.get("processing_time_ms", 0)))} · '
                               f'SHA-256 {_text(report.get("file_sha256"))}</p>'
                               f'<p class="muted">Limites/configuração: amostragem {_text("ativa" if report.get("settings", {}).get("sampling_enabled") else "desativada")}; '
                               f'{_number(report.get("settings", {}).get("max_rows_to_analyze"))} linhas, '
                               f'{_number(report.get("settings", {}).get("max_columns_to_analyze"))} colunas e '
                               f'{_number(report.get("settings", {}).get("max_cells_to_analyze"))} células por tabela.</p></section>'
                               for report_index, (filename, report) in enumerate(reports))
    failed_rows = "".join(f'<tr><td>{_text(item.get("filename"))}</td><td>{_text(item.get("error"))}</td></tr>'
                          for item in batch.get("results", []) if not item.get("analysis"))
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <meta name="referrer" content="no-referrer"><title>Diagnóstico de Dados · BI Swiss Knife</title><style>
      :root{{--ink:#17231d;--muted:#617168;--line:#dbe4dd;--green:#176b3d;--pale:#eef6f0;--critical:#9f2e29;--attention:#8a5b00;--info:#315983}}
      *{{box-sizing:border-box}}body{{margin:0;background:#f5f8f6;color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
      header{{padding:38px max(24px,calc((100vw - 1120px)/2));background:#14251b;color:white}}header strong{{letter-spacing:.13em;color:#9ee0b5;font-size:12px}}
      header h1{{font-size:32px;margin:10px 0 4px}}header p{{color:#c3d3c8;margin:0}}main{{max-width:1120px;margin:24px auto;padding:0 20px 50px}}
      nav{{position:sticky;top:0;background:#f5f8f6ee;padding:10px 0;display:flex;gap:8px;overflow:auto;z-index:2}}nav a{{white-space:nowrap;padding:8px 12px;border:1px solid var(--line);border-radius:99px;color:var(--green);text-decoration:none;background:white}}
      .insight-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}}.insight-card{{border:1px solid var(--line);border-radius:10px;padding:14px;background:#fbfdfb}}.insight-card p{{margin:7px 0;font-size:13px}}
      section,.panel,.sheet{{background:white;border:1px solid var(--line);border-radius:14px;padding:22px;margin:14px 0;scroll-margin-top:68px}}h2,h3{{line-height:1.2}}h2{{font-size:24px}}h3{{font-size:18px;margin:24px 0 12px}}h4{{font-size:14px;margin:3px 0 6px}}
      .muted,small{{color:var(--muted)}}.cards,.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}.cards>div,.stats>div,.metric{{padding:15px;background:var(--pale);border-radius:10px}}
      .cards small,.stats small{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}}.cards strong,.stats b{{display:block;font-size:20px;margin-top:4px}}
      .score{{display:flex;align-items:baseline;gap:14px}}.score strong{{font-size:34px;color:var(--green)}}.score span{{font-size:18px}}
      .dimensions{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:14px 0}}.dimension{{padding:12px;background:#f7faf8;border-radius:8px}}.dimension>div{{display:flex;justify-content:space-between;gap:12px}}
      progress{{width:100%;height:10px;accent-color:var(--green);margin-top:8px}}.alert{{display:flex;gap:12px;margin:8px 0;padding:12px;border-left:4px solid var(--info);background:#f4f8fc;border-radius:5px}}
      .alert.critical{{border-color:var(--critical);background:#fff4f2}}.alert.attention{{border-color:var(--attention);background:#fff9eb}}.alert.information{{border-color:var(--info)}}.alert p{{margin:5px 0 0;color:var(--muted);font-size:13px}}
      .badge{{display:inline-block;border-radius:99px;background:#e9f3ec;padding:3px 9px;font-size:11px;color:var(--green);white-space:nowrap}}
      table{{width:100%;border-collapse:collapse;min-width:720px}}th,td{{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}}th{{background:#eef4ef;font-size:11px;text-transform:uppercase}}
      .table-scroll{{overflow:auto}}.sheet{{padding:0;overflow:hidden}}.sheet summary{{cursor:pointer;padding:15px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;list-style:none}}.sheet summary::-webkit-details-marker{{display:none}}.sheet summary span:first-child{{font-weight:700;flex:1;min-width:170px}}.sheet-body{{padding:0 18px 20px}}
      @media(max-width:650px){{header{{padding:26px 18px}}header h1{{font-size:25px}}main{{padding:0 12px 30px}}section{{padding:16px}}}}
      @media print{{body{{background:white;font-size:10pt}}header{{padding:18px 0;background:white;color:var(--ink);border-bottom:2px solid var(--green)}}nav{{display:none}}main{{max-width:none;margin:0;padding:0}}section,.panel,.sheet{{break-inside:avoid;box-shadow:none;margin:8px 0;padding:12px}}.sheet{{break-inside:auto}}.sheet:not([open])>.sheet-body{{display:block}}a{{color:inherit}}}}
      </style></head><body><header><strong>BI SWISS KNIFE</strong><h1>Diagnóstico de Dados</h1><p>Relatório local · sem prévia de linhas ou rótulos de categorias</p></header><main>
      <nav aria-label="Navegação do relatório"><a href="#summary">Resumo</a><a href="#human-summary-0">Entendimento</a><a href="#discoveries-0">Descobertas</a><a href="#opportunities-0">Análises possíveis</a><a href="#dashboard-0">Dashboard</a><a href="#quality">Qualidade técnica</a><a href="#sheets">Abas e estrutura</a><a href="#relationships">Relações</a><a href="#insights">Técnico</a><a href="#security">Segurança</a></nav>
      <section id="summary"><h2>Resumo da seleção</h2><div class="cards"><div><small>Arquivos</small><strong>{_number(batch.get("file_count", len(batch.get("results", []))))}</strong></div>
        <div><small>Abas</small><strong>{_number(total_sheets)}</strong></div><div><small>Registros avaliados</small><strong>{_number(total_rows)}</strong></div>
        <div><small>Colunas</small><strong>{_number(total_columns)}</strong></div><div><small>Tipos de alertas</small><strong>{_number(len(all_alerts))}</strong></div></div>
        <div class="table-scroll"><table><thead><tr><th>Arquivo</th><th>Status</th><th>Abas</th><th>Qualidade geral</th></tr></thead><tbody>{overview_rows or '<tr><td colspan="4">Nenhuma análise concluída.</td></tr>'}</tbody></table></div>
        {f'<h3>Arquivos com falha</h3><div class="table-scroll"><table><thead><tr><th>Arquivo</th><th>Motivo informado</th></tr></thead><tbody>{failed_rows}</tbody></table></div>' if failed_rows else ''}</section>
      <section id="quality"><h2>Qualidade geral</h2><p class="muted">O score resume regras heurísticas; uma aba auxiliar, template ou destinada a preenchimento pode ter score baixo sem representar erro. Interprete junto às dimensões, aos alertas e ao contexto.</p>{''.join(f'<article class="panel"><h3>{_text(name)}</h3><div class="score"><strong>{_text(report.get("quality", {}).get("score"))}/100</strong><span>{_text(report.get("quality", {}).get("classification"))}</span></div><div class="dimensions">{_quality_bars(report.get("quality", {}))}</div></article>' for name, report in reports)}</section>
      {report_sections or '<section><p>Nenhum relatório disponível.</p></section>'}<section id="technical"><h2>Notas de interpretação</h2><p>Indicadores podem refletir amostragem quando ela foi aplicada. Confira os avisos de cada aba e valide regras de negócio antes de tomar decisões.</p><p>Valores fora da faixa de 1,5 × IQR são anomalias estatísticas e podem ser legítimos.</p></section>
      <footer class="muted">Gerado localmente pelo BI Swiss Knife. Nenhum serviço externo é necessário.</footer></main></body></html>'''


def _security_html(security: dict[str, Any] | None) -> str:
    security = security or {}
    checks = [
        ("Arquivo original alterado", False),
        ("Arquivo processado localmente", True),
        ("Arquivo aberto em modo somente leitura", True),
        ("Macros executadas", security.get("macros_executed")),
        ("Objetos incorporados executados", security.get("embedded_objects_executed")),
        ("Conexões externas acessadas", security.get("external_connections_accessed")),
        ("Relações externas seguidas", security.get("external_relationships_followed")),
        ("Conexões externas atualizadas", security.get("external_connections_updated")),
        ("Fórmulas recalculadas", security.get("formulas_recalculated")),
    ]
    summary = "".join(f'<li>{"Não" if value is False else "Sim" if value is True else "Não informado"} · {_text(label)}</li>'
                     for label, value in checks)
    active = (f'<article class="alert attention"><div><h4>Conteúdo potencialmente ativo detectado</h4><p>Foi identificado, mas não executado. Tipos: '
              f'{_text(", ".join(security.get("active_content_types", [])), "não informados")}</p></div></article>'
              if security.get("active_content_detected") else '<p>Não foi detectado conteúdo potencialmente ativo.</p>')
    formula_action = {"cached_values_only": "valores armazenados em cache; sem recálculo",
                      "not_applicable": "não aplicável"}.get(str(security.get("formulas_action")),
                                                                  str(security.get("formulas_action") or "não informado"))
    return (f'<ul>{summary}<li>Fórmulas: {_text(formula_action)}</li>'
            f'<li>Relações externas detectadas: {_number(security.get("external_relationship_count", 0))}</li></ul>{active}')


def _warnings_html(report: dict[str, Any]) -> str:
    messages = [*report.get("security_warnings", []), *report.get("warnings", [])]
    if not messages:
        return '<p class="muted">Nenhuma observação adicional.</p>'
    return "<ul>" + "".join(f"<li>{_text(message)}</li>" for message in messages) + "</ul>"


def _relationships_html(report: dict[str, Any]) -> str:
    relationships = report.get("relationships", [])
    if not relationships:
        return '<p class="muted">Nenhuma relação com evidência suficiente foi sugerida.</p>'
    return "".join(
        f'<article class="alert information"><div><h4>{_text(item.get("source_table"))}.{_text(item.get("source_column"))} '
        f'→ {_text(item.get("target_table"))}.{_text(item.get("target_column"))}</h4>'
        f'<strong>{_text(item.get("coverage_pct"))}% de correspondência · '
        f'{_text(item.get("cardinality"))} · confiança {_text(item.get("confidence"))}</strong>'
        f'<p>{_text(item.get("reason"))}</p></div></article>'
        for item in relationships
    )


def _discovery_html(report: dict[str, Any]) -> str:
    semantic = report.get("semantic_model") or {}
    insight_block = report.get("insights") or {}
    items = insight_block.get("items", [])
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items = sorted(items, key=lambda item: priority_order.get(item.get("priority"), 3))[:12]
    dimensions, measures, dates = (semantic.get(key, []) for key in ("dimensions", "measures", "dates"))
    overview = (f'<p><b>Dimensões:</b> {_text(", ".join(item.get("name", "") for item in dimensions) or "Nenhuma identificada")}</p>'
                f'<p><b>Medidas:</b> {_text(", ".join(item.get("name", "") for item in measures) or "Nenhuma identificada")}</p>'
                f'<p><b>Datas:</b> {_text(", ".join(item.get("name", "") for item in dates) or "Nenhuma identificada")}</p>')
    cards = []
    for item in items:
        fields = [*item.get("dimensions", []), *item.get("measures", []), *item.get("dates", [])]
        field_names = ", ".join(f"{field.get('table')}.{field.get('column')}" for field in fields)
        cards.append(
            f'<article class="insight-card"><div><span class="badge">{_text(item.get("priority", "low"))} · {_text(item.get("type"))}</span> '
            f'<span class="badge">Confiança: {_text(item.get("confidence"))}</span></div>'
            f'<h4>{_text(item.get("title"))}</h4><p><b>Pergunta:</b> {_text(item.get("business_question"))}</p>'
            f'<p><b>Campos:</b> {_text(field_names or "—")}</p><p><b>Visual:</b> {_text(item.get("visual"))}</p>'
            f'<p><b>Por que foi sugerido:</b> {_text(item.get("reason"))}</p>'
            f'<p><b>Evidências:</b> {_text(" ".join(item.get("evidence", [])))}</p></article>')
    blueprint = report.get("dashboard_blueprint") or {}
    pages = "".join(f'<li><b>{_text(page.get("name"))}</b>: {_text(page.get("purpose"))}</li>'
                    for page in blueprint.get("recommended_pages", []))
    if not semantic:
        cards.append('<p class="muted">Este relatório foi criado sem a camada de descoberta semântica.</p>')
    elif not items:
        cards.append('<p class="muted">Não há combinações com evidência suficiente para sugerir análises.</p>')
    return (f'<section id="insights"><h3>O que posso analisar?</h3>{overview}'
            f'<h4>Principais oportunidades de análise</h4><div class="insight-grid">{"".join(cards)}</div>'
            f'<h4>Blueprint sugerido de dashboard</h4><p>{_text(blueprint.get("objective", "Sem blueprint disponível."))}</p>'
            f'<ul>{pages or "<li>Nenhuma página sugerida.</li>"}</ul>'
            f'<p><b>Filtros candidatos:</b> {_text(", ".join(item.get("column", "") for item in blueprint.get("filters", [])) or "Nenhum")}</p>'
            f'<p class="muted">Sugestões heurísticas derivadas dos metadados; valide confiança e regra de negócio antes de usar.</p></section>')
