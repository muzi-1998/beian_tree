from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import pytest

from dqr_asof_adapter import asof_evidence
from dqr_aggregation.pipeline import resolve_release_status
from d5_frozen_adapter import FrozenD5Mapper
from runtime import D5_REFERENCE_END, OUTPUT


def fixture():
    grid = pd.DataFrame({"timestamp": pd.to_datetime(["2026-04-14 00:00", "2026-04-14 01:00", "2026-04-14 02:00"]),
                         "sensor_id": "DO_1_1"})
    grid["decision_at"] = grid.timestamp + pd.Timedelta(hours=1)
    source = pd.DataFrame({"timestamp": pd.to_datetime(["2026-04-14 01:00", "2026-04-14 02:00"]),
                           "available_at": pd.to_datetime(["2026-04-14 01:10", "2026-04-14 02:10"]),
                           "sensor_id": "DO_1_1", "score": [4.2, np.nan]})
    return grid, source


def test_no_open_snapshot_no_backward_search_for_valid_score():
    grid, source = fixture()
    out = asof_evidence(grid, source, dimension="D5", object_id="sensor_id", lifetime="1h")
    assert np.isnan(out.score.iloc[0])
    assert out.score.iloc[1] == 4.2
    assert np.isnan(out.score.iloc[2])
    assert out.D5_source_label.iloc[2] == source.timestamp.iloc[1]


def test_half_open_expiry_and_prefix():
    grid, source = fixture()
    grid["decision_at"] += pd.Timedelta(minutes=10)
    out = asof_evidence(grid, source, dimension="D5", object_id="sensor_id", lifetime="1h")
    short = asof_evidence(grid.iloc[:1], source.iloc[:1], dimension="D5", object_id="sensor_id", lifetime="1h")
    pd.testing.assert_frame_equal(short, out.iloc[:1])
    expired = asof_evidence(grid.iloc[1:2], source.iloc[:1], dimension="D5", object_id="sensor_id", lifetime="1h")
    assert expired.score.isna().all()


def test_duplicate_information_clock_rejected():
    grid, source = fixture()
    with pytest.raises(ValueError, match="ambiguous"):
        asof_evidence(grid, pd.concat([source, source]), dimension="D5", object_id="sensor_id", lifetime="1h")


def test_expired_boolean_evidence_remains_unknown():
    grid, source = fixture()
    source["eligible"] = True
    grid["decision_at"] += pd.Timedelta(minutes=10)
    out = asof_evidence(grid.iloc[1:2], source.iloc[:1], dimension="D5", object_id="sensor_id", lifetime="1h")
    assert out.eligible.isna().all()
    assert out.score.isna().all()


def test_gate_fail_precedes_missing_quality():
    status = resolve_release_status(pd.Series([np.nan, 4., 4.]), pd.Series(["Fail", "Fail", None]),
                                    pd.Series(["insufficient", "full", "full"]))
    assert status.tolist() == ["gate_fail", "gate_fail", "gate_not_evaluated"]


def test_frozen_ecdf_never_fits_unknown_stratum():
    asset = dict(fitted_until=str(D5_REFERENCE_END), gamma=1., records=[], references=[
        dict(risk_metric="risk_profile", analyte="DO", regime_id=0, zone_id="A", values=list(range(20)))])
    mapper = FrozenD5Mapper(asset)
    source = pd.DataFrame(dict(analyte=["DO", "DO", "ORP"], active_regime_id=[0, 1, 0], zone_id=["A"]*3,
                               risk_profile=[10., 10., 10.], risk_gradient=[0.]*3, risk_rank=[0.]*3, risk_rep=[0.]*3))
    out = mapper.transform(source)
    assert out.Q_profile.iloc[0] == pytest.approx(2.8)
    assert out.Q_profile.iloc[1:].isna().all()
    assert out[["Q_gradient", "Q_rank", "Q_rep"]].isna().all().all()
    pd.testing.assert_frame_equal(mapper.transform(source.iloc[:1]), out.iloc[:1])


def test_frozen_support_does_not_include_future_fit():
    asset = json.loads((OUTPUT / "assets/D5_frozen_inference.json").read_text())
    assert pd.Timestamp(asset["fitted_until"]) == D5_REFERENCE_END
    assert len(asset["support"]) == 56
    assert "L1" in {row["support_level"] for row in asset["support"]}
    assert all(len(row["values"]) >= 20 for row in asset["references"])


def test_d5_row_arithmetic_is_batch_length_invariant():
    from d5_frozen_adapter import FrozenD5
    from d5_local.evidence.engine import SpatialEvidenceEngine
    model = FrozenD5()
    template = next(t for t in model.templates.values() if len(t.reconstruction_neighbors) > 1)
    rng = np.random.default_rng(906)
    x = pd.DataFrame(rng.normal(size=(1501, len(template.sensor_order))), columns=template.sensor_order)
    engine = SpatialEvidenceEngine(model.pipeline.topology, stable_row_reduction=True)
    full = engine._score_template(x, template)
    for n in [3, 51, 1000]:
        short = engine._score_template(x.iloc[:n], template)
        for name in full:
            np.testing.assert_array_equal(short[name], full[name][:n])
