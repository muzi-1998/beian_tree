from __future__ import annotations

from enum import Enum


class EvaluationStatus(str, Enum):
    EVALUABLE = "evaluable"
    REPORT_ONLY = "report_only"
    LIMITED_SUPPORT = "limited_support"
    OUT_OF_TEMPLATE = "out_of_template"
    TOPOLOGY_SUSPECT = "topology_suspect"
    NOT_EVALUABLE = "not_evaluable"
    NOT_APPLICABLE = "not_applicable"


class SupportLevel(str, Enum):
    L3 = "L3"
    L2 = "L2"
    L1 = "L1"
    L0 = "L0"


class RegimeState(str, Enum):
    LOCKED = "Locked"
    SWITCH_CANDIDATE = "SwitchCandidate"
    ACTIVE_NEW = "ActiveNew"
    OOD_HOLD = "OODHold"


ZONE_CONSENSUS_LABELS = {
    "sensor_localized_target",
    "sensor_localized_reference",
    "zone_coherent_process_shift",
    "bilateral_structural_shift",
    "parallel_shape_asymmetry",
    "spatially_consistent",
    "inconclusive",
    "not_evaluable",
}
