import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';

const here = path.dirname(fileURLToPath(import.meta.url));
const t0 = process.argv.includes('--t0');
const source = path.join(here, 'outputs', 'source_data', ...(t0 ? ['T0'] : []));
const tables = JSON.parse(await fs.readFile(path.join(source, 'workbook_tables.json'), 'utf8'));
const wb = Workbook.create();
const isClock = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$/.test(value);
for (const table of tables) {
  const sheet = wb.worksheets.add(table.name);
  sheet.showGridLines = false;
  // Serial dates avoid a runtime Date-export local-midnight conversion defect.
  // All source times retain their literal Asia/Shanghai clock, without shifting.
  const values = table.rows.map(row => row.map(value => isClock(value)
    ? 25569 + Date.parse(value.replace(' ', 'T') + (value.length === 10 ? 'T00:00:00Z' : 'Z')) / 86400000 : value));
  sheet.getRangeByIndexes(0, 0, values.length + 1, table.columns.length).values = [table.columns, ...values];
  const used = sheet.getUsedRange();
  used.format.font = {name: 'Arial', size: 10, color: '#202326'};
  used.format.rowHeight = 24;
  used.format.columnWidth = 23;
  const header = sheet.getRangeByIndexes(0, 0, 1, table.columns.length);
  header.format.fill = '#E4E8ED';
  header.format.font = {name: 'Arial', size: 10, bold: true, color: '#202326'};
  header.format.wrapText = true;
  header.format.rowHeight = t0 ? 80 : 62;
  header.format.borders = {bottom: {style: 'thin', color: '#929BA5'}};
  for (let j = 0; j < table.columns.length; j++) {
    const column = sheet.getRangeByIndexes(1, j, values.length, 1);
    const original = values.map(row => row[j]).filter(value => value !== null);
    const sourceColumn = table.rows.map(row => row[j]).filter(value => value !== null);
    if (sourceColumn.length && sourceColumn.every(isClock)) column.setNumberFormat('yyyy-mm-dd hh:mm');
    else if (original.length && original.every(value => typeof value === 'number')) {
      const nonzero = original.filter(value => value !== 0);
      column.setNumberFormat(nonzero.length && nonzero.every(value => Math.abs(value) < 1e-8)
        ? '0.00E+00' : original.every(Number.isInteger) ? '#,##0' : t0 ? '0.0000' : '0.0000000000');
    } else {
      column.format.wrapText = true;
      if (original.some(value => typeof value === 'string' && value.length > 32)) column.format.columnWidth = 48;
    }
  }
  if (values.length > 15) sheet.freezePanes.freezeRows(1);
  console.log((await wb.inspect({kind: 'region', sheetId: table.name, range: 'A1:F4', maxChars: 900})).ndjson);
}
const file = await SpreadsheetFile.exportXlsx(wb);
await file.save(path.join(source, t0 ? 'Temporal_holdout_T0_source.xlsx' : 'Temporal_holdout_stage_B_source.xlsx'));
await fs.mkdir(path.join(here, '.local_qa'), {recursive: true});
for (const table of (t0 ? tables : [{name: 'D4 historical impact'}])) {
  const preview = await wb.render({sheetName: table.name, range: 'A1:G8', scale: 1.3, format: 'png'});
  await fs.writeFile(path.join(here, '.local_qa', `workbook_${table.name.replaceAll(' ', '_')}.png`),
    new Uint8Array(await preview.arrayBuffer()));
}
console.log('Source workbook and preview exported. Verify all cells independently with verify_stage_b.py.');
process.exit(0);
