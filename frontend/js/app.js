const input = document.querySelector('#file-input');
const folderInput = document.querySelector('#folder-input');
const drop = document.querySelector('#drop-zone');
const button = document.querySelector('#analyze-button');
const statusEl = document.querySelector('#status');
const resultEl = document.querySelector('#results');
const progressCard = document.querySelector('#analysis-progress');
const maxFiles = 50;
let selectedFiles = [];
const relativePaths = new WeakMap();
const headerChoiceDialog = document.querySelector('#header-choice');

document.querySelector('#browse').addEventListener('click', () => input.click());
document.querySelector('#browse-folder').addEventListener('click', () => folderInput.click());
input.addEventListener('change', () => {
  setFiles([...input.files]);
  input.value = '';
});
folderInput.addEventListener('change', () => {
  setFiles([...folderInput.files]);
  folderInput.value = '';
});

['dragenter', 'dragover'].forEach(event => drop.addEventListener(event, e => {
  e.preventDefault();
  drop.classList.add('dragover');
}));
['dragleave', 'drop'].forEach(event => drop.addEventListener(event, e => {
  e.preventDefault();
  drop.classList.remove('dragover');
}));
drop.addEventListener('drop', async event => {
  try {
    const items = [...(event.dataTransfer?.items || [])].filter(item => item.kind === 'file');
    const handles = await readDroppedHandles(items);
    if (handles) {
      setFiles(handles.flat());
      return;
    }
    const entries = items.map(item => item.webkitGetAsEntry?.()).filter(Boolean);
    if (entries.length) {
      const groups = await Promise.all(entries.map(readEntry));
      setFiles(groups.flat());
      return;
    }
    setFiles([...(event.dataTransfer?.files || [])]);
  } catch {
    showStatus('Não foi possível ler a pasta solta. Tente escolhê-la pelo botão “Escolher pasta”.', 'error');
  }
});

async function readDroppedHandles(items) {
  if (!items.length || !items.every(item => typeof item.getAsFileSystemHandle === 'function')) return null;
  const handles = await Promise.all(items.map(item => item.getAsFileSystemHandle()));
  if (handles.some(handle => !handle)) return null;
  return Promise.all(handles.map(handle => readHandle(handle)));
}

async function readHandle(handle, parentPath = '') {
  const path = parentPath ? `${parentPath}/${handle.name}` : handle.name;
  if (handle.kind === 'file') {
    const file = await handle.getFile();
    relativePaths.set(file, path);
    return [file];
  }
  if (handle.kind !== 'directory') return [];
  const files = [];
  for await (const [, child] of handle.entries()) files.push(...await readHandle(child, path));
  return files;
}

function readEntry(entry) {
  if (entry.isFile) {
    return new Promise((resolve, reject) => entry.file(file => {
      relativePaths.set(file, entry.fullPath.replace(/^\/+/, ''));
      resolve(file);
    }, reject));
  }
  if (!entry.isDirectory) return Promise.resolve([]);
  const reader = entry.createReader();
  return new Promise((resolve, reject) => {
    const children = [];
    const readNext = () => reader.readEntries(async entries => {
      if (!entries.length) {
        try {
          const nested = await Promise.all(children.map(readEntry));
          resolve(nested.flat());
        } catch (error) {
          reject(error);
        }
        return;
      }
      children.push(...entries);
      readNext();
    }, reject);
    readNext();
  });
}

function fileLabel(file) {
  return relativePaths.get(file) || file.webkitRelativePath || file.name;
}

function setFiles(files) {
  statusEl.className = 'status';
  statusEl.textContent = '';
  resultEl.hidden = true;
  const valid = files.filter(file => /\.(xlsx|xlsm|csv)$/i.test(file.name));
  const unique = new Map();
  valid.forEach(file => unique.set(`${fileLabel(file)}:${file.size}:${file.lastModified}`, file));
  selectedFiles = [...unique.values()];
  const rejected = files.length - selectedFiles.length;
  if (selectedFiles.length > maxFiles) {
    selectedFiles = [];
    showStatus(`Selecione no máximo ${maxFiles} arquivos por vez.`, 'error');
  } else if (!selectedFiles.length) {
    showStatus('Não encontrei arquivos .xlsx, .xlsm ou .csv na seleção.', 'error');
  } else if (rejected) {
    showStatus(`${rejected} item(ns) foram ignorados; somente CSV e XLSX são aceitos.`);
  }
  const nameEl = document.querySelector('#file-name');
  if (selectedFiles.length) {
    const labels = selectedFiles.slice(0, 3).map(fileLabel);
    const remaining = selectedFiles.length - labels.length;
    nameEl.textContent = `${selectedFiles.length} arquivo(s): ${labels.join(', ')}${remaining ? ` e mais ${remaining}` : ''}`;
    nameEl.hidden = false;
  } else {
    nameEl.hidden = true;
  }
  button.disabled = selectedFiles.length === 0;
}

button.addEventListener('click', async () => {
  if (!selectedFiles.length) return;
  const filesToAnalyze = [...selectedFiles];
  const selectedDelimiter = document.querySelector('#csv-delimiter').value;
  const common = {
    csv_delimiter: selectedDelimiter === 'tab' ? '\t' : selectedDelimiter,
    decimal_separator: document.querySelector('#decimal-separator').value,
    header_mode: document.querySelector('#header-mode').value,
  };
  button.disabled = true;
  button.textContent = 'Analisando…';
  showStatus(`Analisando ${filesToAnalyze.length} arquivo(s) localmente. A duração depende do tamanho dos dados.`);
  try {
    const payload = await submitBatchWithProgress(filesToAnalyze, common);
    if (common.header_mode === 'auto') await resolveAmbiguousHeaders(payload, common, filesToAnalyze);
    renderBatch(payload);
    const succeeded = payload.results.filter(item => item.analysis && item.analysis.status !== 'failed').length;
    const failed = payload.results.length - succeeded;
    downloadReport(JSON.stringify(payload, null, 2), 'application/json', 'bi-swiss-knife-relatorio.json');
    showStatus(failed
      ? `${succeeded} arquivo(s) analisado(s); ${failed} com erro. O relatório JSON foi baixado para o computador.`
      : `${succeeded} arquivo(s) analisado(s). O relatório JSON foi baixado para o computador.`, failed ? '' : 'success');
  } catch (error) {
    showStatus(error.message || 'Não foi possível analisar os arquivos.', 'error');
  } finally {
    button.disabled = selectedFiles.length === 0;
    button.innerHTML = 'Analisar arquivos <span>→</span>';
  }
});

