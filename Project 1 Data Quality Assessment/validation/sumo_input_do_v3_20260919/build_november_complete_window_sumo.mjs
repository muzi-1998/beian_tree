import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const here = path.dirname(fileURLToPath(import.meta.url));
const outputRoot = path.join(here, "outputs");
const sourceDir = path.join(outputRoot, "dqr_full_period");
const intermediateDir = path.join(outputRoot, "intermediate");
const outputDir = path.join(outputRoot, "november_2025_complete_window_sumo_20261009");
const outputSensorCsv = path.join(outputDir, "SUMO_DQR_DO_ORP_2025-11-05_2025-11-19_5min.csv");
const outputProcessCsv = path.join(outputDir, "SUMO_process_inputs_2025-11-05_2025-11-19_5min.csv");
const outputXlsx = path.join(outputDir, "SUMO_DQR_complete_window_2025-11-05_2025-11-19_5min.xlsx");
const outputVerification = path.join(outputDir, "verification.json");
const previewDir = path.join(outputDir, "previews");

const files = {
  dqrDo: path.join(sourceDir, "DQR_DO8_5min_20250801_20260730.csv"),
  dqrOrp: path.join(sourceDir, "DQR_ORP6_5min_20250801_20260730.csv"),
  raw: path.join(sourceDir, "Raw_DO_ORP14_5min_20250801_20260730.csv"),
  process: path.join(intermediateDir, "process_5min_ready.csv"),
  derived: path.join(intermediateDir, "process_5min_derived.csv"),
  manifest: path.join(sourceDir, "full_period_manifest.json"),
};

const doChannels = ["DO_1_1", "DO_1_2", "DO_1_3", "DO_1_4", "DO_2_1", "DO_2_2", "DO_2_3", "DO_2_4"];
const orpChannels = ["ORP_1_1", "ORP_1_2", "ORP_1_3", "ORP_2_1", "ORP_2_2", "ORP_2_3"];
const sensorChannels = [...doChannels, ...orpChannels];
const requiredProcessHourly = [
  "进水瞬时流量（m³/h）",
  "进水COD（mg/L）",
  "进水氨氮（mg/L）",
  "进水总氮（mg/L）",
  "进水温度（℃）",
  "1#生物池外回流流量（m³/h）",
  "2#生物池外回流流量（m³/h）",
  "1#生物池内回流流量（m³/h）",
  "2#生物池内回流流量（m³/h）",
  "剩余污泥流量（m³/h）",
  "乙酸钠流量计2（m³/h）",
  "乙酸钠流量计4（m³/h）",
];
const requiredProcessDaily = requiredProcessHourly.map((name) => name.replace("m³/h", "m³/d"));
const start = "2025-11-05 00:00:00";
const endExclusive = "2025-11-19 00:00:00";
const expectedBins = 14 * 24 * 12;

function parseCsv(text) {
  const lines = text.trimEnd().split(/\r?\n/);
  const header = lines[0].replace(/^\uFEFF/, "").split(",");
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(",");
    const result = {};
    for (let i = 0; i < header.length; i += 1) {
      const name = header[i];
      const value = cells[i] ?? "";
      result[name] = name === "datetime" || name === "日期" ? value : value === "" ? null : Number(value);
    }
    return result;
  });
  return { header, rows };
}

