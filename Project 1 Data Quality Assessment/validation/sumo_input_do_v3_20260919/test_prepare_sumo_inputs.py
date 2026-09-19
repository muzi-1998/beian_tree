from __future__ import annotations

import numpy as np
import pandas as pd

from prepare_sumo_inputs import (
    ColumnSpec,
    _bounded_linear_interpolate,
    _physical_screen,
    clean_frame,
    make_derived,
)


def test_bounded_interpolation_fills_only_complete_short_gaps() -> None:
    index = pd.date_range("2025-01-01", periods=12, freq="1min")
    source = pd.Series([1.0, np.nan, np.nan, 4.0, 5.0, np.nan, np.nan, np.nan, np.nan, 10.0, np.nan, 12.0], index=index)
    result, filled = _bounded_linear_interpolate(source, max_gap=3)
    assert filled.sum() == 3
    assert result.iloc[1] == 2.0
    assert result.iloc[2] == 3.0
    assert result.iloc[5:9].isna().all()
    assert result.iloc[10] == 11.0


def test_negative_flow_separates_zero_equivalent_from_invalid() -> None:
    index = pd.date_range("2025-01-01", periods=6, freq="1min")
    source = pd.Series([100.0, 110.0, -2.0, -20.0, 0.0, 90.0], index=index)
    spec = ColumnSpec("test", "flow", "flow", "m3/h", "flow")
    clean, invalid, zero, deadband = _physical_screen(source, spec)
    assert deadband == 5.0
    assert clean.iloc[2] == 0.0
    assert zero.iloc[2]
    assert invalid.iloc[3]
    assert np.isnan(clean.iloc[3])


def test_user_specified_derived_formulas() -> None:
    index = pd.date_range("2025-01-01", periods=1, freq="1min")
    frame = pd.DataFrame(index=index)
    for column in [
        "进水瞬时流量（m³/h）",
        "出水瞬时流量（m³/h）",
        "氯化铁流量计1（m³/h）",
        "氯化铁流量计2（m³/h）",
        "乙酸钠流量计2（m³/h）",
        "乙酸钠流量计4（m³/h）",
        "FIT1531A排泥流量（m³/h）",
        "FIT1531B排泥流量（m³/h）",
        "1#生物池外回流流量（m³/h）",
        "2#生物池外回流流量（m³/h）",
        "1#生物池内回流流量（m³/h）",
        "2#生物池内回流流量（m³/h）",
        "剩余污泥流量（m³/h）",
    ]:
        frame[column] = 1.0
    frame["进水氨氮（mg/L）"] = 20.0
    frame["进水总氮（mg/L）"] = 50.0
    frame["出水COD（mg/L）"] = 10.0
    result = make_derived(frame)
    assert result.iloc[0]["进水瞬时流量（m³/d）"] == 24.0
    assert result.iloc[0]["MBR循环流（m³/d）"] == 72.0
    assert result.iloc[0]["frSNHx_TKN（氨氮/总氮）"] == 0.4
    assert result.iloc[0]["frSU_SCCOD代理量（mg/L）"] == 7.5


def test_flow_hampel_candidates_are_not_automatically_replaced() -> None:
    index = pd.date_range("2025-01-01", periods=21, freq="1min", name="日期")
    values = [10.0, 10.1, 9.9, 10.2, 9.8] * 2 + [1000.0] + [10.0, 10.1, 9.9, 10.2, 9.8] * 2
    raw = pd.DataFrame({"flow": values}, index=index)
    spec = ColumnSpec("test", "flow", "flow", "m3/h", "flow")
    clean, _, qa = clean_frame(raw, [spec])
    assert clean.iloc[10, 0] == 1000.0
    assert qa.iloc[0]["Hampel候选率（%）"] > 0
    assert qa.iloc[0]["Hampel替换率（%）"] == 0
