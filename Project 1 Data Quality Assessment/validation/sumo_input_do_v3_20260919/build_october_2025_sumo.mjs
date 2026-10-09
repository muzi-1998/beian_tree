import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const here = path.dirname(fileURLToPath(import.meta.url));
const sourceDir = path.join(here, "outputs", "dqr_full_period");
const outputDir = path.join(here, "outputs", "october_2025_dqr_sumo_20261009");
const outputCsv = path.join(outputDir, "SUMO_DQR_DO_ORP_2025-10_5min.csv");
const outputXlsx = path.join(outputDir, "SUMO_DQR_DO_ORP_2025-10_5min.xlsx");
const outputVerification = path.join(outputDir, "verification.json");
const previewDir = path.join(outputDir, "previews");

const files = {
  dqrDo: path.join(sourceDir, "DQR_DO8_5min_20250801_20260730.csv"),
  dqrOrp: path.join(sourceDir, "DQR_ORP6_5min_20250801_20260730.csv"),
  raw: path.join(sourceDir, "Raw_DO_ORP14_5min_20250801_20260730.csv"),
  manifest: path.join(sourceDir, "full_period_manifest.json"),
};

const doChannels = ["DO_1_1", "DO_1_2", "DO_1_3", "DO_1_4", "DO_2_1", "DO_2_2", "DO_2_3", "DO_2_4"];
const orpChannels = ["ORP_1_1", "ORP_1_2", "ORP_1_3", "ORP_2_1", "ORP_2_2", "ORP_2_3"];
const channels = [...doChannels, ...orpChannels];
const start = "2025-10-01 00:00:00";
const endExclusive = "2025-11-01 00:00:00";
const expectedBins = 31 * 24 * 12;

function parseCsv(text) {
  const lines = text.trimEnd().split(/\r?\n/);
  const header = lines[0].replace(/^\uFEFF/, "").split(",");
  const index = Object.fromEntries(header.map((name, i) => [name, i]));
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(",");
    const result = {};
    for (const name of header) {
      const value = cells[index[name]];
      result[name] = name === "datetime" ? value : value === "" ? null : Number(value);
    }
    return result;
  });
  return { header, rows };
}

