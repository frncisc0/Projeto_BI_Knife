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
    ? `<h3>Sinais considerados</h3>${reasons.map(alert => `<div class="relationship">${escapeHtml(alert.message)}</div>`).join('')}`
    : '<p class="subtle">Nenhum sinal relevante foi identificado pelas regras atuais.</p>'}`;
}

function qualityColumnHints(tables) {
  const inconsistent = tables.flatMap(table => table.column_analyses
    .filter(column => column.inconsistent_values > 0)
    .map(column => `${table.name}.${column.name}`));
  return inconsistent.length
    ? `<p class="subtle">Colunas com valores incompatíveis: ${inconsistent.map(escapeHtml).join(', ')}.</p>` : '';
}

function renderFileDetails(report) {
  const target = document.querySelector('#file-details');
  const tabs = [['summary', 'Resumo'], ['structure', 'Estrutura'], ['columns', 'Colunas'], ['quality', 'Qualidade'], ['keys', 'Chaves'], ['relationships', 'Relacionamentos'], ['anomalies', 'Anomalias'], ['statistics', 'Estatísticas']];
  const securityPanel = report.security ? `<div class="panel"><h3>Segurança do arquivo</h3><div class="relationship">Conteúdo potencialmente ativo detectado: ${report.security.active_content_detected ? 'Sim' : 'Não'}</div><div class="relationship">Tipos identificados: ${escapeHtml(report.security.active_content_types.join(', ') || 'nenhum')}</div><div class="relationship">Conteúdo ativo executado: Não · ação: ${escapeHtml(report.security.active_content_action)}</div><div class="relationship">Relações externas seguidas: Não (${report.security.external_relationship_count} detectada(s)) · conexões externas atualizadas: Não</div><div class="relationship">Macros executadas: Não · objetos incorporados executados: Não · fórmulas recalculadas: Não (${escapeHtml(report.security.formulas_action)})</div></div>` : '';
  target.innerHTML = `<div class="subtle">${escapeHtml(report.filename)} · status ${escapeHtml(report.status)} · ${report.tables.length} aba(s) · ${(report.file_size_bytes / 1048576).toFixed(2)} MB · analisado em ${escapeHtml(new Date(report.analyzed_at).toLocaleString('pt-BR'))}</div>
    <div class="metric-grid dashboard-grid"><div class="metric"><label>TABELAS</label><strong>${report.tables.length}</strong></div><div class="metric"><label>LINHAS</label><strong>${report.tables.reduce((sum, table) => sum + table.rows, 0).toLocaleString('pt-BR')}</strong></div><div class="metric"><label>COLUNAS</label><strong>${report.tables.reduce((sum, table) => sum + table.columns, 0).toLocaleString('pt-BR')}</strong></div><div class="metric"><label>NULOS</label><strong>${report.tables.reduce((sum, table) => sum + table.column_analyses.reduce((n, column) => n + column.null_count, 0), 0).toLocaleString('pt-BR')}</strong></div><div class="metric"><label>DUPLICIDADES</label><strong>${report.tables.reduce((sum, table) => sum + table.duplicate_rows, 0).toLocaleString('pt-BR')}</strong></div><div class="metric"><label>CHAVES POSSÍVEIS</label><strong>${report.tables.reduce((sum, table) => sum + table.key_candidates.length, 0)}</strong></div><div class="metric"><label>RELACIONAMENTOS</label><strong>${report.relationships.length}</strong></div><div class="metric"><label>ALERTAS</label><strong>${report.tables.reduce((sum, table) => sum + table.quality.alerts.filter(alert => alert.severity !== 'ok').length, 0)}</strong></div><div class="metric"><label>QUALIDADE</label><strong class="${report.quality.classification === 'Crítica' ? 'quality-bad' : ''}">${escapeHtml(report.quality.classification)}</strong></div></div>
    <div class="panel table-head"><label for="table-select">Tabela/aba</label><select class="table-select" id="table-select">${report.tables.map((table, i) => `<option value="${i}">${escapeHtml(table.name)}</option>`).join('')}</select></div>
    <nav class="diagnostic-tabs" aria-label="Seções do diagnóstico">${tabs.map(([id, label], index) => `<button class="diagnostic-tab${index === 0 ? ' active' : ''}" data-tab="${id}">${label}</button>`).join('')}</nav>
    <div id="diagnostic-content"></div>
    ${securityPanel}
    <div class="panel privacy-note">Prévia dos dados desativada: este relatório não contém valores de células nem rótulos de categorias.</div>
    <div class="panel"><h3>Privacidade e importação</h3><div class="subtle">SHA-256: ${escapeHtml(report.file_sha256)} · configurações CSV e limites registrados no relatório JSON.</div>${report.security_warnings.map(warning => `<div class="subtle">${escapeHtml(warning)}</div>`).join('')}</div>
    ${report.warnings.map(warning => `<div class="warning">⚠ ${escapeHtml(warning)}</div>`).join('')}`;
  let activeTab = 'summary';
  const selector = target.querySelector('#table-select');
  const content = target.querySelector('#diagnostic-content');
  const renderTab = () => {
    const table = report.tables[Number(selector.value)];
    target.querySelectorAll('.diagnostic-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.tab === activeTab));
    content.innerHTML = tabContent(activeTab, report, table);
  };
  selector.addEventListener('change', renderTab);
  target.querySelectorAll('.diagnostic-tab').forEach(tab => tab.addEventListener('click', () => { activeTab = tab.dataset.tab; renderTab(); }));
  renderTab();
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
  if (tab === 'quality') return `<div class="panel"><h3>Qualidade — ${escapeHtml(table.name)}</h3><p><b>${escapeHtml(table.quality.classification)}</b> · ${table.quality.score}/100</p>${renderQualityDimensions(table.quality)}${qualityColumnHints([table])}${table.quality.alerts.map(alert => `<div class="relationship"><span class="pill severity-${escapeHtml(alert.severity)}">${{critical:'🔴 Crítico',attention:'🟠 Atenção',information:'🟡 Informação',ok:'🟢 OK'}[alert.severity] || escapeHtml(alert.severity)}</span> ${escapeHtml(alert.message)}</div>`).join('')}<h3>Ausências por coluna</h3>${table.column_analyses.filter(column => column.null_count).map(column => `<div class="relationship"><b>${escapeHtml(column.name)}</b>: ${column.null_count} (${column.null_pct}%) — ${escapeHtml(column.null_classification)}. Avalie se a ausência é esperada.</div>`).join('') || '<div class="subtle">Nenhum valor ausente detectado.</div>'}</div>`;
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
