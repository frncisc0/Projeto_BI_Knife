const input = document.querySelector('#file-input');
const folderInput = document.querySelector('#folder-input');
const drop = document.querySelector('#drop-zone');
const button = document.querySelector('#analyze-button');
const statusEl = document.querySelector('#status');
const resultEl = document.querySelector('#results');
const maxFiles = 50;
let selectedFiles = [];

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
  const items = [...(event.dataTransfer?.items || [])];
  const entries = items.map(item => item.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.length) {
    setFiles([...(event.dataTransfer?.files || [])]);
    return;
  }
  try {
    const groups = await Promise.all(entries.map(readEntry));
    setFiles(groups.flat());
  } catch {
    showStatus('Não foi possível ler a pasta solta. Tente escolhê-la pelo botão “Escolher pasta”.', 'error');
  }
});

function readEntry(entry) {
  if (entry.isFile) {
    return new Promise((resolve, reject) => entry.file(file => {
      Object.defineProperty(file, '_relativePath', { value: entry.fullPath.replace(/^\/+/, ''), configurable: true });
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
  return file._relativePath || file.webkitRelativePath || file.name;
}

function setFiles(files) {
  statusEl.className = 'status';
  statusEl.textContent = '';
  resultEl.hidden = true;
  const valid = files.filter(file => /\.(xlsx|csv)$/i.test(file.name));
  const unique = new Map();
  valid.forEach(file => unique.set(`${fileLabel(file)}:${file.size}:${file.lastModified}`, file));
  selectedFiles = [...unique.values()];
  const rejected = files.length - selectedFiles.length;
  if (selectedFiles.length > maxFiles) {
    selectedFiles = [];
    showStatus(`Selecione no máximo ${maxFiles} arquivos por vez.`, 'error');
  } else if (!selectedFiles.length) {
    showStatus('Não encontrei arquivos .xlsx ou .csv na seleção.', 'error');
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
  const data = new FormData();
  selectedFiles.forEach(file => data.append('uploads', file, fileLabel(file)));
  button.disabled = true;
  button.textContent = 'Analisando…';
  showStatus(`Analisando ${selectedFiles.length} arquivo(s) localmente. A duração depende do tamanho dos dados.`);
  try {
    const response = await fetch('/api/analyze-batch', { method: 'POST', body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Falha ao analisar os arquivos.');
    renderBatch(payload);
    const succeeded = payload.results.filter(item => item.analysis).length;
    const failed = payload.results.length - succeeded;
    showStatus(failed ? `${succeeded} arquivo(s) analisado(s); ${failed} com erro.` : `${succeeded} arquivo(s) analisado(s).`, failed ? '' : 'success');
  } catch (error) {
    showStatus(error.message || 'Não foi possível analisar os arquivos.', 'error');
  } finally {
    button.disabled = selectedFiles.length === 0;
    button.innerHTML = 'Analisar arquivos <span>→</span>';
  }
});

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
  const totalRows = successes.reduce((sum, item) => sum + item.analysis.tables.reduce((n, table) => n + table.rows, 0), 0);
  const totalColumns = successes.reduce((sum, item) => sum + item.analysis.tables.reduce((n, table) => n + table.columns, 0), 0);
  const issueCount = successes.reduce((sum, item) => sum + item.analysis.tables.reduce((tableSum, table) =>
    tableSum + table.duplicate_rows + table.column_analyses.reduce((columnSum, column) =>
      columnSum + column.null_count + (column.empty ? 1 : 0) + column.inconsistent_values, 0), 0), 0);
  const fileRows = batch.results.map(item => `<div class="relationship"><b>${escapeHtml(item.filename)}</b> <span class="subtle">${item.analysis ? 'Analisado' : `Erro: ${escapeHtml(item.error)}`}</span></div>`).join('');
  const details = successes.length ? `<div class="panel"><div class="table-head"><h3>Detalhes do arquivo</h3><select class="table-select" id="file-select">${successes.map((item, i) => `<option value="${i}">${escapeHtml(item.filename)}</option>`).join('')}</select></div><div id="file-details"></div></div>` : '<div class="panel subtle">Nenhum arquivo pôde ser analisado.</div>';
  resultEl.hidden = false;
  resultEl.innerHTML = `<div class="results-head"><div><h2>Visão geral da seleção</h2><div class="subtle">${successes.length} de ${batch.file_count} arquivo(s) analisado(s)</div></div><button id="export" class="secondary-button">↓ Exportar relatório</button></div>
    <div class="metric-grid"><div class="metric"><label>LINHAS</label><strong>${totalRows.toLocaleString('pt-BR')}</strong></div><div class="metric"><label>COLUNAS</label><strong>${totalColumns.toLocaleString('pt-BR')}</strong></div><div class="metric"><label>ALERTAS DE QUALIDADE</label><strong class="${issueCount ? 'quality-bad' : ''}">${issueCount.toLocaleString('pt-BR')}</strong></div></div>
    <div class="panel"><h3>Arquivos selecionados</h3>${fileRows}</div>${details}`;
  resultEl.querySelector('#export').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify(batch, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'bi-swiss-knife-relatorio.json';
    link.click();
    URL.revokeObjectURL(link.href);
  });
  if (successes.length) {
    const selector = resultEl.querySelector('#file-select');
    const update = () => renderFileDetails(successes[Number(selector.value)].analysis);
    selector.addEventListener('change', update);
    update();
  }
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderFileDetails(report) {
  const target = document.querySelector('#file-details');
  target.innerHTML = `<div class="subtle">${escapeHtml(report.filename)} · ${report.tables.length} tabela(s) · ${(report.file_size_bytes / 1048576).toFixed(2)} MB</div>
    <div class="panel"><div class="table-head"><h3>Perfil das colunas</h3><select class="table-select" id="table-select">${report.tables.map((table, i) => `<option value="${i}">${escapeHtml(table.name)}</option>`).join('')}</select></div><div id="columns-table" class="scroll"></div></div>
    <div class="panel"><h3>Prévia dos dados</h3><div id="preview-table" class="scroll preview"></div></div>
    <div class="panel"><h3>Relacionamentos sugeridos</h3><div id="relations"></div></div>
    ${report.warnings.map(warning => `<div class="warning">⚠ ${escapeHtml(warning)}</div>`).join('')}`;
  const selector = target.querySelector('#table-select');
  const update = () => {
    const table = report.tables[Number(selector.value)];
    renderColumns(table);
    renderPreview(table);
  };
  selector.addEventListener('change', update);
  update();
  const relations = target.querySelector('#relations');
  relations.innerHTML = report.relationships.length ? report.relationships.map(relation => `<div class="relationship"><b>${escapeHtml(relation.source_table)}.${escapeHtml(relation.source_column)}</b> → <b>${escapeHtml(relation.target_table)}.${escapeHtml(relation.target_column)}</b> <span class="subtle">${relation.coverage_pct}% cobertura · ${relation.confidence}</span></div>`).join('') : '<div class="subtle">Nenhum relacionamento provável encontrado neste arquivo.</div>';
}

function renderColumns(table) {
  document.querySelector('#columns-table').innerHTML = `<table><thead><tr><th>COLUNA</th><th>TIPO</th><th>NULOS</th><th>DISTINTOS</th><th>REPETIDOS</th><th>INCONSISTÊNCIAS</th><th>CHAVE?</th><th>ESTATÍSTICAS / MAIS FREQUENTES</th></tr></thead><tbody>${table.column_analyses.map(column => {
    const stats = Object.entries(column.statistics).map(([key, value]) => `${key}: ${value}`).join(' · ');
    const top = column.top_values.slice(0, 4).map(value => `${value.value} (${value.count})`).join(' · ');
    return `<tr><td>${escapeHtml(column.name)}</td><td><span class="pill">${escapeHtml(column.inferred_type)}</span></td><td>${column.null_count} <span class="subtle">(${column.null_pct}%)</span></td><td>${column.distinct_count}</td><td>${column.duplicate_count}</td><td>${column.inconsistent_values}</td><td>${column.key_candidate ? '✓ provável' : '—'}</td><td>${escapeHtml([stats, top].filter(Boolean).join(' | ') || '—')}</td></tr>`;
  }).join('')}</tbody></table>`;
}

function renderPreview(table) {
  const keys = table.preview[0] ? Object.keys(table.preview[0]) : [];
  document.querySelector('#preview-table').innerHTML = keys.length ? `<table><thead><tr>${keys.map(key => `<th>${escapeHtml(key)}</th>`).join('')}</tr></thead><tbody>${table.preview.map(row => `<tr>${keys.map(key => `<td title="${escapeHtml(row[key])}">${escapeHtml(row[key]) || '—'}</td>`).join('')}</tr>`).join('')}</tbody></table>` : '<div class="subtle">Sem linhas para exibir.</div>';
}