async function submitBatchWithProgress(files, options) {
  progressCard.hidden = false;
  updateProgress({ progress: 0, stage: 'initializing', message: 'Preparando envio local', status: 'running',
    filename: files.length === 1 ? fileLabel(files[0]) : files.length + ' arquivos',
    elapsed_seconds: 0, estimated_remaining_seconds: null });
  // The upload panel is taller than a typical viewport. Bring progress into view
  // before waiting for the upload/job response so the user sees feedback at once.
  progressCard.scrollIntoView({ block: 'center' });
  const data = new FormData();
  files.forEach(file => data.append('uploads', file, fileLabel(file)));
  Object.entries(options).forEach(([key, value]) => data.append(key, value));
  const response = await fetch('/api/analyze-progress', { method: 'POST', body: data });
  const job = await response.json();
  if (!response.ok) throw new Error(job.detail || 'Falha ao iniciar a análise.');
  while (true) {
    const progressResponse = await fetch('/api/analyze-jobs/' + encodeURIComponent(job.job_id) + '/progress');
    const state = await progressResponse.json();
    if (!progressResponse.ok) throw new Error(state.detail || 'Não foi possível consultar o progresso.');
    updateProgress(state);
    if (state.status === 'completed') {
      if (!state.result) throw new Error('A análise terminou sem um relatório.');
      return state.result;
    }
    if (state.status === 'error') throw new Error(state.message || 'Não foi possível concluir a análise.');
    await new Promise(resolve => setTimeout(resolve, 400));
  }
}

function formatDuration(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  return String(Math.floor(value / 60)).padStart(2, '0') + ':' + String(value % 60).padStart(2, '0');
}

function updateProgress(state) {
  const progress = Math.max(0, Math.min(100, Number(state.progress) || 0));
  document.querySelector('#progress-bar').value = progress;
  document.querySelector('#progress-percent').textContent = progress + '%';
  document.querySelector('#progress-title').textContent =
    state.status === 'completed' ? 'Análise concluída' : state.status === 'error' ? 'Falha na análise' : 'Analisando arquivo';
  document.querySelector('#progress-filename').textContent = state.filename || '';
  document.querySelector('#progress-stage').textContent = state.message || state.stage || 'Processando';
  const sheetText = state.file_type === 'csv'
    ? (state.records_scanned != null ? Number(state.records_scanned).toLocaleString('pt-BR') + ' registros contados' : '')
    : state.total_sheets
    ? 'Aba ' + Math.min(state.current_sheet || 1, state.total_sheets) + ' de ' + state.total_sheets
      + (state.current_sheet_name ? ' — ' + state.current_sheet_name : '')
      + (state.rows_available != null ? ' · ' + Number(state.rows_available).toLocaleString('pt-BR') + ' linhas disponíveis' : '')
    : (state.total_files > 1 ? 'Arquivo ' + (state.current_file || 1) + ' de ' + state.total_files : '');
  document.querySelector('#progress-sheets').textContent = sheetText;
  document.querySelector('#progress-elapsed').textContent = formatDuration(state.elapsed_seconds);
  const remaining = state.estimated_remaining_seconds;
  document.querySelector('#progress-remaining').textContent = state.status === 'completed'
    ? '00:00' : remaining == null ? 'Calculando...' : '~' + formatDuration(remaining);
  progressCard.dataset.status = state.status || 'running';
}

function chooseHeader(filename) {
  document.querySelector('#header-choice-file').textContent = filename;
  headerChoiceDialog.showModal();
  return new Promise(resolve => headerChoiceDialog.addEventListener('close', () => {
    resolve(headerChoiceDialog.returnValue === 'header' ? 'true'
      : headerChoiceDialog.returnValue === 'data' ? 'false' : null);
  }, { once: true }));
}

async function resolveAmbiguousHeaders(batch, options, files) {
  for (let index = 0; index < batch.results.length; index += 1) {
    const item = batch.results[index];
    if (!item.analysis || !item.analysis.warnings.some(warning => warning.includes('é ambígua'))) continue;
    const choice = await chooseHeader(item.filename);
    if (choice === null) continue;
    const file = files[index];
    const corrected = await submitBatchWithProgress([file], { ...options, header_mode: choice });
    if (corrected.results[0]?.analysis) item.analysis = corrected.results[0].analysis;
    else item.error = corrected.results[0]?.error || 'Não foi possível reanalisar com a escolha informada.';
  }
}

function showStatus(message, type = '') {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);
}

function renderBatch(batch) {
  const successes = batch.results.filter(item => item.analysis);
  const analyzedCount = successes.filter(item => item.analysis.status !== 'failed').length;
  const totalRows = successes.reduce((sum, item) => sum + item.analysis.tables.reduce((n, table) => n + table.rows, 0), 0);
  const totalColumns = successes.reduce((sum, item) => sum + item.analysis.tables.reduce((n, table) => n + table.columns, 0), 0);
  const issueCount = successes.reduce((sum, item) => sum + item.analysis.tables.reduce((tableSum, table) =>
    tableSum + table.duplicate_rows + table.column_analyses.reduce((columnSum, column) =>
      columnSum + column.inconsistent_values, 0), 0), 0);
  const fileRows = batch.results.map(item => {
    const status = item.analysis?.status === 'partial' ? 'Análise parcial'
      : item.analysis?.status === 'failed' ? 'Falha na análise'
        : item.analysis ? 'Analisado' : `Erro: ${escapeHtml(item.error)}`;
    return `<div class="relationship"><b>${escapeHtml(item.filename)}</b> <span class="subtle">${status}</span></div>`;
  }).join('');
  const details = successes.length ? `<div class="panel"><div class="table-head"><h3>Detalhes do arquivo</h3><select class="table-select" id="file-select">${successes.map((item, i) => `<option value="${i}">${escapeHtml(item.filename)}</option>`).join('')}</select></div><div id="file-details"></div></div>` : '<div class="panel subtle">Nenhum arquivo pôde ser analisado.</div>';
  resultEl.hidden = false;
  resultEl.innerHTML = `<div class="results-head"><div><h2>Visão geral da seleção</h2><div class="subtle">${analyzedCount} de ${batch.file_count} arquivo(s) analisado(s) · ${successes.length} relatório(s) disponível(is)</div></div><div class="export-actions"><button id="export-json" class="secondary-button">Baixar JSON</button><button id="export-csv" class="secondary-button">CSV resumo</button><button id="export-html" class="secondary-button">Abrir HTML offline</button><button id="export-pdf" class="secondary-button">Exportar PDF</button></div></div>
    <div class="metric-grid"><div class="metric"><label>LINHAS</label><strong>${totalRows.toLocaleString('pt-BR')}</strong></div><div class="metric"><label>COLUNAS</label><strong>${totalColumns.toLocaleString('pt-BR')}</strong></div><div class="metric"><label>ITENS PARA REVISAR</label><strong class="${issueCount ? 'quality-bad' : ''}">${issueCount.toLocaleString('pt-BR')}</strong><span class="subtle">sem contar ausências</span></div></div>
    <div class="panel"><h3>Arquivos selecionados</h3>${fileRows}</div>${details}`;
  resultEl.querySelector('#export-json').addEventListener('click', () => downloadReport(JSON.stringify(batch, null, 2), 'application/json', 'bi-swiss-knife-relatorio.json'));
  resultEl.querySelector('#export-csv').addEventListener('click', () => downloadReport(batchCsv(batch), 'text/csv;charset=utf-8', 'bi-swiss-knife-resumo.csv'));
  resultEl.querySelector('#export-html').addEventListener('click', () => exportDerivedReport(batch, '/api/report-html', 'text/html;charset=utf-8', 'bi-swiss-knife-relatorio.html', true));
  resultEl.querySelector('#export-pdf').addEventListener('click', () => exportDerivedReport(batch, '/api/report-pdf', 'application/pdf', 'bi-swiss-knife-relatorio-executivo.pdf'));
  if (successes.length) {
    const selector = resultEl.querySelector('#file-select');
    const update = () => renderFileDetails(successes[Number(selector.value)].analysis);
    selector.addEventListener('change', update);
    update();
  }
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function downloadReport(content, type, filename) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportDerivedReport(batch, endpoint, mediaType, filename, openInTab = false) {
  const preview = openInTab ? window.open('about:blank', '_blank') : null;
  if (preview) preview.opener = null;
  try {
    const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(batch) });
    if (!response.ok) {
      let detail = 'Não foi possível gerar o relatório.';
      try { detail = (await response.json()).detail || detail; } catch { /* keep the safe generic message */ }
      throw new Error(detail);
    }
    const blob = await response.blob();
    if (preview) {
      const url = URL.createObjectURL(new Blob([blob], { type: mediaType }));
      preview.location.replace(url);
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } else {
      downloadReport(blob, mediaType, filename);
    }
    showStatus(filename.endsWith('.pdf') ? 'PDF executivo gerado localmente.' : 'HTML offline aberto em outra guia.', 'success');
  } catch (error) {
    if (preview) preview.close();
    showStatus(error.message || 'Não foi possível gerar o relatório.', 'error');
  }
}

