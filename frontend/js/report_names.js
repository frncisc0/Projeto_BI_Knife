const usedDownloadNames = new Set();

function safeReportBase(sourceName) {
  const basename = String(sourceName || 'arquivo').split(/[\\/]/).pop() || 'arquivo';
  const dot = basename.lastIndexOf('.');
  const stem = dot > 0 ? basename.slice(0, dot) : basename;
  let safe = stem.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/[ .]+$/g, '') || 'arquivo';
  if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(safe)) safe = `_${safe}`;
  return safe;
}

function reportTimestamp(batch) {
  const analyses = (batch.results || []).map(item => item.analysis).filter(Boolean);
  const latest = analyses.map(item => item.analyzed_at).filter(Boolean)
    .sort((left, right) => new Date(left) - new Date(right)).at(-1);
  const match = String(latest || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if (match) return `${match[1]}-${match[2]}-${match[3]}_${match[4]}-${match[5]}-${match[6]}`;
  const now = new Date();
  const pad = value => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;
}

function uniqueReportName(filename) {
  if (!usedDownloadNames.has(filename)) {
    usedDownloadNames.add(filename);
    return filename;
  }
  const dot = filename.lastIndexOf('.');
  const stem = dot > 0 ? filename.slice(0, dot) : filename;
  const extension = dot > 0 ? filename.slice(dot) : '';
  let suffix = 1;
  let candidate;
  do {
    candidate = `${stem}_${String(suffix).padStart(2, '0')}${extension}`;
    suffix += 1;
  } while (usedDownloadNames.has(candidate));
  usedDownloadNames.add(candidate);
  return candidate;
}

export function reportDownloadFilename(batch, extension) {
  const results = Array.isArray(batch.results) ? batch.results : [];
  const timestamp = reportTimestamp(batch);
  const stem = results.length > 1
    ? `BI-Swiss-Knife_analise-combinada_${timestamp}`
    : `${safeReportBase(results[0]?.analysis?.filename || results[0]?.filename)}_${timestamp}_BI-Swiss-Knife`;
  return uniqueReportName(`${stem}.${extension}`);
}
