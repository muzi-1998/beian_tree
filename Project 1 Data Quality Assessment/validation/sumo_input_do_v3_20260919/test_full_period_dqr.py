import pandas as pd

from export_full_period_dqr import BOUNDARY, END, START, WINDOW_DAYS, same_hour_evidence


def test_same_hour_evidence_does_not_shift_the_hour():
    index = pd.date_range("2026-01-01 01:00", periods=60, freq="min")
    evidence = pd.DataFrame({
        "timestamp": [pd.Timestamp("2026-01-01 01:00")],
        "Q_node_available": [4.2], "E_node": [1], "D3_gate_status": ["Pass"],
        "D5_report_score": [4.0], "coverage_class": ["full"],
    })
    joined = same_hour_evidence(index, evidence)
    assert joined.index.equals(index)
    assert joined["Q_node_available"].eq(4.2).all()


def test_full_period_and_boundary_contract_are_explicit():
    assert START == pd.Timestamp("2025-08-01 00:00:00")
    assert BOUNDARY == pd.Timestamp("2026-04-14 00:00:00")
    assert END == pd.Timestamp("2026-07-31 00:00:00")
    assert WINDOW_DAYS == 14
