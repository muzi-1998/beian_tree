import pandas as pd
import pytest

from audit_intake import compare_overlap, mapping_rows, unique_source


def source_columns():
    columns = ["\u65e5\u671f"]
    for analyte, count, unit in (("DO", 4, "mg/L"), ("ORP", 3, "mV")):
        for line in (1, 2):
            for position in range(1, count + 1):
                columns.append(f"{line}#\u751f\u7269\u6c60{analyte}{position}\uff08{unit}\uff09")
    for direction in ("\u5916", "\u5185"):
        for line in (1, 2):
            columns.append(f"{line}#\u751f\u7269\u6c60{direction}\u56de\u6d41\u6d41\u91cf\uff08m\u00b3/h\uff09")
    return columns


def test_complete_mapping_preserves_analyte_line_position_and_context():
    rows = mapping_rows(source_columns())
    assert len(rows) == 18
    assert sum(r["role"] == "scored_sensor" for r in rows) == 14
    assert {r["canonical_id"] for r in rows if r["role"] == "context_only"} == {"QR_1", "QR_2", "QIR_1", "QIR_2"}
    assert rows[0]["canonical_id"] == "DO_1_1"
    assert rows[5]["canonical_id"] == "DO_2_2"


@pytest.mark.parametrize("mode", ["missing", "duplicate", "bad_unit", "orp4"])
def test_invalid_mapping_fails_closed(mode):
    columns = source_columns()
    if mode == "missing":
        columns.pop()
    elif mode == "duplicate":
        columns.append(columns[1])
    elif mode == "bad_unit":
        columns[1] = columns[1].replace("mg/L", "mV")
    else:
        columns[9] = columns[9].replace("ORP1", "ORP4")
    with pytest.raises(ValueError):
        mapping_rows(columns)


def test_equal_overlap_does_not_hide_inserted_timestamp_values():
    index = pd.date_range("2026-04-01", periods=4, freq="min")
    new = pd.DataFrame({"DO_1_1": [1.0, 2.0, None, 4.0]}, index=index)
    old = new.drop(index[1:3])
    result = compare_overlap(old, new, "synthetic")[0]
    assert result["equal_within_1e_9_fraction"] == 1
    assert result["new_only_timestamps_inside_old_span"] == 2
    assert result["inserted_timestamp_new_present"] == 1
    assert result["inserted_timestamp_new_missing"] == 1


def test_overlap_cannot_use_holdout_values():
    new = pd.DataFrame({"DO_1_1": [1.0]}, index=pd.to_datetime(["2026-04-14"]))
    with pytest.raises(ValueError, match="precede holdout"):
        compare_overlap(new, new, "synthetic")


def test_source_selection_rejects_ambiguous_export(tmp_path):
    with pytest.raises(ValueError):
        unique_source(tmp_path, "*.csv")
    first = tmp_path / "one.csv"
    first.touch()
    assert unique_source(tmp_path, "*.csv") == first
    (tmp_path / "two.csv").touch()
    with pytest.raises(ValueError):
        unique_source(tmp_path, "*.csv")
