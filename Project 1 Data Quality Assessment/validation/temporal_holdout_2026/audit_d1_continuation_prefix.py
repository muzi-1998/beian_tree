"""Exercise new-detector continuation after a simulated old-period cutover."""
from __future__ import annotations

import pandas as pd

from d1_frozen_adapter import FrozenD1
from inference_inputs import load_raw, cache_folder
from replay_d1_recovery import difference
from runtime import OUTPUT, write_json


def main():
    folder = cache_folder(False)
    raw = load_raw()
    processed, residual, innovation = [pd.read_parquet(folder / f"{key}.parquet")
                                      for key in ["processed", "residual", "innovation"]]
    engine = FrozenD1()
    kwargs = dict(journal_end="2026-01-31 23:00:00")
    full, full_evidence, _ = engine.predict(raw, processed, residual, innovation, **kwargs)
    cutoff = pd.Timestamp("2026-04-01")
    # Remove the unavailable final three preprocessing minutes at the prefix.
    raw_short = raw.loc[raw.index < cutoff]
    bound = cutoff-pd.Timedelta(minutes=3)
    short, short_evidence, _ = engine.predict(raw_short, processed.loc[processed.index < bound],
        residual.loc[residual.index < bound], innovation.loc[innovation.index < bound], **kwargs)
    rows = []
    for sensor, block in short.groupby("sensor_id"):
        block = block.set_index("timestamp").loc["2026-02-01":]
        expected = full.loc[full.sensor_id.eq(sensor)].set_index("timestamp").reindex(block.index)
        columns = [c for c in block if c not in {"sensor_id", "available_at", "source_window_end"}]
        changed, error = difference(block[columns], expected[columns])
        rows.append(dict(sensor_id=sensor, continuation_hours=len(block), changed_hours=changed, maximum_error=error))
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / "audit/D1_actual_detector_continuation_prefix.csv", index=False)
    write_json(OUTPUT / "audit/D1_actual_continuation_qa.json", dict(
        passed=bool(table.changed_hours.eq(0).all()), simulated_cutover="2026-02-01", prefix_end=str(cutoff),
        scope="new_raw_detector_path_plus_recovery_not_merely_archived_subscore_replay",
        no_new_period_values=True, n_compared_sensor_hours=int(table.continuation_hours.sum())))
    if table.changed_hours.sum():
        raise RuntimeError("Actual D1 continuation is not prefix invariant")


if __name__ == "__main__":
    main()
