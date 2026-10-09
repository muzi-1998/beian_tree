import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(root, 'outputs', 'dqr_forcing');
const tables = JSON.parse(await fs.readFile(path.join(out, 'audit_tables.json'), 'utf8'));
const manifest = JSON.parse(await fs.readFile(path.join(out, 'DQR_forcing_manifest.json'), 'utf8'));
tables.Contract.rows.push(...Object.entries(manifest.selected_pilot).map(([key,value])=>[
  `Selected pilot: ${key.replaceAll('_',' ')}`, typeof value==='object' ? JSON.stringify(value) : String(value)
]));
const wb = Workbook.create();
const preview = path.join(out, 'previews');
await fs.mkdir(preview, {recursive:true});
const columnName = n => { let name=''; for(n++;n>0;n=Math.floor((n-1)/26)) name=String.fromCharCode(65+(n-1)%26)+name; return name; };
// Excel serials represent local wall-clock values, not timezone-bearing instants.
const excelDate = value => {
  const parts = value.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!parts) throw new Error(`Invalid source timestamp: ${value}`);
  const [,year,month,day,hour,minute,second='0'] = parts;
  return (Date.UTC(+year,+month-1,+day,+hour,+minute,+second)-Date.UTC(1899,11,30))/86400000;
};
const headings = {
  sensor_id:'Sensor', minutes:'Total minutes', full_evidence_minutes:'Full evidence\n(min)',
  evidence_limited_pct:'Evidence limited\n(%)', low_trigger_minutes:'Low-Q trigger\n(min)',
  gate_fail_minutes:'Gate failure\n(min)', repaired_minutes:'Repaired\n(min)',
  unrecoverable_minutes:'Unrecoverable\n(min)', zero_equivalent_minutes:'Zero equivalent\n(min)',
  full_evidence_pct:'Full evidence\n(%)', start:'Start (local time)', end_exclusive:'End, exclusive\n(local time)',
  warmup_days:'Warm-up\n(days)', post_warmup_days:'After warm-up\n(days)',
  supports_28d_plus_warmup:'28 d evaluation +\n14 d warm-up?',
  missing_bins_108d:'Missing 5 min bins\n(108 d)', missing_pct_108d:'Missing\n(108 d, %)'
};
const scopeLabels = {
  six_aerobic_DO:'Six aerobic DO', eight_DO_common_DO4:'Eight DO (shared DO4)',
  eight_DO_plus_required_process_nonmissing_units_pending:'Eight DO + 12 process inputs (units pending)'
};
for (const [name, table] of Object.entries(tables)) {
  const sh = wb.worksheets.add(name);
  const rows = table.rows.map(row=>row.map((v,j)=> {
    const field=table.columns[j];
    if (['start','end_exclusive'].includes(field) && v) return excelDate(v);
    if (field==='scope') return scopeLabels[v] ?? v;
    return v;
  }));
  const last = columnName(table.columns.length-1);
  const headers = table.columns.map(c=>headings[c] ?? c.replaceAll('_',' '));
  sh.getRange(`A1:${last}${rows.length+1}`).values = [headers,...rows];
  const all = sh.getRange(`A1:${last}${rows.length+1}`);
  all.format.font={name:'Arial',size:10};
  all.format.columnWidth=19;
  all.format.rowHeight=22;
  all.format.verticalAlignment='center';
  sh.getRange(`A1:${last}1`).format={fill:'#1F4E79',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:54};
  sh.getRange(`A2:${last}${rows.length+1}`).setNumberFormat('0.00');
  table.columns.forEach((c,j)=>{
    const col=columnName(j);
    if (['start','end_exclusive'].includes(c)) {
      sh.getRange(`${col}2:${col}${rows.length+1}`).setNumberFormat('yyyy-mm-dd hh:mm');
      sh.getRange(`${col}1:${col}${rows.length+1}`).format.columnWidth=23;
    } else if(c.endsWith('minutes') || c==='minutes' || c==='missing_bins_108d') {
      sh.getRange(`${col}2:${col}${rows.length+1}`).setNumberFormat('0');
    }
  });
  if(name==='Windows') {sh.getRange(`A1:A${rows.length+1}`).format.columnWidth=58; all.format.wrapText=true; all.format.rowHeight=36;}
  if(name==='Contract') {sh.getRange(`A1:A${rows.length+1}`).format.columnWidth=49;sh.getRange(`B1:B${rows.length+1}`).format.columnWidth=95;all.format.wrapText=true;all.format.rowHeight=32;}
  if(name==='ProcessCoverage') {sh.getRange(`A1:A${rows.length+1}`).format.columnWidth=46;}
  sh.getRange(`A1:${last}1`).format.rowHeight=54;
}
wb.recalculate();
for (const sh of wb.worksheets.items) {
  const last=columnName(Math.min(tables[sh.name].columns.length,10)-1);
  const range=`A1:${last}${Math.min(tables[sh.name].rows.length+1,17)}`;
  const blob=await wb.render({sheetName:sh.name,range,scale:1.3,format:'png'});
  await fs.writeFile(path.join(preview,`${sh.name}.png`),new Uint8Array(await blob.arrayBuffer()));
}
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:30},maxChars:3000});
await fs.writeFile(path.join(out,'workbook_error_scan.json'),errors.ndjson);
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,'DQR_DO_ORP_export_audit.xlsx'));
console.log(`DQR audit workbook exported; ${Object.keys(tables).length} sheets rendered.`);
