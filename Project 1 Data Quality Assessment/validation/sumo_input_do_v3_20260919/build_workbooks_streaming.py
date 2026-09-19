from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
import xlsxwriter


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
INTERMEDIATE_DIR = OUTPUT_DIR / "intermediate"


SPECIFICATIONS = [
    (
        "SUMO_process_inputs_1min.xlsx",
        [("Raw", "process_1min_raw.csv"), ("Clean", "process_1min_clean.csv"), ("Derived_m3d", "process_1min_derived.csv")],
        "process",
    ),
    (
        "SUMO_process_inputs_5min.xlsx",
        [("Raw", "process_5min_raw.csv"), ("Clean", "process_5min_clean.csv"), ("Derived_m3d", "process_5min_derived.csv")],
        "process",
    ),
    (
        "SUMO_process_inputs_1h.xlsx",
        [("Raw", "process_1h_raw.csv"), ("Clean", "process_1h_clean.csv"), ("Derived_m3d", "process_1h_derived.csv")],
        "process",
    ),
    (
        "SUMO_DO_ORP_1min.xlsx",
        [("Raw", "sensors_1min_raw.csv"), ("Clean", "sensors_1min_clean.csv")],
        "sensor",
    ),
    (
        "SUMO_DO_ORP_5min.xlsx",
        [("Raw", "sensors_5min_raw.csv"), ("Clean", "sensors_5min_clean.csv")],
        "sensor",
    ),
]


def _is_sensor(variable: str) -> bool:
    return variable.startswith("DO_") or variable.startswith("ORP_")


def _convert(value: str, column: int):
    if value == "":
        return None
    if column == 0:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value
    try:
        return float(value)
    except ValueError:
        return value


def _write_csv_sheet(workbook, name: str, csv_path: Path, formats: dict[str, object]) -> tuple[int, int]:
    worksheet = workbook.add_worksheet(name)
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(1, 1)
    worksheet.set_column(0, 0, 19)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        worksheet.write_row(0, 0, header, formats["header"])
        worksheet.set_row(0, 52)
        worksheet.set_column(1, len(header) - 1, 22)
        for row_index, row in enumerate(reader, start=1):
            timestamp = _convert(row[0], 0)
            if isinstance(timestamp, datetime):
                worksheet.write_datetime(row_index, 0, timestamp, formats["date"])
            else:
                worksheet.write(row_index, 0, timestamp, formats["text"])
            values = [_convert(value, column_index) for column_index, value in enumerate(row[1:], start=1)]
            worksheet.write_row(row_index, 1, values, formats["number"])
    worksheet.autofilter(0, 0, row_index, len(header) - 1)
    return row_index + 1, len(header)


def _write_small_sheet(workbook, name: str, frame: pd.DataFrame, formats: dict[str, object]) -> None:
    worksheet = workbook.add_worksheet(name)
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(1, 0)
    worksheet.write_row(0, 0, list(frame.columns), formats["header_secondary"])
    worksheet.set_row(0, 52)
    for row_index, row in enumerate(frame.itertuples(index=False, name=None), start=1):
        for column_index, value in enumerate(row):
            if pd.isna(value):
                worksheet.write_blank(row_index, column_index, None, formats["text"])
            elif isinstance(value, (int, float)):
                worksheet.write_number(row_index, column_index, float(value), formats["number"])
            else:
                worksheet.write(row_index, column_index, str(value), formats["text"])
    for column_index, column in enumerate(frame.columns):
        longest = max(len(str(column)), *(len(str(value)) for value in frame[column].head(200).fillna("")))
        worksheet.set_column(column_index, column_index, min(max(longest + 2, 12), 30))
    worksheet.autofilter(0, 0, len(frame), len(frame.columns) - 1)


def build() -> None:
    qa_all = pd.read_csv(INTERMEDIATE_DIR / "qa_summary.csv", encoding="utf-8-sig")
    dictionary_all = pd.read_csv(INTERMEDIATE_DIR / "data_dictionary.csv", encoding="utf-8-sig")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for filename, sheets, scope in SPECIFICATIONS:
        workbook = xlsxwriter.Workbook(
            OUTPUT_DIR / filename,
            {"constant_memory": True, "nan_inf_to_errors": True},
        )
        workbook.set_properties(
            {
                "title": filename.removesuffix(".xlsx"),
                "subject": "SUMO Input DO downstream-validation data package",
                "author": "Project 1 Data Quality Assessment",
                "comments": "Raw observations are preserved. See QA and DataDictionary.",
            }
        )
        formats = {
            "header": workbook.add_format(
                {"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1, "border_color": "#17365D"}
            ),
            "header_secondary": workbook.add_format(
                {"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "#FFFFFF", "bg_color": "#44546A", "align": "center", "valign": "vcenter", "text_wrap": True}
            ),
            "date": workbook.add_format({"font_name": "Arial", "font_size": 9, "num_format": "yyyy-mm-dd hh:mm", "valign": "vcenter"}),
            "number": workbook.add_format({"font_name": "Arial", "font_size": 9, "num_format": "0.0000", "valign": "vcenter"}),
            "text": workbook.add_format({"font_name": "Arial", "font_size": 9, "valign": "vcenter"}),
        }
        for sheet_name, csv_name in sheets:
            _write_csv_sheet(workbook, sheet_name, INTERMEDIATE_DIR / csv_name, formats)
        sensor_scope = scope == "sensor"
        qa = qa_all[qa_all["变量"].map(_is_sensor) == sensor_scope]
        dictionary = dictionary_all[dictionary_all["输出变量"].map(_is_sensor) == sensor_scope]
        _write_small_sheet(workbook, "QA", qa, formats)
        _write_small_sheet(workbook, "DataDictionary", dictionary, formats)
        workbook.close()


if __name__ == "__main__":
    build()
