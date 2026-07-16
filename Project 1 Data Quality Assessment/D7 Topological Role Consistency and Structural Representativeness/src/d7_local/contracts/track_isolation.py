from __future__ import annotations

from pathlib import Path
from typing import Iterable


class TrackIsolationError(RuntimeError):
    pass


class TrackIsolationGuard:
    FORBIDDEN_TOKENS = (
        "d1_score",
        "d1_total",
        "d2_score",
        "d4_score",
        "d5_score",
        "d6_score",
        "d6_raw",
        "fault_probability",
        "cooldown",
    )

    def validate_input_schema(self, columns: Iterable[str]) -> None:
        offenders = [
            column
            for column in columns
            if any(token in str(column).lower() for token in self.FORBIDDEN_TOKENS)
        ]
        if offenders:
            raise TrackIsolationError(f"Forbidden upstream fields in d7_local: {offenders}")

    def validate_write_target(self, target: Path, local_root: Path) -> None:
        resolved_target = target.resolve()
        resolved_root = local_root.resolve()
        if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
            raise TrackIsolationError(f"d7_local cannot write outside {resolved_root}")

    def attest_manifest(self, manifest: dict[str, object]) -> None:
        if manifest.get("track_id") != "d7_local":
            raise TrackIsolationError("Local manifest must use track_id=d7_local")
        if manifest.get("upstream_score_consumed") is not False:
            raise TrackIsolationError("Local manifest must attest upstream_score_consumed=false")
