from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from prepare_sumo_inputs import (
    DO_ORP_SPECS,
    FLAG_EXTENDED_INTERPOLATED,
    FLAG_HAMPEL_CANDIDATE,
    FLAG_LONG_GAP,
    OUTPUT_DIR,
    PROCESS_SPECS,
    SOURCES,
)


HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(verify_hashes: bool = False) -> None:
    checks: dict[str, bool] = {}

    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)
        if not value:
            raise AssertionError(name)

    process_raw = pd.read_parquet(OUTPUT_DIR / "SUMO_process_inputs_1min_raw.parquet")
    process_clean = pd.read_parquet(OUTPUT_DIR / "SUMO_process_inputs_1min_clean.parquet")
    process_ready = pd.read_parquet(OUTPUT_DIR / "SUMO_process_inputs_1min_ready.parquet")
    sensor_raw = pd.read_parquet(OUTPUT_DIR / "SUMO_DO_ORP_1min_raw.parquet")
    sensor_clean = pd.read_parquet(OUTPUT_DIR / "SUMO_DO_ORP_1min_clean.parquet")
    sensor_ready = pd.read_parquet(OUTPUT_DIR / "SUMO_DO_ORP_1min_ready.parquet")
    flags = pd.read_parquet(OUTPUT_DIR / "SUMO_input_quality_flags_1min.parquet")

    check("process_timebase", process_raw.index.equals(process_clean.index) and process_raw.index.equals(process_ready.index))
    check("sensor_timebase", sensor_raw.index.equals(sensor_clean.index) and sensor_raw.index.equals(sensor_ready.index))
    check("process_ready_not_less_complete", bool((process_ready.notna().sum() >= process_clean.notna().sum()).all()))
    check("sensor_ready_not_less_complete", bool((sensor_ready.notna().sum() >= sensor_clean.notna().sum()).all()))
    check("process_ready_nonnegative", bool((process_ready.stack() >= 0).all()))
    check("DO_ready_nonnegative", bool((sensor_ready.filter(like="DO_").stack() >= 0).all()))
    check("signed_ORP_retained", bool((sensor_ready.filter(like="ORP_").min() < 0).all()))

    for spec in [*PROCESS_SPECS, *DO_ORP_SPECS]:
        if spec.near_zero_threshold is None:
            continue
        frame = sensor_ready if spec.canonical.startswith(("DO_", "ORP_")) else process_ready
        retained = frame[spec.canonical].dropna()
        check(
            f"near_zero_removed:{spec.canonical}",
            bool(retained.gt(spec.near_zero_threshold).all()),
        )

    check("effluent_ammonia_zero_retained", bool(process_ready["出水氨氮（mg/L）"].eq(0).any()))
    check("effluent_TP_zero_retained", bool(process_ready["出水总磷（mg/L）"].eq(0).any()))
    check("DO4_process_floor_retained", bool(sensor_ready[["DO_1_4（mg/L）", "DO_2_4（mg/L）"]].le(0.05).any().all()))

    process_flags = flags["process"]
    sensor_flags = flags["sensor"]
    for scope, clean, ready, scope_flags in [
        ("process", process_clean, process_ready, process_flags),
        ("sensor", sensor_clean, sensor_ready, sensor_flags),
    ]:
        unsigned = scope_flags.astype("uint16")
        extended = unsigned.apply(lambda column: (column & FLAG_EXTENDED_INTERPOLATED) != 0)
        long_gap = unsigned.apply(lambda column: (column & FLAG_LONG_GAP) != 0)
        candidate = unsigned.apply(lambda column: (column & FLAG_HAMPEL_CANDIDATE) != 0)
        check(f"{scope}_extended_starts_missing", bool(clean.where(extended).isna().all().all()))
        check(
            f"{scope}_extended_becomes_defined",
            int(ready.where(extended).notna().sum().sum()) == int(extended.sum().sum()),
        )
        check(f"{scope}_long_gap_remains_missing", bool(ready.where(long_gap).isna().all().all()))
        check(f"{scope}_hampel_candidates_recorded", int(candidate.sum().sum()) > 0)

    if verify_hashes:
        manifest = json.loads((OUTPUT_DIR / "SUMO_input_manifest.json").read_text(encoding="utf-8"))
        for name, path in SOURCES.items():
            check(f"input_hash:{name}", sha256(path) == manifest["input_sha256"][name])
        for name, digest in manifest["code_sha256"].items():
            check(f"code_hash:{name}", sha256(HERE / name) == digest)
        for name, digest in manifest["intermediate_sha256"].items():
            check(f"intermediate_hash:{name}", sha256(OUTPUT_DIR / "intermediate" / name) == digest)
        for name, metadata in manifest["final_outputs"].items():
            output = OUTPUT_DIR / name
            check(f"output_exists:{name}", output.exists())
            check(f"output_size:{name}", output.stat().st_size == metadata["bytes"])
            check(f"output_hash:{name}", sha256(output) == metadata["sha256"])

    result = {
        "contract": "SUMO-INPUT-V3.1-20260922",
        "checks": checks,
        "summary": {
            "process_clean_nonmissing": int(process_clean.notna().sum().sum()),
            "process_ready_nonmissing": int(process_ready.notna().sum().sum()),
            "sensor_clean_nonmissing": int(sensor_clean.notna().sum().sum()),
            "sensor_ready_nonmissing": int(sensor_ready.notna().sum().sum()),
            "ORP_negative_ready": int(sensor_ready.filter(like="ORP_").lt(0).sum().sum()),
            "DO4_near_zero_ready": int(sensor_ready[["DO_1_4（mg/L）", "DO_2_4（mg/L）"]].le(0.05).sum().sum()),
        },
    }
    if not verify_hashes:
        path = OUTPUT_DIR / "SUMO_cleaning_v2_QA.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"{len(checks)} cleaning-contract checks passed; frozen hashes checked: {verify_hashes}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-hashes", action="store_true")
    main(parser.parse_args().verify_hashes)