function csvCell(value) {
  let text = String(value ?? '');
  if (/^[\s]*[=+@\-]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function batchCsv(batch) {
  const rows = [['arquivo','aba','linhas','perfiladas','amostrada','coluna','tipo','nulos','percentual_nulos','distintos','invalidos','outliers','qualidade']];
  batch.results.forEach(item => (item.analysis?.tables || []).forEach(table => table.column_analyses.forEach(column => rows.push([
    item.filename, table.name, table.rows, table.rows_analyzed, table.sampled ? 'sim' : 'não', column.name,
    column.inferred_type, column.null_count, column.null_pct, column.distinct_count, column.inconsistent_values,
    column.anomalies.reduce((sum, anomaly) => sum + anomaly.count, 0), table.quality.classification,
  ]))));
  return '\ufeff' + rows.map(row => row.map(csvCell).join(';')).join('\r\n');
}

function renderQualityDimensions(quality) {
  const dimensions = [
    ['Completude', quality.completeness_pct], ['Unicidade', quality.uniqueness_pct],
    ['Consistência', quality.consistency_pct], ['Validade', quality.validity_pct],
    ['Integridade', quality.integrity_assessed ? quality.integrity_pct : null],
  ];
  return `<div class="metric-grid">${dimensions.map(([label, value]) => `<div class="metric"><label>${label.toUpperCase()}</label><strong class="${value !== null && value < 70 ? 'quality-bad' : ''}">${value === null ? 'Não avaliada' : `${value}%`}</strong></div>`).join('')}</div>`;
}

function qualityReasons(quality) {
  const reasons = (quality.alerts || []).filter(alert => alert.severity !== 'ok');
  return `${reasons.length
    ? `<h3>Sinais considerados</h3>${reasons.map(alert => `<div class="relationship">${escapeHtml(alert.message)}${renderAlertContext(alert)}</div>`).join('')}`
    : '<p class="subtle">Nenhum sinal relevante foi identificado pelas regras atuais.</p>'}`;
}

function renderAlertContext(alert) {
  return `${alert.affected_columns ? `<div class="subtle">Colunas afetadas: ${escapeHtml(alert.affected_columns)}</div>` : ''}${alert.recommendation ? `<div class="subtle">Recomendação: ${escapeHtml(alert.recommendation)}</div>` : ''}`;
}

function qualityColumnHints(tables) {
  const inconsistent = tables.flatMap(table => table.column_analyses
    .filter(column => column.inconsistent_values > 0)
    .map(column => `${table.name}.${column.name}`));
  return inconsistent.length
    ? `<p class="subtle">Colunas com valores incompatíveis: ${inconsistent.map(escapeHtml).join(', ')}.</p>` : '';
}

const v3Views = [['overview', 'Visão Geral'], ['discoveries', 'Descobertas'], ['analyses', 'O que posso analisar?'],
  ['blueprint', 'Dashboard recomendado'], ['technical', 'Análise técnica'], ['security', 'Segurança']];
const priorityLabels = { high: 'Alta prioridade', medium: 'Média prioridade', low: 'Baixa prioridade' };
const insightTypeLabels = { ranking: 'Ranking', comparison: 'Comparação', trend: 'Tendência', kpi: 'KPI',
  distribution: 'Distribuição', outlier: 'Outlier', correlation: 'Correlação', coverage: 'Cobertura',
  segmentation: 'Segmentação', detail_table: 'Tabela detalhada' };

function renderFileDetails(report) {
  const target = document.querySelector('#file-details');
  const state = { view: 'overview', diagnosticTab: 'summary', tableIndex: 0,
    priority: 'all', type: 'all', showAllInsights: false, showAllKpis: false };
  target.innerHTML = `<nav class="v21-nav" aria-label="Navegação da análise">${v3Views.map(([id, label]) => `<button class="v21-nav-button${id === state.view ? ' active' : ''}" data-view="${id}">${label}</button>`).join('')}</nav>
    <div id="v21-content"></div>`;
  const content = target.querySelector('#v21-content');
  const render = () => {
    target.querySelectorAll('.v21-nav-button').forEach(tab => tab.classList.toggle('active', tab.dataset.view === state.view));
    const renderer = {
      overview: () => renderV3Overview(report),
      discoveries: () => renderV3Discoveries(report),
      analyses: () => renderV3Analyses(report),
      blueprint: () => renderV3Blueprint(report),
      technical: () => renderV3Technical(report, state),
      security: () => renderV21Security(report),
    }[state.view];
    content.innerHTML = renderer();
    bindV21ViewEvents(report, state, render);
  };
  target.querySelectorAll('.v21-nav-button').forEach(tab => tab.addEventListener('click', () => { state.view = tab.dataset.view; render(); }));
  render();
}

function v21Metric(label, value, note = '') {
  return `<div class="metric"><label>${escapeHtml(label)}</label><strong>${escapeHtml(value)}</strong>${note ? `<span class="subtle">${escapeHtml(note)}</span>` : ''}</div>`;
}

function renderHumanFinding(item, detailed = false) {
  const warnings = item.warnings?.length ? `<p class="warning">${item.warnings.map(escapeHtml).join(' · ')}</p>` : '';
  return `<article class="insight-card human-finding"><div class="insight-badges"><span class="priority-badge">${escapeHtml(item.importance || item.type || 'Descoberta')}</span><span class="pill">${escapeHtml(item.type || 'Análise')}</span></div>
    <h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.description)}</p>${warnings}
    ${detailed && item.why ? `<details><summary>Por que isso foi sugerido?</summary><p>${escapeHtml(item.why)}</p></details>` : ''}</article>`;
}

function renderV3Overview(report) {
  const summary = report.human_summary || {};
  const findings = summary.key_findings || [];
  const attention = summary.attention_points || [];
  const components = summary.quality_components || [];
  return `<section class="panel executive-panel"><div class="v21-eyebrow">BI SWISS KNIFE · V3.0</div><h2>${escapeHtml(summary.title || 'Resumo da análise')}</h2>
    <p class="subtle">Arquivo analisado: ${escapeHtml(report.filename)}</p><p class="business-question">${escapeHtml(summary.executive_summary || 'Resumo indisponível.')}</p></section>
    <section class="panel"><div class="table-head"><div><h2>Como estão os dados?</h2><p>${escapeHtml(summary.data_quality_summary || 'A qualidade foi avaliada pelas verificações disponíveis.')}</p></div>
    ${v21Metric('QUALIDADE GERAL', `${Number(report.quality?.score || 0).toLocaleString('pt-BR', {minimumFractionDigits: 1, maximumFractionDigits: 1})}/100`, report.quality?.classification || '')}</div>
    <div class="quality-component-grid">${components.map(component => `<div><b>${escapeHtml(component.name)}</b><strong>${Number(component.value || 0).toLocaleString('pt-BR', {maximumFractionDigits: 1})}%</strong><small>${escapeHtml(component.description)}</small></div>`).join('')}</div></section>
    <section class="panel"><h2>O que encontramos</h2><ul class="human-summary-list">${(summary.what_was_found || []).map(text => `<li>${escapeHtml(text)}</li>`).join('') || '<li>Não foi possível resumir os campos identificados.</li>'}</ul></section>
    <section class="panel"><div class="table-head"><div><h2>Principais descobertas</h2><p>Possibilidades de análise sustentadas pelos campos encontrados.</p></div><button class="secondary-button" data-go-view="discoveries">Ver descobertas</button></div>
    <div class="insight-grid">${findings.slice(0, 3).map(item => renderHumanFinding(item)).join('') || '<p class="subtle">Não há descobertas prioritárias com evidência suficiente.</p>'}</div></section>
    <section class="panel"><h2>Pontos de atenção</h2>${attention.slice(0, 3).map(point => `<div class="human-attention severity-${escapeHtml(point.severity)}"><b>${escapeHtml({critical:'Problema crítico',attention:'Atenção',information:'Informação'}[point.severity] || 'Informação')}</b><p>${escapeHtml(point.message)}</p></div>`).join('') || '<p class="subtle">Nenhum ponto de atenção foi registrado.</p>'}</section>
    <section class="panel"><h2>Dashboard recomendado</h2><p>${escapeHtml(summary.dashboard_summary || 'Ainda não há uma recomendação disponível.')}</p><button class="secondary-button" data-go-view="blueprint">Ver proposta de dashboard</button></section>`;
}

function renderV3Discoveries(report) {
  const summary = report.human_summary || {};
  const findings = summary.key_findings || [];
  const points = summary.attention_points || [];
  return `<section class="panel"><h2>Principais descobertas</h2><p>Estas são possibilidades indicadas pelos metadados analisados; não representam conclusões sobre resultados específicos.</p>
    <div class="insight-grid">${findings.map(item => renderHumanFinding(item, true)).join('') || '<p class="subtle">Não foram encontradas análises prioritárias com evidência suficiente.</p>'}</div></section>
    <section class="panel"><h2>Pontos de atenção</h2>${points.map(point => `<div class="human-attention severity-${escapeHtml(point.severity)}"><div class="insight-badges"><b>${escapeHtml({critical:'Problema crítico',attention:'Atenção',information:'Informação'}[point.severity] || 'Informação')}</b><span class="pill">${escapeHtml(point.source || 'análise')}</span></div><p>${escapeHtml(point.message)}</p></div>`).join('') || '<p class="subtle">Nenhum ponto de atenção foi registrado.</p>'}</section>`;
}

function renderV3Analyses(report) {
  const opportunities = report.human_summary?.analysis_opportunities || [];
  const insightsById = Object.fromEntries((report.insights?.items || []).map(item => [item.id, item]));
  return `<section class="panel"><h2>O que posso analisar com esses dados?</h2><p>As categorias abaixo só aparecem quando existem sugestões com evidências correspondentes.</p>
    ${opportunities.map(group => `<section class="opportunity-group"><h3>${escapeHtml(group.category)}</h3><div class="insight-grid">${(group.suggestions || []).map(suggestion => {
      const source = insightsById[suggestion.insight_id];
      return `<article class="insight-card human-finding"><h3>${escapeHtml(suggestion.question)}</h3><p>${escapeHtml(suggestion.description)}</p>${source ? `<details><summary>Por que sugerimos isso?</summary><p>${escapeHtml(suggestion.why)}</p>${(source.warnings || []).map(warning => `<p class="warning">${escapeHtml(warning)}</p>`).join('')}</details>` : ''}</article>`;
    }).join('')}</div></section>`).join('') || '<p class="subtle">Não há oportunidades com evidência suficiente para recomendar análises.</p>'}</section>`;
}

function renderV3Blueprint(report) {
  const blueprint = report.dashboard_blueprint || {};
  const findingsById = Object.fromEntries((report.human_summary?.key_findings || []).map(item => [item.insight_id, item]));
  const calculations = report.kpis?.calculation_candidates || [];
  const kpis = blueprint.kpis || [];
  return `<section class="panel executive-panel"><div class="v21-eyebrow">DASHBOARD ARCHITECT</div><h2>${escapeHtml(blueprint.title || 'Dashboard recomendado')}</h2>
    <p class="business-question">${escapeHtml(blueprint.objective || 'Organizar as análises sustentadas pelos dados.')}</p><p>${escapeHtml(blueprint.audience || '')}</p></section>
    <section class="panel"><h2>Páginas sugeridas</h2><div class="blueprint-grid">${(blueprint.recommended_pages || []).map(page => `<article class="semantic-card"><h3>${escapeHtml(page.name)}</h3><p>${escapeHtml(page.purpose)}</p><p class="subtle">${escapeHtml(page.rationale || '')}</p>
      ${page.kpis?.length ? `<h4>Indicadores</h4><ul>${page.kpis.map(kpi => `<li><b>${escapeHtml(kpi.name)}</b> — ${escapeHtml(kpi.measure?.column || kpi.calculation_candidate?.numerator || 'medida candidata')}</li>`).join('')}</ul>` : ''}
      <h4>Análises recomendadas</h4>${(page.visuals || []).map(item => `<div class="relationship"><b>${escapeHtml(item.business_question || item.title)}</b><p class="subtle">${escapeHtml(item.visual)} · ${escapeHtml(findingsById[item.id]?.description || item.type)}</p></div>`).join('') || '<p class="subtle">Sem análises priorizadas para esta página.</p>'}</article>`).join('') || '<p class="subtle">Ainda não há páginas sustentadas por evidências suficientes.</p>'}</div></section>
    <section class="panel"><h2>KPIs principais</h2><div class="insight-grid">${kpis.map(kpi => {
      const calculation = kpi.calculation_candidate;
      const description = calculation ? `${calculation.numerator} dividido por ${calculation.denominator}. Valide a regra de negócio antes de calcular.` : `${kpi.name} foi identificado como medida candidata nos dados.`;
      return `<article class="kpi-card"><h3>${escapeHtml(kpi.name)}</h3><p>${escapeHtml(description)}</p><p class="subtle">${escapeHtml(kpi.table || '')}</p></article>`;
    }).join('') || '<p class="subtle">Não há KPIs com prioridade suficiente para esta proposta.</p>'}</div>
    ${calculations.length ? `<details><summary>Cálculos candidatos (não validados)</summary>${calculations.map(item => `<p><b>${escapeHtml(item.name)}</b>: ${escapeHtml(item.numerator)} ÷ ${escapeHtml(item.denominator)}. ${escapeHtml(item.reason)} Valide a regra de negócio.</p>`).join('')}</details>` : ''}</section>
    <section class="panel"><h2>Filtros e interações</h2><h3>Filtros sugeridos</h3><div class="filter-row">${(blueprint.filters || []).map(item => `<span class="pill">${escapeHtml(item.column)}</span>`).join('') || '<span class="subtle">Nenhum filtro foi sugerido.</span>'}</div>
    ${blueprint.interactions?.length ? `<h3>Filtros cruzados possíveis</h3>${blueprint.interactions.map(item => `<p>${escapeHtml(item.source)} → ${escapeHtml(item.target)} · ${escapeHtml(item.reason)}</p>`).join('')}` : '<p class="subtle">Não há relações suficientemente confiáveis para sugerir filtros cruzados ou hierarquias.</p>'}
    ${(blueprint.design_rationale || []).map(item => `<p class="subtle">${escapeHtml(item)}</p>`).join('')}${(blueprint.warnings || []).map(item => `<p class="warning">${escapeHtml(item)}</p>`).join('')}</section>`;
}

function renderV3Technical(report, state) {
  return `<section class="panel"><h2>Análise técnica</h2><p>Os detalhes semânticos, critérios de prioridade e diagnósticos completos continuam disponíveis aqui.</p>
    <details><summary>Modelo semântico e relacionamentos</summary>${renderV21Semantics(report)}</details>
    <details><summary>Diagnóstico completo por aba</summary>${renderV21Diagnosis(report, state)}</details>
    <details><summary>Insights, evidências e avisos técnicos</summary>${renderV21Insights(report, {...state, showAllInsights: true})}</details>
    <details><summary>KPIs e cálculos candidatos</summary>${renderV21Kpis(report, {...state, showAllKpis: true})}</details></section>`;
}

function renderSemanticFields(fields, emptyText) {
  return fields?.length ? `<ul class="semantic-field-list">${fields.map(field => `<li><span>${escapeHtml(field.name)}</span><small>${escapeHtml(field.confidence)}${field.format ? ` · ${escapeHtml(field.format)}` : ''}</small></li>`).join('')}</ul>` : `<p class="subtle">${escapeHtml(emptyText)}</p>`;
}

function renderV21Semantics(report) {
  const model = report.semantic_model || {};
  const tables = model.tables || [];
  const tableCards = tables.map(table => {
    const relations = (model.relationships || []).filter(relation => relation.source_table === table.name || relation.target_table === table.name);
    const warnings = (model.semantic_warnings || []).filter(warning => warning.includes(table.name));
    return `<article class="semantic-card"><div class="card-heading"><div><h3>${escapeHtml(table.name)}</h3><p>${escapeHtml(table.table_type)} · confiança ${escapeHtml(table.confidence)}</p></div></div>
      <div class="semantic-grid"><div><h4>Dimensões</h4>${renderSemanticFields(table.dimensions, 'Nenhuma elegível')}</div>
      <div><h4>Medidas</h4>${renderSemanticFields(table.measures, 'Nenhuma elegível')}</div>
      <div><h4>Datas</h4>${renderSemanticFields(table.dates, 'Nenhuma identificada')}</div>
      <div><h4>Identificadores</h4>${renderSemanticFields(table.identifiers, 'Nenhum candidato')}</div></div>
      <details><summary>Evidências e contexto</summary><p>${escapeHtml(table.reason)}</p>${(table.evidence || []).map(item => `<p class="subtle">${escapeHtml(item)}</p>`).join('')}
      ${warnings.map(item => `<p class="warning">${escapeHtml(item)}</p>`).join('')}</details></article>`;
  }).join('');
  const relationships = (model.relationships || []).map(relation => `<article class="relationship-card"><div class="relation-flow"><b>${escapeHtml(relation.source_table)}</b><span>↓</span><b>${escapeHtml(relation.source_column)}</b><span>→</span><b>${escapeHtml(relation.target_table)}</b><span>↓</span><b>${escapeHtml(relation.target_column)}</b></div>
    <p>Confiança: ${escapeHtml(relation.confidence)} · ${escapeHtml(relation.relationship_type)}</p><details><summary>Evidências e avisos</summary><p>${escapeHtml(relation.reason)}</p><p class="subtle">Relacionamento heurístico: confirme a semântica e as chaves antes de usar.</p></details></article>`).join('');
  return `<section class="panel"><h2>Entendimento semântico</h2><p class="subtle">Classificações fornecidas pelo Semantic Model do backend; não são recalculadas na interface.</p>
    <p>Tipo global: <b>${escapeHtml(model.table_type || 'desconhecida')}</b> · confiança ${escapeHtml(model.table_type_confidence || 'low')} · domínios candidatos: ${escapeHtml((model.business_domains || []).join(', ') || 'não identificados')}</p>
    ${tableCards || '<p class="subtle">Nenhuma tabela com evidência semântica suficiente.</p>'}</section>
    <section class="panel"><h3>Relacionamentos semânticos</h3>${relationships || '<p class="subtle">Nenhum relacionamento semântico disponível.</p>'}
    ${(model.semantic_warnings || []).map(warning => `<p class="warning">${escapeHtml(warning)}</p>`).join('')}</section>`;
}

function renderInsightCard(item) {
  const references = list => (list || []).map(field => `${field.table}.${field.column}`).join(', ') || '—';
  const priority = priorityLabels[item.priority] || 'Prioridade não definida';
  return `<article class="insight-card"><div class="insight-badges"><span class="priority-badge priority-${escapeHtml(item.priority)}">${escapeHtml(priority)}</span><span class="pill">${escapeHtml(insightTypeLabels[item.type] || item.type)}</span></div>
    <h3>${escapeHtml(item.title)}</h3><p class="business-question">${escapeHtml(item.business_question)}</p>
    <div class="insight-fields"><div><small>Dimensão</small><b>${escapeHtml(references(item.dimensions))}</b></div><div><small>Medida</small><b>${escapeHtml(references(item.measures))}</b></div>${item.dates?.length ? `<div><small>Data</small><b>${escapeHtml(references(item.dates))}</b></div>` : ''}</div>
    <p><small>Visual recomendado</small><br><b>${escapeHtml(item.visual)}</b> · confiança ${escapeHtml(item.confidence)}</p>
    <details><summary>Por que foi sugerido?</summary><p>${escapeHtml(item.reason)}</p><p><b>Evidências:</b></p><ul>${(item.evidence || []).map(evidence => `<li>${escapeHtml(evidence)}</li>`).join('')}</ul>${(item.warnings || []).map(warning => `<p class="warning">${escapeHtml(warning)}</p>`).join('')}</details></article>`;
}

function renderV21Insights(report, state) {
  const items = report.insights?.items || [];
  const filtered = items.filter(item => (state.priority === 'all' || item.priority === state.priority)
    && (state.type === 'all' || item.type === state.type));
  const topLimit = Number(report.insights?.top_limit || 12);
  const visible = state.showAllInsights ? filtered : filtered.slice(0, topLimit);
  const typeOptions = Object.keys(insightTypeLabels).map(type => `<option value="${escapeHtml(type)}"${state.type === type ? ' selected' : ''}>${escapeHtml(insightTypeLabels[type])}</option>`).join('');
  return `<section class="panel"><div class="table-head"><div><h2>Top ${topLimit} análises</h2><p class="subtle">${Number(report.insights?.duplicates_removed || 0)} duplicata(s) semântica(s) removida(s) · ordenadas pela relevância estimada. O score não é uma métrica empresarial.</p></div><label>Tipo <select id="insight-type-filter" class="table-select"><option value="all">Todos os tipos</option>${typeOptions}</select></label></div>
    <div class="filter-row">${[['all','Todas'],['high','Alta'],['medium','Média'],['low','Baixa']].map(([key,label]) => `<button class="filter-button${state.priority === key ? ' active' : ''}" data-priority="${key}">${label}</button>`).join('')}</div>
    <p class="subtle">${filtered.length} análise(s) compatível(is) com os filtros.</p><div class="insight-grid">${visible.map(renderInsightCard).join('') || '<p class="subtle">Nenhuma análise atende a estes filtros.</p>'}</div>
    ${filtered.length > topLimit ? `<button id="toggle-insights" class="secondary-button">${state.showAllInsights ? 'Mostrar Top 12' : 'Ver todas as análises'}</button>` : ''}</section>`;
}

function renderV21Kpis(report, state) {
  const kpis = report.kpis?.suggested || [];
  const primaryKpis = kpis.filter(kpi => kpi.priority === 'high' || kpi.priority === 'medium');
  const visible = state.showAllKpis ? kpis : primaryKpis.slice(0, 8);
  const calculations = report.kpis?.calculation_candidates || [];
  return `<section class="panel"><h2>KPIs principais</h2><p class="subtle">Priorizados pela relevância; a prioridade não valida a regra de negócio.</p><div class="insight-grid">${visible.map(kpi => `<article class="kpi-card"><span class="priority-badge priority-${escapeHtml(kpi.priority)}">${escapeHtml(priorityLabels[kpi.priority] || kpi.priority)}</span><h3>${escapeHtml(kpi.name)}</h3><p>${escapeHtml(kpi.table)} · ${escapeHtml(kpi.measure?.column || kpi.calculation_candidate?.numerator || 'cálculo candidato')}</p><p>Confiança: ${escapeHtml(kpi.confidence)}</p><details><summary>Justificativa</summary><p>${escapeHtml(kpi.reason)}</p></details></article>`).join('') || '<p class="subtle">Nenhum KPI de prioridade alta ou média; confira as sugestões complementares.</p>'}</div>
    ${kpis.length > 8 || kpis.some(kpi => kpi.priority === 'low') ? `<button id="toggle-kpis" class="secondary-button">${state.showAllKpis ? 'Mostrar principais' : 'Ver todas as sugestões de KPI'}</button>` : ''}</section>
    <section class="panel"><h3>Cálculos que podem ser derivados</h3><p class="subtle">Candidatos não validados; nenhuma fórmula ou DAX foi executado.</p>${calculations.map(calc => `<article class="calculation-card"><div><span class="pill">CÁLCULO CANDIDATO</span> · confiança ${escapeHtml(calc.confidence)}</div><h3>${escapeHtml(calc.name)}</h3><div class="fraction"><span>${escapeHtml(calc.numerator)}</span><i></i><span>${escapeHtml(calc.denominator)}</span></div><p>${escapeHtml(calc.reason)}</p><p class="subtle">Valide a fórmula, os filtros e a regra de negócio antes de calcular.</p></article>`).join('') || '<p class="subtle">Nenhum cálculo candidato foi identificado.</p>'}</section>`;
}

function renderV21Blueprint(report) {
  const blueprint = report.dashboard_blueprint || {};
  return `<section class="panel"><div class="v21-eyebrow">DASHBOARD BLUEPRINT</div><h2>${escapeHtml(blueprint.title || 'Blueprint')}</h2><p>${escapeHtml(blueprint.objective || 'Sem objetivo disponível.')}</p>
    <div class="blueprint-grid">${(blueprint.recommended_pages || []).map(page => `<article class="semantic-card"><h3>${escapeHtml(page.name)}</h3><p>${escapeHtml(page.purpose)}</p><h4>Análises</h4>${(page.visuals || []).map(item => `<div class="relationship"><b>${escapeHtml(item.title)}</b><div class="subtle">${escapeHtml(item.visual)} · ${escapeHtml(priorityLabels[item.priority] || item.priority)}</div></div>`).join('') || '<p class="subtle">Sem visuais sugeridos.</p>'}</article>`).join('') || '<p class="subtle">Nenhuma página foi sugerida.</p>'}</div>
    <h3>KPIs candidatos</h3><div class="filter-row">${(blueprint.kpis || []).map(kpi => `<span class="pill">${escapeHtml(kpi.name)}</span>`).join('') || '<span class="subtle">Nenhum</span>'}</div>
    <h3>Filtros candidatos</h3><div class="filter-row">${(blueprint.filters || []).map(filter => `<span class="pill">${escapeHtml(filter.column)}</span>`).join('') || '<span class="subtle">Nenhum</span>'}</div>
    ${(blueprint.warnings || []).map(warning => `<p class="warning">${escapeHtml(warning)}</p>`).join('')}</section>`;
}

function renderV21Security(report) {
  const security = report.security || {};
  return `<section class="panel"><h2>Segurança e privacidade</h2><div class="metric-grid">${v21Metric('PROCESSAMENTO', 'Local')}${v21Metric('MACROS EXECUTADAS', 'Não')}${v21Metric('RELAÇÕES EXTERNAS SEGUIDAS', 'Não')}${v21Metric('CONEXÕES ATUALIZADAS', 'Não')}</div>
    <p>Conteúdo potencialmente ativo detectado: ${security.active_content_detected ? 'Sim, não executado' : 'Não'} · relações externas detectadas: ${Number(security.external_relationship_count || 0)}.</p>
    <p class="subtle">Nenhum serviço externo é chamado pela descoberta. Os cards usam campos e evidências agregadas; não exibem linhas de registros.</p>
    ${[...(report.security_warnings || []), ...(report.warnings || [])].map(warning => `<p class="warning">${escapeHtml(warning)}</p>`).join('')}</section>`;
}

function renderV21Diagnosis(report, state) {
  const tabs = [['summary', 'Resumo'], ['structure', 'Estrutura'], ['columns', 'Colunas'], ['quality', 'Qualidade'], ['keys', 'Chaves'], ['relationships', 'Relacionamentos'], ['anomalies', 'Anomalias'], ['statistics', 'Estatísticas']];
  if (!report.tables.length) return '<div class="panel">Não há abas para diagnosticar.</div>';
  const table = report.tables[state.tableIndex] || report.tables[0];
  return `<div class="panel table-head"><label for="table-select">Tabela/aba</label><select class="table-select" id="table-select">${report.tables.map((item, i) => `<option value="${i}"${i === state.tableIndex ? ' selected' : ''}>${escapeHtml(item.name)}</option>`).join('')}</select></div>
    <nav class="diagnostic-tabs" aria-label="Seções do diagnóstico">${tabs.map(([id, label]) => `<button class="diagnostic-tab${id === state.diagnosticTab ? ' active' : ''}" data-tab="${id}">${label}</button>`).join('')}</nav>
    <div id="diagnostic-content">${tabContent(state.diagnosticTab, report, table)}</div>`;
}

function bindV21ViewEvents(report, state, render) {
  document.querySelectorAll('[data-go-view]').forEach(button => button.addEventListener('click', () => {
    state.view = button.dataset.goView;
    render();
  }));
  document.querySelectorAll('.diagnostic-tab').forEach(tab => tab.addEventListener('click', () => { state.diagnosticTab = tab.dataset.tab; render(); }));
  document.querySelector('#table-select')?.addEventListener('change', event => { state.tableIndex = Number(event.target.value); render(); });
  document.querySelectorAll('[data-priority]').forEach(button => button.addEventListener('click', () => { state.priority = button.dataset.priority; render(); }));
  document.querySelector('#insight-type-filter')?.addEventListener('change', event => { state.type = event.target.value; render(); });
  document.querySelector('#toggle-insights')?.addEventListener('click', () => { state.showAllInsights = !state.showAllInsights; render(); });
  document.querySelector('#toggle-kpis')?.addEventListener('click', () => { state.showAllKpis = !state.showAllKpis; render(); });
}

function flattenStats(stats, prefix = '') {
  return Object.entries(stats || {}).flatMap(([key, value]) => {
    const label = prefix ? `${prefix} / ${key}` : key;
    return value && typeof value === 'object' ? flattenStats(value, label) : [[label, value]];
  });
}

function tabContent(tab, report, table) {
  if (['failed', 'error', 'skipped'].includes(table.status)) return `<div class="panel"><h3>Aba não processada — ${escapeHtml(table.name)}</h3><p>${escapeHtml(table.error_message || 'A leitura desta aba não foi concluída.')}</p><p class="subtle">As outras abas legíveis continuam disponíveis no relatório.</p></div>`;
  if (tab === 'summary') return `<div class="panel"><h3>Diagnóstico do arquivo</h3><p>Qualidade geral: <b>${escapeHtml(report.quality.classification)}</b> (${report.quality.score}/100), segundo as faixas e pesos configurados.</p>${renderQualityDimensions(report.quality)}${qualityReasons(report.quality)}${qualityColumnHints(report.tables)}<p class="subtle">${report.tables.some(item => item.sampled) ? 'Alguns indicadores foram calculados sobre amostra limitada; consulte os avisos.' : 'As tabelas foram perfiladas sem amostragem.'}</p></div><div class="panel">${renderTableSummary(report.tables)}</div>`;
  if (tab === 'structure') return '<div class="panel"><h3>' + escapeHtml(table.name) + ' — ' + escapeHtml(table.table_type) + '</h3><p>' + escapeHtml(table.table_type_reason) + ' Confiança: ' + escapeHtml(table.table_type_confidence) + '.</p><p>Status: ' + escapeHtml(table.status) + ' · cabeçalho ' + escapeHtml(table.header_detection?.status || 'não informado') + (table.header_row_used ? ', linha ' + table.header_row_used : '') + ' (' + escapeHtml(table.header_detection?.header_source || '—') + ').</p><p>' + Number(table.rows_available ?? table.rows).toLocaleString('pt-BR') + ' linhas disponíveis; ' + table.rows_analyzed.toLocaleString('pt-BR') + ' analisadas; ' + Number(table.rows_empty || 0).toLocaleString('pt-BR') + ' vazias internas; ' + Number(table.trailing_empty_rows || 0).toLocaleString('pt-BR') + ' vazias finais; sampling ' + (table.sampled ? escapeHtml(table.sampling_method || 'sim') : 'não') + '.</p><p>' + table.columns + ' colunas; ' + table.empty_columns + ' colunas vazias e ' + table.duplicate_rows + ' linhas duplicadas na amostra.</p>' + (table.sampled ? '<div class="warning">Indicadores calculados sobre amostra uniforme dos registros preenchidos.</div>' : '') + '</div><div class="panel">' + renderTableSummary([table]) + '</div>';
  if (tab === 'columns') return `<div class="panel"><h3>Perfil e tipo provável de cada coluna</h3><div class="scroll"><table><thead><tr><th>COLUNA</th><th>PAPEL SEMÂNTICO</th><th>TIPO INFERIDO</th><th>TIPO FÍSICO</th><th>CONFIANÇA / MOTIVO</th><th>VALORES</th><th>NULOS</th><th>PREENCHIDO</th><th>ÚNICOS</th><th>CARDINALIDADE</th><th>REPETIDOS</th><th>INVÁLIDOS</th><th>ZEROS</th><th>NEGATIVOS</th><th>ESTATÍSTICAS AGREGADAS</th></tr></thead><tbody>${table.column_analyses.map(column => `<tr><td>${escapeHtml(column.name)}${column.sensitive ? '<div class="subtle">Estatísticas suprimidas por possível sensibilidade</div>' : ''}</td><td>${escapeHtml(column.semantic_role || 'unknown')} (${escapeHtml(column.semantic_role_confidence || 'low')})</td><td>${escapeHtml(column.inferred_type)}</td><td>${escapeHtml(column.physical_type || column.original_type)}</td><td>${escapeHtml(column.confidence)}<div class="subtle">${escapeHtml(column.type_reason)}</div></td><td>${column.value_count.toLocaleString('pt-BR')}</td><td>${column.null_count} (${column.null_pct}%)<div class="subtle">${escapeHtml(column.null_classification)}; avalie se a ausência é esperada.</div></td><td>${column.completeness_pct}%</td><td>${column.distinct_count} (${column.distinct_pct}%)</td><td>${escapeHtml(column.cardinality)}</td><td>${column.duplicate_count}</td><td>${column.inconsistent_values}</td><td>${column.zero_count ?? '—'}</td><td>${column.negative_count ?? '—'}</td><td>${escapeHtml(flattenStats(column.statistics).map(([key, value]) => `${key}: ${value}`).join(' · ') || '—')}</td></tr>`).join('')}</tbody></table></div></div>`;
  if (tab === 'quality') return `<div class="panel"><h3>Qualidade — ${escapeHtml(table.name)}</h3><p><b>${escapeHtml(table.quality.classification)}</b> · ${table.quality.score}/100</p><p class="subtle">O score é um resumo heurístico. Uma aba auxiliar, template ou destinada a preenchimento pode ter score baixo sem representar erro; considere o contexto e os sinais abaixo.</p>${renderQualityDimensions(table.quality)}${qualityColumnHints([table])}${table.quality.alerts.map(alert => `<div class="relationship"><span class="pill severity-${escapeHtml(alert.severity)}">${{critical:'🔴 Crítico',attention:'🟠 Atenção',information:'🟡 Informação',ok:'🟢 OK'}[alert.severity] || escapeHtml(alert.severity)}</span> ${escapeHtml(alert.message)}${renderAlertContext(alert)}</div>`).join('')}<h3>Ausências por coluna</h3>${table.column_analyses.filter(column => column.null_count).map(column => `<div class="relationship"><b>${escapeHtml(column.name)}</b>: ${column.null_count} (${column.null_pct}%) — ${escapeHtml(column.null_classification)}. Avalie se a ausência é esperada.</div>`).join('') || '<div class="subtle">Nenhum valor ausente detectado.</div>'}</div>`;
  if (tab === 'keys') {
    const labels = { strong_candidate: 'Candidato forte a identificador', possible_identifier: 'Possível identificador',
      high_uniqueness_measure: 'Medida altamente única; não tratar como chave',
      high_uniqueness_unconfirmed: 'Alta unicidade sem evidência semântica de chave' };
    const highUnique = table.column_analyses.filter(column => labels[column.key_assessment]
      && !['strong_candidate', 'possible_identifier'].includes(column.key_assessment));
    return `<div class="panel"><h3>Possíveis identificadores — ${escapeHtml(table.name)}</h3>${table.key_candidates.length ? table.key_candidates.map(key => `<div class="relationship"><b>${key.columns.map(escapeHtml).join(' + ')}</b> · ${escapeHtml(labels[key.assessment] || 'Possível identificador')} · confiança ${escapeHtml(key.confidence)} · ${key.uniqueness_pct}% única${key.completeness_pct === undefined ? '' : ` · ${key.completeness_pct}% preenchida`}<div class="subtle">${key.reasons.map(escapeHtml).join(' · ')}</div></div>`).join('') : '<div class="subtle">Nenhuma coluna foi classificada como identificador candidato.</div>'}<h3>Alta unicidade sem evidência de chave</h3>${highUnique.length ? highUnique.map(column => `<div class="relationship"><b>${escapeHtml(column.name)}</b> · ${escapeHtml(labels[column.key_assessment])} · ${column.distinct_pct}% única<div class="subtle">${column.key_reasons.map(escapeHtml).join(' · ')}</div></div>`).join('') : '<div class="subtle">Nenhuma coluna nesta condição.</div>'}<p class="subtle">Unicidade isolada não comprova uma chave. Confira regras de negócio e contexto antes de usar como identificador.</p></div>`;
  }
  if (tab === 'relationships') return `<div class="panel"><h3>Possíveis relacionamentos</h3>${report.relationships.length ? report.relationships.map(relation => `<div class="relationship"><b>${escapeHtml(relation.source_table)}.${escapeHtml(relation.source_column)}</b> → <b>${escapeHtml(relation.target_table)}.${escapeHtml(relation.target_column)}</b><div class="subtle">Possível ${escapeHtml(relation.cardinality)} · confiança ${escapeHtml(relation.confidence)} · cobertura ${relation.coverage_pct}% · ${relation.matched_values} correspondências · ${relation.unmatched_values} sem correspondência</div><div class="subtle">${escapeHtml(relation.reason)}</div></div>`).join('') : '<div class="subtle">Nenhum relacionamento provável identificado entre abas deste arquivo.</div>'}</div>`;
  if (tab === 'anomalies') return `<div class="panel"><h3>Anomalias estatísticas — ${escapeHtml(table.name)}</h3>${table.column_analyses.flatMap(column => column.anomalies).length ? table.column_analyses.flatMap(column => column.anomalies).map(anomaly => `<div class="relationship"><span class="pill">${escapeHtml(anomaly.severity)}</span> <b>${escapeHtml(anomaly.column)}</b>: ${anomaly.count} possíveis outliers pelo método ${escapeHtml(anomaly.method)}.<div class="subtle">${escapeHtml(anomaly.description)}</div></div>`).join('') : '<div class="subtle">Nenhuma anomalia estatística detectada pelas regras atuais.</div>'}</div>`;
  return `<div class="panel"><h3>Estatísticas agregadas — ${escapeHtml(table.name)}</h3>${table.column_analyses.map(column => `<div class="relationship"><b>${escapeHtml(column.name)}</b> (${escapeHtml(column.inferred_type)})<div class="subtle">${column.sensitive ? 'Estatísticas suprimidas por possível sensibilidade.' : escapeHtml(flattenStats(column.statistics).map(([key, value]) => `${key}: ${value}`).join(' · ') || 'Sem estatísticas aplicáveis.')}</div></div>`).join('')}</div>`;
}

function renderTableSummary(tables) {
  return `<div class="scroll"><table><thead><tr><th>WORKSHEET</th><th>STATUS</th><th>CABEÇALHO</th><th>LINHAS DISPONÍVEIS / ANALISADAS</th><th>VAZIAS INTERNAS / FINAIS</th><th>AMOSTRAGEM</th><th>COLUNAS</th><th>QUALIDADE</th></tr></thead><tbody>${tables.map(table => `<tr><td>${escapeHtml(table.name)}</td><td>${escapeHtml(table.status || 'completed')}${table.error_message ? `<div class="subtle">${escapeHtml(table.error_message)}</div>` : ''}</td><td>${escapeHtml(table.header_detection?.status || '—')}${table.header_row_used ? `<div class="subtle">linha ${table.header_row_used} · ${escapeHtml(table.header_detection?.header_source || 'worksheet')}</div>` : ''}</td><td>${Number(table.rows_available ?? table.rows).toLocaleString('pt-BR')} / ${Number(table.rows_analyzed).toLocaleString('pt-BR')}</td><td>${Number(table.rows_empty || table.empty_rows || 0).toLocaleString('pt-BR')} / ${Number(table.trailing_empty_rows || 0).toLocaleString('pt-BR')}</td><td>${table.sampled ? escapeHtml(table.sampling_method || 'uniforme') : 'não'}</td><td>${table.columns} (${table.columns_analyzed} analisadas)</td><td>${escapeHtml(table.quality.classification)} (${table.quality.score})</td></tr>`).join('')}</tbody></table></div>`;
}
