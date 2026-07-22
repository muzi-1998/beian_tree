from __future__ import annotations

import numpy as np
import pandas as pd

from src.detectors.drift_pls import core_engineered_peers, select_pls_peers


def test_core_peers_never_bind_do_to_orp_by_suffix():
    columns = ["DO_1_1", "DO_1_2", "DO_2_1", "ORP_1_1"]
    peers = core_engineered_peers("DO_1_1", columns)
    assert peers == ["DO_1_2", "DO_2_1"]
    assert "ORP_1_1" not in peers


def test_blocked_cv_adds_informative_same_analyte_candidate():
    rng = np.random.default_rng(7)
    n = 24 * 50
    informative = rng.normal(size=n)
    frame = pd.DataFrame({
        "DO_1_1": 1.8 * informative + rng.normal(scale=0.08, size=n),
        "DO_1_2": rng.normal(size=n),
        "DO_2_1": rng.normal(size=n),
        "DO_1_3": informative,
        "ORP_1_1": informative,
    })
    audit = select_pls_peers(frame, "DO_1_1")
    assert "DO_1_3" in audit["selected_peers"]
    assert "ORP_1_1" not in audit["candidate_peers"]
    assert audit["cv_improvement_pct"] > 2.0


def test_floor_route_can_be_target_but_not_another_targets_predictor():
    rng = np.random.default_rng(8)
    frame = pd.DataFrame(rng.normal(size=(24 * 50, 5)), columns=[
        "DO_1_1", "DO_1_2", "DO_1_3", "DO_1_4", "DO_2_3",
    ])
    audit = select_pls_peers(
        frame,
        "DO_1_3",
        excluded_predictors={"DO_1_4"},
    )
    assert "DO_1_4" not in audit["core_peers"]
    assert "DO_1_4" not in audit["candidate_peers"]


def test_single_topology_peer_is_preserved_when_twin_is_excluded():
    rng = np.random.default_rng(9)
    n = 24 * 50
    adjacent = rng.normal(size=n)
    frame = pd.DataFrame({
        "DO_1_1": rng.normal(size=n),
        "DO_1_2": rng.normal(size=n),
        "DO_1_4": rng.normal(size=n),
        "DO_2_2": rng.normal(size=n),
        "DO_2_3": adjacent,
        "DO_2_4": 1.4 * adjacent + rng.normal(scale=0.08, size=n),
    })
    audit = select_pls_peers(
        frame,
        "DO_2_4",
        excluded_predictors={"DO_1_4"},
    )

    assert audit["core_peers"] == ["DO_2_3"]
    assert audit["selected_peers"] == ["DO_2_3"]
    assert audit["candidate_peers"] == ["DO_2_2"]
    assert audit["redundancy_status"] == "limited_single_peer"
    assert "DO_1_1" not in audit["selected_peers"]
    assert "DO_1_2" not in audit["selected_peers"]