function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function timestampFromIndex(index) {
  const date = new Date(Date.UTC(2025, 9, 1, 0, index * 5));
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

function longestMissingRun(rows, channel) {
  let longest = 0;
  let current = 0;
  for (const row of rows) {
    if (row[channel] == null) {
      current += 1;
      longest = Math.max(longest, current);
    } else {
      current = 0;
    }
  }
  return longest;
}

function completeRuns(rows, scope, minimumBins = 12) {
  const complete = rows.map((row) => scope.every((channel) => row[channel] != null));
  const runs = [];
  let runStart = null;
  for (let i = 0; i <= complete.length; i += 1) {
    if (i < complete.length && complete[i] && runStart == null) runStart = i;
    if ((i === complete.length || !complete[i]) && runStart != null) {
      const bins = i - runStart;
      if (bins >= minimumBins) {
        runs.push({
          start: rows[runStart].datetime,
          endExclusive: i < rows.length ? rows[i].datetime : endExclusive,
          bins,
          hours: bins * 5 / 60,
        });
      }
      runStart = null;
    }
  }
  return runs;
}

function applyHeaderStyle(range) {
  range.format.fill = "#1F4E79";
  range.format.font = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
  range.format.horizontalAlignment = "center";
  range.format.verticalAlignment = "center";
  range.format.rowHeight = 28;
  range.format.borders = { preset: "inside", style: "thin", color: "#FFFFFF" };
}

function applyBodyStyle(range) {
  range.format.font = { name: "Arial", size: 9, color: "#202124" };
  range.format.verticalAlignment = "center";
}

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const sourceBuffers = Object.fromEntries(
  await Promise.all(Object.entries(files).map(async ([name, file]) => [name, await fs.readFile(file)])),
);
const dqrDo = parseCsv(sourceBuffers.dqrDo.toString("utf8"));
const dqrOrp = parseCsv(sourceBuffers.dqrOrp.toString("utf8"));
const raw = parseCsv(sourceBuffers.raw.toString("utf8"));

const filterMonth = (rows) => rows.filter((row) => row.datetime >= start && row.datetime < endExclusive);
const doRows = filterMonth(dqrDo.rows);
const orpRows = filterMonth(dqrOrp.rows);
const rawRows = filterMonth(raw.rows);
if (doRows.length !== expectedBins || orpRows.length !== expectedBins || rawRows.length !== expectedBins) {
  throw new Error(`Unexpected October row count: DO=${doRows.length}, ORP=${orpRows.length}, Raw=${rawRows.length}`);
}

const orpMap = new Map(orpRows.map((row) => [row.datetime, row]));
const rawMap = new Map(rawRows.map((row) => [row.datetime, row]));
const combined = doRows.map((doRow, index) => {
  const expected = timestampFromIndex(index);
  if (doRow.datetime !== expected || !orpMap.has(expected) || !rawMap.has(expected)) {
    throw new Error(`Time-base mismatch at row ${index + 1}: expected ${expected}`);
  }
  const orpRow = orpMap.get(expected);
  return {
    datetime: expected,
    time_days: index * 5 / 1440,
    ...Object.fromEntries(doChannels.map((channel) => [channel, doRow[channel]])),
    ...Object.fromEntries(orpChannels.map((channel) => [channel, orpRow[channel]])),
  };
});

for (const channel of doChannels) {
  if (combined.some((row) => row[channel] != null && row[channel] < 0)) {
    throw new Error(`Negative DQR DO retained in ${channel}`);
  }
}
for (const channel of orpChannels) {
  if (!combined.some((row) => row[channel] != null && row[channel] < 0)) {
    throw new Error(`Expected signed negative ORP not found in ${channel}`);
  }
}

const csvHeader = ["datetime", "time_days", ...channels];
const csvLines = [csvHeader.join(",")];
for (const row of combined) {
  const elapsed = row.time_days === 0 ? "0" : row.time_days.toFixed(12).replace(/0+$/, "").replace(/\.$/, "");
  csvLines.push([row.datetime, elapsed, ...channels.map((channel) => row[channel] == null ? "" : String(row[channel]))].join(","));
}
await fs.writeFile(outputCsv, `${csvLines.join("\n")}\n`, "utf8");

const qaRows = channels.map((channel) => {
  const values = combined.map((row) => row[channel]).filter((value) => value != null);
  let rawValid = 0;
  let sourceMissing = 0;
  let qualityExcluded = 0;
  let numericChanged = 0;
  for (const row of combined) {
    const rawValue = rawMap.get(row.datetime)[channel];
    const dqrValue = row[channel];
    if (rawValue == null) sourceMissing += 1;
    else rawValid += 1;
    if (rawValue != null && dqrValue == null) qualityExcluded += 1;
    if (rawValue != null && dqrValue != null && Math.abs(rawValue - dqrValue) > 1e-9) numericChanged += 1;
  }
  return [
    channel,
    channel.startsWith("DO_") ? "DO" : "ORP",
    expectedBins,
    rawValid,
    values.length,
    values.length / expectedBins,
    sourceMissing,
    qualityExcluded,
    numericChanged,
    Math.min(...values),
    median(values),
    values.reduce((sum, value) => sum + value, 0) / values.length,
    Math.max(...values),
    longestMissingRun(combined, channel),
  ];
});

const dailyRows = [];
for (let day = 0; day < 31; day += 1) {
  const dayRows = combined.slice(day * 288, (day + 1) * 288);
  const fraction = (scope) => dayRows.filter((row) => scope.every((channel) => row[channel] != null)).length / 288;
  dailyRows.push([excelSerial(dayRows[0].datetime), fraction(doChannels), fraction(orpChannels), fraction(channels)]);
}

const blockRows = [];
for (const [scopeName, scope] of [["DO8", doChannels], ["ORP6", orpChannels], ["DO8+ORP6", channels]]) {
  for (const run of completeRuns(combined, scope)) {
    blockRows.push([
      scopeName,
      excelSerial(run.start),
      excelSerial(run.endExclusive),
      run.bins,
      run.hours,
      run.hours >= 24 ? "Yes" : "No",
    ]);
  }
}
blockRows.sort((a, b) => a[0].localeCompare(b[0]) || a[1] - b[1]);

const sourceHashes = Object.fromEntries(Object.entries(sourceBuffers).map(([name, buffer]) => [name, sha256(buffer)]));
const jointComplete = combined.filter((row) => channels.every((channel) => row[channel] != null)).length;
const contractRows = [
  ["run_id", "SUMO-DQR-OCT2025-5MIN-20261009"],
  ["period", "2025-10-01 00:00:00 <= t < 2025-11-01 00:00:00"],
  ["time_step", "5 min"],
  ["expected_rows", String(expectedBins)],
  ["time_days", "Reset to 0 at 2025-10-01 00:00:00"],
  ["channels", "DO8 + ORP6"],
  ["joint_complete_bins", String(jointComplete)],
  ["joint_complete_pct", `${(100 * jointComplete / expectedBins).toFixed(3)}%`],
  ["missing_policy", "DQR-unavailable and source-missing bins remain blank; no interpolation or Raw fallback"],
  ["SUMO_use", "Use only continuous blocks listed in Runnable_Blocks, or apply a separately validated repair/restart protocol"],
  ["ORP_semantics", "Signed negative ORP is retained as physical signal"],
  ["DO4_semantics", "DQR zero-equivalent physicalization is retained; Raw remains in the frozen source product"],
  ["validation_semantics", "October 2025 is retrospective development data, not prospective blind validation"],
  ["source_DQR_DO", path.basename(files.dqrDo)],
  ["source_DQR_DO_sha256", sourceHashes.dqrDo],
  ["source_DQR_ORP", path.basename(files.dqrOrp)],
  ["source_DQR_ORP_sha256", sourceHashes.dqrOrp],
  ["source_Raw", path.basename(files.raw)],
  ["source_Raw_sha256", sourceHashes.raw],
  ["source_manifest", path.basename(files.manifest)],
  ["source_manifest_sha256", sourceHashes.manifest],
];

const workbook = Workbook.create();
const inputSheet = workbook.worksheets.add("SUMO_Input");
const qaSheet = workbook.worksheets.add("Channel_QA");
const dailySheet = workbook.worksheets.add("Daily_Coverage");
const blocksSheet = workbook.worksheets.add("Runnable_Blocks");
const contractSheet = workbook.worksheets.add("Contract");

const inputHeader = ["datetime", "time_days", ...channels];
const inputValues = combined.map((row) => [
  excelSerial(row.datetime), row.time_days, ...channels.map((channel) => row[channel]),
]);
inputSheet.getRangeByIndexes(0, 0, 1, inputHeader.length).values = [inputHeader];
inputSheet.getRangeByIndexes(1, 0, inputValues.length, inputHeader.length).values = inputValues;
applyHeaderStyle(inputSheet.getRangeByIndexes(0, 0, 1, inputHeader.length));
applyBodyStyle(inputSheet.getRangeByIndexes(1, 0, inputValues.length, inputHeader.length));
inputSheet.getRange(`A2:A${inputValues.length + 1}`).setNumberFormat("yyyy-mm-dd hh:mm");
inputSheet.getRange(`B2:B${inputValues.length + 1}`).setNumberFormat("0.000000");
inputSheet.getRange(`C2:J${inputValues.length + 1}`).setNumberFormat("0.000");
inputSheet.getRange(`K2:P${inputValues.length + 1}`).setNumberFormat("0.000");
inputSheet.getRange(`A1:A${inputValues.length + 1}`).format.columnWidth = 19;
inputSheet.getRange(`B1:B${inputValues.length + 1}`).format.columnWidth = 12;
inputSheet.getRange(`C1:P${inputValues.length + 1}`).format.columnWidth = 11;
inputSheet.freezePanes.freezeRows(1);
inputSheet.freezePanes.freezeColumns(2);
inputSheet.showGridLines = false;
inputSheet.tabColor = "#1F4E79";
inputSheet.getRange(`C2:P${inputValues.length + 1}`).conditionalFormats.add("containsBlanks", {
  format: { fill: "#FCE8E6", font: { color: "#B3261E" } },
});

const qaHeader = ["channel", "analyte", "expected_bins", "raw_valid_bins", "dqr_valid_bins", "dqr_completeness", "source_missing_bins", "dqr_excluded_bins", "numeric_changed_bins", "min", "median", "mean", "max", "longest_missing_run_bins"];
qaSheet.getRangeByIndexes(0, 0, 1, qaHeader.length).values = [qaHeader];
qaSheet.getRangeByIndexes(1, 0, qaRows.length, qaHeader.length).values = qaRows;
applyHeaderStyle(qaSheet.getRangeByIndexes(0, 0, 1, qaHeader.length));
applyBodyStyle(qaSheet.getRangeByIndexes(1, 0, qaRows.length, qaHeader.length));
qaSheet.getRange(`F2:F${qaRows.length + 1}`).setNumberFormat("0.000%");
qaSheet.getRange(`J2:M${qaRows.length + 1}`).setNumberFormat("0.000");
qaSheet.getRange(`A1:N${qaRows.length + 1}`).format.autofitColumns();
qaSheet.getRange("A1:A15").format.columnWidth = 13;
qaSheet.freezePanes.freezeRows(1);
qaSheet.showGridLines = false;
qaSheet.tabColor = "#5B9BD5";

const dailyHeader = ["date", "DO8_complete", "ORP6_complete", "DO8_ORP6_complete"];
dailySheet.getRangeByIndexes(0, 0, 1, dailyHeader.length).values = [dailyHeader];
dailySheet.getRangeByIndexes(1, 0, dailyRows.length, dailyHeader.length).values = dailyRows;
applyHeaderStyle(dailySheet.getRangeByIndexes(0, 0, 1, dailyHeader.length));
applyBodyStyle(dailySheet.getRangeByIndexes(1, 0, dailyRows.length, dailyHeader.length));
dailySheet.getRange(`A2:A${dailyRows.length + 1}`).setNumberFormat("yyyy-mm-dd");
dailySheet.getRange(`B2:D${dailyRows.length + 1}`).setNumberFormat("0.0%");
dailySheet.getRange(`A1:D${dailyRows.length + 1}`).format.autofitColumns();
dailySheet.freezePanes.freezeRows(1);
dailySheet.showGridLines = false;
dailySheet.tabColor = "#70AD47";

const blockHeader = ["scope", "start", "end_exclusive", "bins", "hours", "at_least_24h"];
blocksSheet.getRangeByIndexes(0, 0, 1, blockHeader.length).values = [blockHeader];
blocksSheet.getRangeByIndexes(1, 0, blockRows.length, blockHeader.length).values = blockRows;
applyHeaderStyle(blocksSheet.getRangeByIndexes(0, 0, 1, blockHeader.length));
applyBodyStyle(blocksSheet.getRangeByIndexes(1, 0, blockRows.length, blockHeader.length));
blocksSheet.getRange(`B2:C${blockRows.length + 1}`).setNumberFormat("yyyy-mm-dd hh:mm");
blocksSheet.getRange(`E2:E${blockRows.length + 1}`).setNumberFormat("0.00");
blocksSheet.getRange(`A1:F${blockRows.length + 1}`).format.autofitColumns();
blocksSheet.getRange(`B1:C${blockRows.length + 1}`).format.columnWidth = 19;
blocksSheet.freezePanes.freezeRows(1);
blocksSheet.showGridLines = false;
blocksSheet.tabColor = "#A5A5A5";

contractSheet.getRange("A1:B1").values = [["field", "value"]];
contractSheet.getRangeByIndexes(1, 0, contractRows.length, 2).values = contractRows;
applyHeaderStyle(contractSheet.getRange("A1:B1"));
applyBodyStyle(contractSheet.getRangeByIndexes(1, 0, contractRows.length, 2));
contractSheet.getRange(`A1:A${contractRows.length + 1}`).format.columnWidth = 28;
contractSheet.getRange(`B1:B${contractRows.length + 1}`).format.columnWidth = 92;
contractSheet.getRange(`B2:B${contractRows.length + 1}`).format.wrapText = true;
contractSheet.getRange(`A2:B${contractRows.length + 1}`).format.rowHeight = 30;
contractSheet.freezePanes.freezeRows(1);
contractSheet.showGridLines = false;
contractSheet.tabColor = "#ED7D31";

workbook.recalculate();
const inspect = await workbook.inspect({
  kind: "sheet,region",
  maxChars: 8000,
  tableMaxRows: 6,
  tableMaxCols: 16,
});
await fs.writeFile(path.join(outputDir, "workbook_inspect.ndjson"), inspect.ndjson, "utf8");
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
await fs.writeFile(path.join(outputDir, "workbook_error_scan.ndjson"), errors.ndjson, "utf8");

for (const [sheetName, range] of [["SUMO_Input", "A1:P25"], ["Channel_QA", "A1:N15"], ["Daily_Coverage", "A1:D32"], ["Runnable_Blocks", `A1:F${Math.min(blockRows.length + 1, 35)}`], ["Contract", `A1:B${contractRows.length + 1}`]]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.4, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputXlsx);

const longestJointBlock = completeRuns(combined, channels).sort((a, b) => b.bins - a.bins)[0];
const outputHashes = {
  csv: sha256(await fs.readFile(outputCsv)),
  xlsx: sha256(await fs.readFile(outputXlsx)),
};
const verification = {
  run_id: "SUMO-DQR-OCT2025-5MIN-20261009",
  checks: {
    expected_rows: combined.length === expectedBins,
    exact_5min_timebase: combined.every((row, index) => row.datetime === timestampFromIndex(index)),
    DO_nonnegative_where_available: doChannels.every((channel) => combined.every((row) => row[channel] == null || row[channel] >= 0)),
    signed_negative_ORP_retained: orpChannels.every((channel) => combined.some((row) => row[channel] != null && row[channel] < 0)),
    no_interpolation_or_raw_fallback: true,
  },
  rows: combined.length,
  channels,
  joint_complete_bins: jointComplete,
  joint_complete_pct: 100 * jointComplete / expectedBins,
  longest_joint_complete_block: longestJointBlock,
  source_sha256: sourceHashes,
  output_sha256: outputHashes,
  builder_sha256: sha256(await fs.readFile(fileURLToPath(import.meta.url))),
};
await fs.writeFile(outputVerification, `${JSON.stringify(verification, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  outputCsv,
  outputXlsx,
  rows: combined.length,
  jointCompleteBins: jointComplete,
  jointCompletePct: 100 * jointComplete / expectedBins,
  longestJointBlock,
  sourceHashes,
  outputHashes,
}, null, 2));
process.exitCode = 0;
