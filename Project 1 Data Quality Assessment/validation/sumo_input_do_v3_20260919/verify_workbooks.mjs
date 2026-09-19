import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const baseDir = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.join(baseDir, "outputs");
const previewDir = path.join(outputDir, "previews");
await fs.mkdir(previewDir, { recursive: true });

// These two files cover both workbook layouts. The full-resolution workbooks
// use the same streaming template and are checked structurally by
// workbook_structural_QA.json.
const requested = process.argv.slice(2);
const files = requested.length ? requested : ["SUMO_process_inputs_1h.xlsx", "SUMO_DO_ORP_5min.xlsx"];
for (const filename of files) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(outputDir, filename)));
  const sheetInfo = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
  await fs.writeFile(path.join(previewDir, `${filename}.sheets.ndjson`), sheetInfo.ndjson, "utf8");
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 },
    summary: "formula error scan",
  });
  await fs.writeFile(path.join(previewDir, `${filename}.errors.ndjson`), errors.ndjson, "utf8");
  for (const sheet of workbook.worksheets.items) {
    const preview = await workbook.render({
      sheetName: sheet.name,
      range: sheet.name === "QA" || sheet.name === "DataDictionary" ? "A1:H18" : "A1:H20",
      scale: 1.4,
      format: "png",
    });
    await fs.writeFile(
      path.join(previewDir, `${filename}.${sheet.name}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}