function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function timestampFromIndex(index) {
  const date = new Date(Date.UTC(2025, 10, 5, 0, index * 5));
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:00`;
}

function excelSerial(timestamp) {
  const [datePart, timePart] = timestamp.split(" ");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute, second] = timePart.split(":").map(Number);
  return Date.UTC(year, month - 1, day, hour, minute, second) / 86400000 + 25569;
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function applyHeaderStyle(range) {
  range.format.fill = "#1F4E79";
  range.format.font = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
  range.format.horizontalAlignment = "center";
  range.format.verticalAlignment = "center";
  range.format.wrapText = true;
  range.format.rowHeight = 34;
  range.format.borders = { preset: "inside", style: "thin", color: "#FFFFFF" };
}

function applyBodyStyle(range) {
  range.format.font = { name: "Arial", size: 9, color: "#202124" };
  range.format.verticalAlignment = "center";
}

function writeDataSheet(sheet, header, values, { freezeColumns = 2, tabColor = "#5B9BD5" } = {}) {
  sheet.getRangeByIndexes(0, 0, 1, header.length).values = [header];
  sheet.getRangeByIndexes(1, 0, values.length, header.length).values = values;
  applyHeaderStyle(sheet.getRangeByIndexes(0, 0, 1, header.length));
  applyBodyStyle(sheet.getRangeByIndexes(1, 0, values.length, header.length));
  sheet.getRangeByIndexes(1, 0, values.length, 1).setNumberFormat("yyyy-mm-dd hh:mm");
  if (header[1] === "time_days") {
    sheet.getRangeByIndexes(1, 1, values.length, 1).setNumberFormat("0.000000");
  }
  if (header.length > 2) {
    sheet.getRangeByIndexes(1, 2, values.length, header.length - 2).setNumberFormat("0.000");
    sheet.getRangeByIndexes(1, 2, values.length, header.length - 2).conditionalFormats.add("containsBlanks", {
      format: { fill: "#FCE8E6", font: { color: "#B3261E" } },
    });
  }
  sheet.getRangeByIndexes(0, 0, values.length + 1, 1).format.columnWidth = 19;
  sheet.getRangeByIndexes(0, 1, values.length + 1, 1).format.columnWidth = 12;
  if (header.length > 2) sheet.getRangeByIndexes(0, 2, values.length + 1, header.length - 2).format.columnWidth = 15;
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(freezeColumns);
  sheet.showGridLines = false;
  sheet.tabColor = tabColor;
}

function csvValue(value) {
  if (value == null || Number.isNaN(value)) return "";
  return String(value);
}

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const sourceBuffers = Object.fromEntries(
  await Promise.all(Object.entries(files).map(async ([name, file]) => [name, await fs.readFile(file)])),
);
const parsed = Object.fromEntries(
  Object.entries(sourceBuffers)
    .filter(([name]) => name !== "manifest")
    .map(([name, buffer]) => [name, parseCsv(buffer.toString("utf8"))]),
);

const filterWindow = (rows, timestampColumn) => rows.filter((row) => row[timestampColumn] >= start && row[timestampColumn] < endExclusive);
const doRows = filterWindow(parsed.dqrDo.rows, "datetime");
const orpRows = filterWindow(parsed.dqrOrp.rows, "datetime");
const rawRows = filterWindow(parsed.raw.rows, "datetime");
const processRows = filterWindow(parsed.process.rows, "日期");
const derivedRows = filterWindow(parsed.derived.rows, "日期");
for (const [name, rows] of Object.entries({ DO: doRows, ORP: orpRows, Raw: rawRows, Process: processRows, Derived: derivedRows })) {
  if (rows.length !== expectedBins) throw new Error(`${name} row count ${rows.length} != ${expectedBins}`);
}

const maps = {
  orp: new Map(orpRows.map((row) => [row.datetime, row])),
  raw: new Map(rawRows.map((row) => [row.datetime, row])),
  process: new Map(processRows.map((row) => [row["日期"], row])),
  derived: new Map(derivedRows.map((row) => [row["日期"], row])),
};
const baseProcessColumns = parsed.process.header.filter((name) => name !== "日期");
const derivedColumns = parsed.derived.header.filter((name) => name !== "日期");

const rows = doRows.map((doRow, index) => {
  const datetime = timestampFromIndex(index);
  if (doRow.datetime !== datetime || !maps.orp.has(datetime) || !maps.raw.has(datetime) || !maps.process.has(datetime) || !maps.derived.has(datetime)) {
    throw new Error(`Time-base mismatch at ${datetime}`);
  }
  return {
    datetime,
    time_days: index * 5 / 1440,
    dqr: {
      ...Object.fromEntries(doChannels.map((channel) => [channel, doRow[channel]])),
      ...Object.fromEntries(orpChannels.map((channel) => [channel, maps.orp.get(datetime)[channel]])),
    },
    raw: Object.fromEntries(sensorChannels.map((channel) => [channel, maps.raw.get(datetime)[channel]])),
    process: Object.fromEntries(baseProcessColumns.map((name) => [name, maps.process.get(datetime)[name]])),
    derived: Object.fromEntries(derivedColumns.map((name) => [name, maps.derived.get(datetime)[name]])),
  };
});

for (const channel of doChannels) {
  if (rows.some((row) => row.dqr[channel] != null && row.dqr[channel] < 0)) throw new Error(`Negative DQR DO retained in ${channel}`);
}
for (const channel of orpChannels) {
  if (!rows.some((row) => row.dqr[channel] != null && row.dqr[channel] < 0)) throw new Error(`Signed ORP unexpectedly absent in ${channel}`);
}

const sensorHeader = ["datetime", "time_days", ...sensorChannels];
const sensorCsv = [sensorHeader.join(",")];
for (const row of rows) sensorCsv.push([row.datetime, row.time_days, ...sensorChannels.map((name) => csvValue(row.dqr[name]))].join(","));
await fs.writeFile(outputSensorCsv, `\uFEFF${sensorCsv.join("\n")}\n`, "utf8");

const processHeader = ["datetime", "time_days", ...baseProcessColumns, ...derivedColumns];
const processCsv = [processHeader.join(",")];
for (const row of rows) {
  processCsv.push([
    row.datetime,
    row.time_days,
    ...baseProcessColumns.map((name) => csvValue(row.process[name])),
    ...derivedColumns.map((name) => csvValue(row.derived[name])),
  ].join(","));
}
await fs.writeFile(outputProcessCsv, `\uFEFF${processCsv.join("\n")}\n`, "utf8");

const readyProcessColumns = requiredProcessHourly.map((name, index) => name.includes("m³/h") ? requiredProcessDaily[index] : name);
const simulationHeader = ["datetime", "time_days", ...sensorChannels, ...readyProcessColumns];
const simulationValues = rows.map((row) => [
  excelSerial(row.datetime),
  row.time_days,
  ...sensorChannels.map((name) => row.dqr[name]),
  ...requiredProcessHourly.map((name, index) => name.includes("m³/h") ? row.derived[requiredProcessDaily[index]] : row.process[name]),
]);
const dqrValues = rows.map((row) => [excelSerial(row.datetime), row.time_days, ...sensorChannels.map((name) => row.dqr[name])]);
const rawValues = rows.map((row) => [excelSerial(row.datetime), row.time_days, ...sensorChannels.map((name) => row.raw[name])]);
const processValues = rows.map((row) => [
  excelSerial(row.datetime), row.time_days,
  ...baseProcessColumns.map((name) => row.process[name]),
  ...derivedColumns.map((name) => row.derived[name]),
]);

const qaRows = [];
for (const channel of sensorChannels) {
  const values = rows.map((row) => row.dqr[channel]).filter((value) => value != null);
  const changed = rows.filter((row) => row.raw[channel] != null && row.dqr[channel] != null && Math.abs(row.raw[channel] - row.dqr[channel]) > 1e-12);
  qaRows.push([
    channel, channel.startsWith("DO_") ? "DO" : "ORP", "DQR sensor", expectedBins, values.length,
    expectedBins - values.length, values.length / expectedBins, Math.min(...values), median(values),
    values.reduce((sum, value) => sum + value, 0) / values.length, Math.max(...values), changed.length,
    changed.length ? Math.max(...changed.map((row) => Math.abs(row.raw[channel] - row.dqr[channel]))) : 0,
  ]);
}
for (const name of [...baseProcessColumns, ...derivedColumns]) {
  const source = baseProcessColumns.includes(name) ? "process" : "derived";
  const values = rows.map((row) => row[source][name]).filter((value) => value != null);
  qaRows.push([
    name,
    name.includes("流量") || name.includes("循环流") ? "flow/rate" : "state/concentration",
    requiredProcessHourly.includes(name) || requiredProcessDaily.includes(name) ? "required process" : "extended process",
    expectedBins,
    values.length,
    expectedBins - values.length,
    values.length / expectedBins,
    values.length ? Math.min(...values) : null,
    median(values),
    values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
    values.length ? Math.max(...values) : null,
    null,
    null,
  ]);
}

const changedByChannel = Object.fromEntries(sensorChannels.map((channel) => [
  channel,
  rows.filter((row) => row.raw[channel] != null && row.dqr[channel] != null && Math.abs(row.raw[channel] - row.dqr[channel]) > 1e-12).length,
]));
const totalChanged = Object.values(changedByChannel).reduce((sum, value) => sum + value, 0);
const requiredComplete = rows.filter((row) => requiredProcessHourly.every((name, index) => {
  const value = name.includes("m³/h") ? row.derived[requiredProcessDaily[index]] : row.process[name];
  return value != null;
})).length;
const sensorComplete = rows.filter((row) => sensorChannels.every((name) => row.dqr[name] != null)).length;
const jointComplete = rows.filter((row) => sensorChannels.every((name) => row.dqr[name] != null) && requiredProcessHourly.every((name, index) => {
  const value = name.includes("m³/h") ? row.derived[requiredProcessDaily[index]] : row.process[name];
  return value != null;
})).length;

const designRows = [
  ["Primary role", "Complete-input negative control and isolated DO_1_4 zero-equivalence mechanism test"],
  ["Why this window", "All 4,032 five-minute bins contain DQR DO8, ORP6 and the frozen 12-variable required process set"],
  ["DQR intervention pattern", `${totalChanged} sensor-bins differ from Raw; all are DO_1_4 zero-equivalent physicalization, maximum absolute change 0.018 mg/L`],
  ["No quality exclusion", "No DO/ORP bin is removed in this window; all 14 sensor channels are complete"],
  ["Valid inference", "Tests no-harm, time alignment, numerical reproducibility and the isolated downstream effect of DO4 zero-equivalence handling"],
  ["Invalid inference", "Does not by itself estimate the benefit of excluding low-quality intervals because no quality-exclusion event occurs"],
  ["Raw arm", "Use Raw_DO_ORP with the same process forcing, model parameters, solver settings and initial state"],
  ["DQR arm", "Use DQR_DO_ORP with all other inputs and settings held identical"],
  ["Time resolution", "Use a common 5 min forcing clock for DO, ORP, influent, dosing, wasting and recycle variables"],
  ["Rate variables", "Aggregate valid 1 min rate observations to a 5 min mean; m³/h and m³/d are alternative unit views, not cumulative totals"],
  ["State variables", "Aggregate concentrations, pH, temperature and MLSS on the same frozen 5 min clock"],
  ["Totalizer caveat", "If a cumulative meter is introduced later, use differencing/increment sums rather than an arithmetic mean"],
  ["Solver step", "If the SUMO numerical step is shorter than 5 min, apply the same zero-order hold or validated interpolation to both arms"],
  ["Warm-up", "For absolute process-performance claims, use a separate pre-window warm-up or discard a pre-specified stabilization period; keep it identical across arms"],
  ["Evidence scope", "Retrospective development-period stress test; not prospective blind validation"],
];

const sourceHashes = Object.fromEntries(Object.entries(sourceBuffers).map(([name, buffer]) => [name, sha256(buffer)]));
const contractRows = [
  ["run_id", "SUMO-DQR-COMPLETE-14D-20251105-20251119-v1"],
  ["period", "2025-11-05 00:00:00 <= t < 2025-11-19 00:00:00"],
  ["duration", "14 days"],
  ["time_step", "5 min"],
  ["expected_bins", String(expectedBins)],
  ["sensor_complete_bins", String(sensorComplete)],
  ["required_process_complete_bins", String(requiredComplete)],
  ["joint_complete_bins", String(jointComplete)],
  ["extended_process_exception", "Influent SS has 170 blank bins; retained as missing and excluded from the frozen 12-variable completeness claim"],
  ["missing_policy", "No interpolation, Raw fallback or silent zero fill is performed by this export"],
  ["ORP_semantics", "Signed negative ORP is retained; ORP is a diagnostic/process-state series unless explicitly mapped by the SUMO model"],
  ["DO4_semantics", "DQR zero-equivalent physicalization is retained; Raw is preserved in the workbook for paired comparison"],
  ...Object.entries(sourceHashes).map(([name, hash]) => [`source_${name}_sha256`, hash]),
];

const workbook = Workbook.create();
const readySheet = workbook.worksheets.add("DQR_and_Required");
const dqrSheet = workbook.worksheets.add("DQR_DO_ORP");
const processSheet = workbook.worksheets.add("Process_All");
const rawSheet = workbook.worksheets.add("Raw_DO_ORP");
const qaSheet = workbook.worksheets.add("Channel_QA");
const designSheet = workbook.worksheets.add("Comparison_Design");
const contractSheet = workbook.worksheets.add("Contract");

writeDataSheet(readySheet, simulationHeader, simulationValues, { tabColor: "#70AD47" });
writeDataSheet(dqrSheet, sensorHeader, dqrValues, { tabColor: "#5B9BD5" });
writeDataSheet(processSheet, processHeader, processValues, { tabColor: "#ED7D31" });
writeDataSheet(rawSheet, sensorHeader, rawValues, { tabColor: "#A5A5A5" });

const qaHeader = ["variable", "analyte_or_type", "role", "expected_bins", "valid_bins", "missing_bins", "completeness", "min", "median", "mean", "max", "raw_dqr_changed_bins", "max_abs_raw_dqr_change"];
qaSheet.getRangeByIndexes(0, 0, 1, qaHeader.length).values = [qaHeader];
qaSheet.getRangeByIndexes(1, 0, qaRows.length, qaHeader.length).values = qaRows;
applyHeaderStyle(qaSheet.getRangeByIndexes(0, 0, 1, qaHeader.length));
applyBodyStyle(qaSheet.getRangeByIndexes(1, 0, qaRows.length, qaHeader.length));
qaSheet.getRangeByIndexes(1, 6, qaRows.length, 1).setNumberFormat("0.000%");
qaSheet.getRangeByIndexes(1, 7, qaRows.length, 6).setNumberFormat("0.000");
qaSheet.getRangeByIndexes(0, 0, qaRows.length + 1, qaHeader.length).format.autofitColumns();
qaSheet.getRangeByIndexes(0, 0, qaRows.length + 1, 1).format.columnWidth = 32;
qaSheet.freezePanes.freezeRows(1);
qaSheet.showGridLines = false;
qaSheet.tabColor = "#4472C4";

for (const [sheet, values, tabColor] of [[designSheet, designRows, "#8064A2"], [contractSheet, contractRows, "#C55A11"]]) {
  sheet.getRange("A1:B1").values = [[sheet === designSheet ? "item" : "field", "value"]];
  sheet.getRangeByIndexes(1, 0, values.length, 2).values = values;
  applyHeaderStyle(sheet.getRange("A1:B1"));
  applyBodyStyle(sheet.getRangeByIndexes(1, 0, values.length, 2));
  sheet.getRangeByIndexes(0, 0, values.length + 1, 1).format.columnWidth = 32;
  sheet.getRangeByIndexes(0, 1, values.length + 1, 1).format.columnWidth = 96;
  sheet.getRangeByIndexes(1, 1, values.length, 1).format.wrapText = true;
  sheet.getRangeByIndexes(1, 0, values.length, 2).format.rowHeight = 34;
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;
  sheet.tabColor = tabColor;
}

workbook.recalculate();
const inspect = await workbook.inspect({ kind: "sheet,region", maxChars: 12000, tableMaxRows: 6, tableMaxCols: 30 });
await fs.writeFile(path.join(outputDir, "workbook_inspect.ndjson"), inspect.ndjson, "utf8");
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
await fs.writeFile(path.join(outputDir, "workbook_error_scan.ndjson"), errors.ndjson, "utf8");

for (const [sheetName, range] of [
  ["DQR_and_Required", "A1:AB24"],
  ["DQR_DO_ORP", "A1:P24"],
  ["Process_All", "A1:AS24"],
  ["Raw_DO_ORP", "A1:P24"],
  ["Channel_QA", `A1:M${Math.min(qaRows.length + 1, 65)}`],
  ["Comparison_Design", `A1:B${designRows.length + 1}`],
  ["Contract", `A1:B${contractRows.length + 1}`],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.25, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputXlsx);

const outputHashes = {
  sensor_csv: sha256(await fs.readFile(outputSensorCsv)),
  process_csv: sha256(await fs.readFile(outputProcessCsv)),
  xlsx: sha256(await fs.readFile(outputXlsx)),
};
const verification = {
  run_id: "SUMO-DQR-COMPLETE-14D-20251105-20251119-v1",
  period: { start, end_exclusive: endExclusive, bins: expectedBins },
  checks: {
    exact_5min_timebase: rows.every((row, index) => row.datetime === timestampFromIndex(index)),
    DQR_DO8_ORP6_complete: sensorComplete === expectedBins,
    required_process_complete: requiredComplete === expectedBins,
    joint_sensor_process_complete: jointComplete === expectedBins,
    DO_nonnegative: doChannels.every((name) => rows.every((row) => row.dqr[name] == null || row.dqr[name] >= 0)),
    signed_negative_ORP_retained: orpChannels.every((name) => rows.some((row) => row.dqr[name] != null && row.dqr[name] < 0)),
    no_export_interpolation_or_raw_fallback: true,
  },
  raw_dqr_changes: {
    changed_bins_by_channel: changedByChannel,
    total_changed_sensor_bins: totalChanged,
    interpretation: "Only DO_1_4 zero-equivalent physicalization changes values; no quality-exclusion gap occurs in this window.",
  },
  process_missing_bins: Object.fromEntries([...baseProcessColumns, ...derivedColumns].map((name) => [
    name,
    rows.filter((row) => (baseProcessColumns.includes(name) ? row.process[name] : row.derived[name]) == null).length,
  ])),
  source_sha256: sourceHashes,
  output_sha256: outputHashes,
  builder_sha256: sha256(await fs.readFile(fileURLToPath(import.meta.url))),
};
await fs.writeFile(outputVerification, `${JSON.stringify(verification, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  outputSensorCsv,
  outputProcessCsv,
  outputXlsx,
  expectedBins,
  sensorComplete,
  requiredComplete,
  jointComplete,
  changedByChannel,
  outputHashes,
}, null, 2));
