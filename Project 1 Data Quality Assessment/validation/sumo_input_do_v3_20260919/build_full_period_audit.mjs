import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(root, 'outputs', 'dqr_full_period');
const tables = JSON.parse(await fs.readFile(path.join(out, 'audit_tables.json'), 'utf8'));
const wb = Workbook.create();
const preview = path.join(out, 'previews');
await fs.mkdir(preview, {recursive: true});

const columnName = n => {
  let name = '';
  for (n++; n > 0; n = Math.floor((n - 1) / 26)) name = String.fromCharCode(65 + (n - 1) % 26) + name;
  return name;
};
const excelDate = value => {
  const parts = String(value).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!parts) return value;
  const [, year, month, day, hour, minute, second = '0'] = parts;
  return (Date.UTC(+year, +month - 1, +day, +hour, +minute, +second) - Date.UTC(1899, 11, 30)) / 86400000;
};
const dateFields = new Set(['start', 'end_exclusive']);
const integerFields = new Set([
  'minutes', 'sensor_minutes', 'raw_present', 'DQR_present', 'quality_excluded_minutes',
  'source_unassessed_minutes', 'native_missing_minutes', 'technical_invalid_minutes',
  'low_trigger_minutes', 'gate_fail_minutes', 'zero_equivalent_minutes',
  'full_evidence_minutes', 'D5_report_minutes', 'expected_5min_bins',
  'DO6_quality_excluded_bins', 'ORP_quality_excluded_bins', 'source_unassessed_bins',
  'contrast_rank', 'direct_run_rank'
]);

for (const [name, table] of Object.entries(tables)) {
  const sheet = wb.worksheets.add(name);
  const rows = table.rows.map(row => row.map((value, index) => dateFields.has(table.columns[index]) ? excelDate(value) : value));
  const last = columnName(table.columns.length - 1);
  const range = sheet.getRange(`A1:${last}${rows.length + 1}`);
  range.values = [table.columns.map(value => value.replaceAll('_', ' ')), ...rows];
  range.format.font = {name: 'Arial', size: 9};
  range.format.verticalAlignment = 'center';
  range.format.rowHeight = 22;
  range.format.columnWidth = 19;
  sheet.getRange(`A1:${last}1`).format = {
    fill: '#1F4E79', font: {name: 'Arial', size: 9, bold: true, color: '#FFFFFF'},
    wrapText: true, rowHeight: 48
  };
  table.columns.forEach((field, index) => {
    const col = columnName(index);
    const cells = sheet.getRange(`${col}2:${col}${rows.length + 1}`);
    if (dateFields.has(field)) {
      cells.setNumberFormat('yyyy-mm-dd hh:mm');
      sheet.getRange(`${col}1:${col}${rows.length + 1}`).format.columnWidth = 22;
    } else if (integerFields.has(field)) {
      cells.setNumberFormat('0');
    } else if (field.endsWith('_pct') || field.includes('_pct_')) {
      cells.setNumberFormat('0.00');
    }
  });
  if (name === 'Contract') {
    sheet.getRange(`A1:A${rows.length + 1}`).format.columnWidth = 38;
    sheet.getRange(`B1:B${rows.length + 1}`).format.columnWidth = 90;
    range.format.wrapText = true;
    range.format.rowHeight = 32;
  }
  if (['PeriodSummary', 'ActionSummary', 'ChannelSummary'].includes(name)) {
    sheet.getRange(`A1:A${rows.length + 1}`).format.columnWidth = 38;
  }
  if (name === 'ChannelSummary') {
    sheet.getRange(`B1:B${rows.length + 1}`).format.columnWidth = 14;
  }
  if (name === 'SelectedWindows') {
    sheet.getRange('A1:B3').format.columnWidth = 22;
    sheet.getRange('C1:C3').format.columnWidth = 32;
  }
  if (name === 'WindowRanking') {
    sheet.getRange(`A1:${last}${rows.length + 1}`).format.columnWidth = 18;
    sheet.getRange('A1:B61').format.columnWidth = 22;
  }
}

wb.recalculate();
for (const sheet of wb.worksheets.items) {
  const table = tables[sheet.name];
  const last = columnName(Math.min(table.columns.length, 12) - 1);
  const visibleRows = Math.min(table.rows.length + 1, 22);
  const blob = await wb.render({sheetName: sheet.name, range: `A1:${last}${visibleRows}`, scale: 1.2, format: 'png'});
  await fs.writeFile(path.join(preview, `${sheet.name}.png`), new Uint8Array(await blob.arrayBuffer()));
}
const errors = await wb.inspect({
  kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',
  options: {useRegex: true, maxResults: 30}, maxChars: 3000
});
await fs.writeFile(path.join(out, 'workbook_error_scan.json'), errors.ndjson);
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out, 'DQR_full_period_SUMO_audit.xlsx'));
console.log(`Full-period DQR audit workbook exported; ${Object.keys(tables).length} sheets rendered.`);
