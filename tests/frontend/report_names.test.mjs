import test from 'node:test';
import assert from 'node:assert/strict';
import { reportDownloadFilename } from '../../frontend/js/report_names.js';

const timestamp = '2026-10-14T22:51:29-03:00';

test('single-file exports preserve the source stem, timestamp and output extension', () => {
  const batch = { results: [{ filename: 'Risco Trabalhista - 08-2026.xlsx',
    analysis: { filename: 'Risco Trabalhista - 08-2026.xlsx', analyzed_at: timestamp } }] };
  assert.equal(reportDownloadFilename(batch, 'pdf'),
    'Risco Trabalhista - 08-2026_2026-10-14_22-51-29_BI-Swiss-Knife.pdf');
});

test('invalid Windows characters are replaced while accents are preserved', () => {
  const batch = { results: [{ filename: 'C:/dados/Risco: São Paulo?.csv',
    analysis: { analyzed_at: timestamp } }] };
  assert.equal(reportDownloadFilename(batch, 'json'),
    'Risco_ São Paulo__2026-10-14_22-51-29_BI-Swiss-Knife.json');
});

test('batch exports use the combined name and the latest analysis timestamp', () => {
  const batch = { results: [
    { filename: 'a.csv', analysis: { analyzed_at: '2026-10-14T21:00:00-03:00' } },
    { filename: 'b.xlsx', analysis: { analyzed_at: timestamp } },
  ] };
  assert.equal(reportDownloadFilename(batch, 'html'),
    'BI-Swiss-Knife_analise-combinada_2026-10-14_22-51-29.html');
});

test('repeated downloads get a safe suffix without changing the timestamp', () => {
  const batch = { results: [{ filename: 'repetido.csv', analysis: { analyzed_at: timestamp } }] };
  assert.equal(reportDownloadFilename(batch, 'csv'),
    'repetido_2026-10-14_22-51-29_BI-Swiss-Knife.csv');
  assert.equal(reportDownloadFilename(batch, 'csv'),
    'repetido_2026-10-14_22-51-29_BI-Swiss-Knife_01.csv');
});
