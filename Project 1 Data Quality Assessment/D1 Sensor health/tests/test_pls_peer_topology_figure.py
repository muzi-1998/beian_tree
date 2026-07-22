from __future__ import annotations

import pandas as pd
import pytest

from make_pls_peer_topology_figure import build_peer_tables


def _state() -> dict:
    channels = ["DO_1_1", "DO_1_2", "DO_2_1"]
    audit = pd.DataFrame(
        {
            "selected_peers": ["DO_1_2;DO_2_1", "DO_1_1", "DO_1_1"],
            "selected_noncore_peers": ["", "", ""],
            "selected_n_components": [2, 1, 1],
            "redundancy_status": ["multi_peer", "limited_single_peer", "limited_single_peer"],
            "validation_status": ["locked", "locked", "locked"],
        },
        index=channels,
    )
    matrix = pd.DataFrame(0, index=channels, columns=channels, dtype=int)
    matrix.loc["DO_1_1", ["DO_1_2", "DO_2_1"]] = 1
    matrix.loc["DO_1_2", "DO_1_1"] = 1
    matrix.loc["DO_2_1", "DO_1_1"] = 1
    return {
        "scored_channels": channels,
        "scoring_mode": {},
        "detectors_raw": {
            "pls_peer_selection_audit": audit,
            "pls_peer_matrix": matrix,
        },
    }


def test_build_peer_tables_classifies_active_core_edges() -> None:
    tables = build_peer_tables(_state())
    classes = tables["topology_class_matrix"]
    assert classes.at["DO_1_1", "DO_1_2"] == 1
    assert classes.at["DO_1_1", "DO_2_1"] == 2
    assert len(tables["formal_peer_pairs"]) == 4


def test_build_peer_tables_rejects_stale_matrix() -> None:
    state = _state()
    state["detectors_raw"]["pls_peer_matrix"].at["DO_1_1", "DO_2_1"] = 0
    with pytest.raises(ValueError, match="Stale PLS matrix"):
        build_peer_tables(state)
