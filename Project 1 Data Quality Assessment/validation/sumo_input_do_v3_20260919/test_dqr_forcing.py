import numpy as np
import pandas as pd

from export_dqr_forcing import aggregate_complete, align_scores, decide, fill_native_short_gaps


def quality(index, q=4.5, e=1.0, gate="Pass"):
    return pd.DataFrame({"Q_node_available": q, "E_node": e, "D3_gate_status": gate}, index=index)


def test_incomplete_low_score_does_not_invent_fault_or_repair():
    ix = pd.date_range("2026-04-14", periods=3, freq="min")
    raw = pd.Series([1., 2., 3.], index=ix)
    evidence = quality(ix, q=2., e=2/3)
    result = decide(raw, evidence, is_do=True)
    assert result.action.eq("KEEP").all()
    assert result.evidence_limited.all()
    assert result.forcing.equals(raw)
    evidence.E_node = 1.
    result = decide(raw, evidence, is_do=True)
    assert result.action.eq("UNRECOVERABLE").all()
    assert result.forcing.isna().all()


def test_fail_overrides_missing_evidence_but_warn_is_not_failure():
    ix = pd.date_range("2026-04-14", periods=2, freq="min")
    evidence = quality(ix, e=np.nan)
    evidence.D3_gate_status = ["Fail", "Warn"]
    result = decide(pd.Series([2., 2.], index=ix), evidence, is_do=True)
    assert result.action.tolist() == ["UNRECOVERABLE", "KEEP"]


def test_no_future_scores_and_half_open_expiry():
    index = pd.to_datetime(["2026-04-14 01:02", "2026-04-14 01:03", "2026-04-14 02:02", "2026-04-14 02:03"])
    evidence = pd.DataFrame({"decision_at": pd.to_datetime(["2026-04-14 01:03"]), "Q_node_available": [2.]})
    result = align_scores(index, evidence)
    assert result.Q_node_available.isna().tolist() == [True, False, False, True]


def test_short_native_gaps_need_trusted_endpoints_and_faults_not_interpolated():
    ix = pd.date_range("2026-04-14", periods=10, freq="min")
    raw = pd.Series([1., np.nan, np.nan, 4., np.nan, np.nan, np.nan, np.nan, 9., 10.], index=ix)
    evidence = quality(ix)
    result = fill_native_short_gaps(decide(raw, evidence, is_do=True), evidence)
    assert result.forcing.iloc[:4].tolist() == [1., 2., 3., 4.]
    assert result.forcing.iloc[4:8].isna().all()
    assert result.action.iloc[1:3].eq("REPAIR").all()
    evidence.E_node = 2/3
    result = fill_native_short_gaps(decide(raw, evidence, is_do=True), evidence)
    assert result.forcing.iloc[1:3].isna().all()


def test_do4_zero_equivalence_is_common_representation_and_orp_stays_signed():
    ix = pd.date_range("2026-04-14", periods=4, freq="min")
    raw = pd.Series([-.03, -.05, -.06, .01], index=ix)
    result = decide(raw, quality(ix), is_do=True, zero_low=-.05)
    assert result.forcing.iloc[:2].eq(0).all()
    assert result.dqr_measurement.iloc[0] == -.03
    assert pd.isna(result.forcing.iloc[2])
    orp = decide(pd.Series([-500., -200., 0., 100.], index=ix), quality(ix), is_do=False)
    assert orp.forcing.iloc[0] == -500.


def test_a_missing_minute_cannot_disappear_in_five_minute_mean():
    ix = pd.date_range("2026-04-14", periods=10, freq="min")
    frame = pd.DataFrame({"DO_1_1": [1., 2., np.nan, 4., 5., 6., 7., 8., 9., 10.]}, index=ix)
    result = aggregate_complete(frame)
    assert pd.isna(result.iloc[0, 0])
    assert result.iloc[1, 0] == 8.
