"""Read-only raw input contract. Later values require a completed opening gate."""
from __future__ import annotations

import json

import pandas as pd

from runtime import HERE, OFFICIAL, OUTPUT, START, END, require_opening_gate, sha256


def load_raw(*, holdout=False):
    historical = pd.read_parquet(OFFICIAL / "1.1 Decomposition/outputs/parquet/time_base_1min_raw.parquet")
    if not holdout:
        if historical.index.max() >= START:
            raise ValueError("Historical source crosses holdout")
        return historical
    require_opening_gate(OUTPUT / "opening_gate.json")
    from opening_lock import verify_lock
    verify_lock(private_inputs=True)
    root = OFFICIAL / "1.1 Decomposition/Raw data/09_25.08.01-26.07.30_all data"
    matches = list(root.glob("*分钟数据*_02_shengwuchi.csv"))
    if len(matches) != 1 or sha256(matches[0]) != "18cb7f4617095655d1cb15a932621a5fbf58ac6b8b16a092e6586caba5aa4856":
        raise ValueError("Annual minute source identity mismatch")
    source = pd.read_csv(matches[0], encoding="utf-8-sig", low_memory=False)
    mapping = pd.read_csv(HERE / "intake_audit/channel_mapping.csv")
    source.index = pd.to_datetime(source.iloc[:, 0], errors="raise")
    source = source[mapping.source_column].rename(columns=dict(zip(mapping.source_column, mapping.canonical_id)))
    source = source.apply(pd.to_numeric, errors="raise")[historical.columns]
    if not source.index.is_unique:
        raise ValueError("Duplicate aligned timestamp")
    # Preserve every frozen old minute. Only append the newly received extension.
    extension = source.loc[(source.index > historical.index[-1]) & (source.index < END)]
    result = pd.concat([historical, extension])
    if not result.index.equals(pd.date_range(result.index[0], END-pd.Timedelta(minutes=1), freq="min")):
        raise ValueError("Unexpected raw clock or holdout endpoint")
    return result


def cache_folder(holdout):
    folder = HERE / ".local_qa" / ("holdout_T0" if holdout else "historical_e2e")
    folder.mkdir(parents=True, exist_ok=True)
    return folder
