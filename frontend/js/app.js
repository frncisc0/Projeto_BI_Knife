const input=document.querySelector('#file-input');
const drop=document.querySelector('#drop-zone');
const button=document.querySelector('#analyze-button');
const statusEl=document.querySelector('#status');
const resultEl=document.querySelector('#results');
let selectedFile=null;

document.querySelector('#browse').addEventListener('click',()=>input.click());
input.addEventListener('change',()=>setFile(input.files[0]));
['dragenter','dragover'].forEach(event=>drop.addEventListener(event,e=>{e.preventDefault();drop.classList.add('dragover')}));
['dragleave','drop'].forEach(event=>drop.addEventListener(event,e=>{e.preventDefault();drop.classList.remove('dragover')}));
drop.addEventListener('drop',e=>setFile(e.dataTransfer.files[0]));
function setFile(file){
  statusEl.className='status';statusEl.textContent='';resultEl.hidden=true;
  if(!file)return;
  if(!/\.(xlsx|csv)$/i.test(file.name)){showStatus('Formato inválido. Selecione um arquivo .xlsx ou .csv.','error');return}
  selectedFile=file;document.querySelector('#file-name').textContent=`${file.name} · ${(file.size/1048576).toFixed(2)} MB`;document.querySelector('#file-name').hidden=false;button.disabled=false;
}
button.addEventListener('click',async()=>{
  if(!selectedFile)return;
  const data=new FormData();data.append('upload',selectedFile);button.disabled=true;button.textContent='Analisando…';showStatus('O arquivo está sendo analisado localmente.');
  try{const response=await fetch('/api/analyze',{method:'POST',body:data});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||'Falha ao analisar.');render(payload);showStatus('Análise concluída.','success')}
  catch(error){showStatus(error.message||'Não foi possível analisar o arquivo.','error')}
  finally{button.disabled=false;button.innerHTML='Analisar arquivo <span>→</span>'}
});
function showStatus(message,type=''){statusEl.textContent=message;statusEl.className=`status ${type}`}
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function render(report){
  resultEl.hidden=false;const totalRows=report.tables.reduce((sum,t)=>sum+t.rows,0),totalColumns=report.tables.reduce((sum,t)=>sum+t.columns,0),issues=report.tables.reduce((sum,t)=>sum+t.column_analyses.reduce((s,c)=>s+c.null_count+(c.empty?1:0)+c.inconsistent_values,0)+t.duplicate_rows,0);
  resultEl.innerHTML=`<div class="results-head"><div><h2>Visão geral</h2><div class="subtle">${escapeHtml(report.filename)} · ${report.tables.length} tabela(s)</div></div><button id="export" class="secondary-button">↓ Exportar relatório</button></div>
  <div class="metric-grid"><div class="metric"><label>LINHAS</label><strong>${totalRows.toLocaleString('pt-BR')}</strong></div><div class="metric"><label>COLUNAS</label><strong>${totalColumns.toLocaleString('pt-BR')}</strong></div><div class="metric"><label>ALERTAS DE QUALIDADE</label><strong class="${issues?'quality-bad':''}">${issues.toLocaleString('pt-BR')}</strong></div></div>
  <div class="panel"><div class="table-head"><h3>Perfil das colunas</h3><select class="table-select" id="table-select">${report.tables.map((t,i)=>`<option value="${i}">${escapeHtml(t.name)}</option>`).join('')}</select></div><div id="columns-table" class="scroll"></div></div>
  <div class="panel"><h3>Prévia dos dados</h3><div id="preview-table" class="scroll preview"></div></div>
  <div class="panel"><h3>Relacionamentos sugeridos</h3><div id="relations"></div></div>
  ${report.warnings.map(w=>`<div class="warning">⚠ ${escapeHtml(w)}</div>`).join('')}`;
  const selector=resultEl.querySelector('#table-select');const update=()=>{const table=report.tables[Number(selector.value)];renderColumns(table);renderPreview(table)};selector.addEventListener('change',update);update();
  const rel=resultEl.querySelector('#relations');rel.innerHTML=report.relationships.length?report.relationships.map(r=>`<div class="relationship"><b>${escapeHtml(r.source_table)}.${escapeHtml(r.source_column)}</b> → <b>${escapeHtml(r.target_table)}.${escapeHtml(r.target_column)}</b> <span class="subtle">${r.coverage_pct}% cobertura · ${r.confidence}</span></div>`).join(''):'<div class="subtle">Nenhum relacionamento provável encontrado neste arquivo.</div>';
  resultEl.querySelector('#export').addEventListener('click',()=>{const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`${report.filename}.analysis.json`;a.click();URL.revokeObjectURL(a.href)});
  resultEl.scrollIntoView({behavior:'smooth',block:'start'});
}
function renderColumns(table){document.querySelector('#columns-table').innerHTML=`<table><thead><tr><th>COLUNA</th><th>TIPO</th><th>NULOS</th><th>DISTINTOS</th><th>REPETIDOS</th><th>INCONSISTÊNCIAS</th><th>CHAVE?</th><th>ESTATÍSTICAS / MAIS FREQUENTES</th></tr></thead><tbody>${table.column_analyses.map(c=>{const stats=Object.entries(c.statistics).map(([k,v])=>`${k}: ${v}`).join(' · ');const top=c.top_values.slice(0,4).map(v=>`${v.value} (${v.count})`).join(' · ');return `<tr><td>${escapeHtml(c.name)}</td><td><span class="pill">${escapeHtml(c.inferred_type)}</span></td><td>${c.null_count} <span class="subtle">(${c.null_pct}%)</span></td><td>${c.distinct_count}</td><td>${c.duplicate_count}</td><td>${c.inconsistent_values}</td><td>${c.key_candidate?'✓ provável':'—'}</td><td>${escapeHtml([stats,top].filter(Boolean).join(' | ')||'—')}</td></tr>`}).join('')}</tbody></table>`}
function renderPreview(table){const keys=table.preview[0]?Object.keys(table.preview[0]):[];document.querySelector('#preview-table').innerHTML=keys.length?`<table><thead><tr>${keys.map(k=>`<th>${escapeHtml(k)}</th>`).join('')}</tr></thead><tbody>${table.preview.map(row=>`<tr>${keys.map(k=>`<td title="${escapeHtml(row[k])}">${escapeHtml(row[k])??'—'}</td>`).join('')}</tr>`).join('')}</tbody></table>`:'<div class="subtle">Sem linhas para exibir.</div>'}
