"""run_d2_pipeline.py
D2 Temporal Continuity & Information Availability — V2 (single-plant)

Channels : 14 scored (DO_1_1..4, DO_2_1..4, ORP_1_1..3, ORP_2_1..3)
           4 support (QR/QIR — excluded from D2 main chain)
Main window : 24 h trailing, step 1 h → hourly output
Calibration : prespecified engineering mapping + development-only reference profile

V2 outputs (artifacts/data/):
  D2_main_scores_hourly.xlsx          – hourly Q_TI, Q_GS, Q_FA, D2_total, grade, usable_tag
  D2_preprocess_flags_hourly.xlsx     – hourly aggregated preprocess flags
  D2_gap_run_table.xlsx               – all gap events (start/end/duration/type/action)
  D2_freeze_availability_events.xlsx  – hard availability-loss events per channel
  D2_interpolation_ledger.xlsx        – imputed gap ledger (short gaps ≤ 5 min)
  D2_mapping_params.xlsx              – piecewise mapping parameters
  D2_sensor_availability_profile.xlsx – sensor-level long-term summary
  D2_timestamp_audit.xlsx             – timestamp alignment audit
  d2_calibration.yaml                 – calibration profile (auto-generated)

State: artifacts/d2_state.pkl
"""
from __future__ import annotations
import hashlib, json, sys, time, pickle, warnings, yaml
warnings.filterwarnings("ignore")
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

_ROOT = Path(__file__).parent
_D1   = _ROOT.parent / "D1 Sensor health"
_DECOMP = _ROOT.parent / "1.1 Decomposition"
CACHE = _ROOT / "cache"
ART   = _ROOT / "artifacts"
(CACHE).mkdir(exist_ok=True)
(ART / "data").mkdir(parents=True, exist_ok=True)
(ART / "figures").mkdir(parents=True, exist_ok=True)

# P2: load D2Config from YAML (configs/ lives next to this script)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from src.utils.config_loader import load_config as _load_d2_config
from src.d2_availability.scorer import (
    D2Aggregator, FreezeAvailabilityScorer, GapSeverityScorer,
    TemporalIntegrityScorer,
)
from src.d2_availability.process_floor import route_availability_evidence
_d2_cfg = _load_d2_config(_ROOT / "configs", version="v2")

# P2: channels sourced from d2_sensors.yaml
SCORED_CHANNELS  = _d2_cfg.scored_channels
SUPPORT_CHANNELS = _d2_cfg.support_channels
ALL_CHANNELS     = SCORED_CHANNELS + SUPPORT_CHANNELS

# Pool topology — P2: sourced from d2_sensors.yaml via D2Config
POOL_TOPOLOGY = {
    sid: {
        "pool":     s.pool,
        "type":     s.sensor_type,
        "inpool":   s.in_pool_neighbors,
        "parallel": s.parallel_to,
        "availability_mode": s.availability_mode,
        "process_zone": s.process_zone,
        "process_floor_threshold": s.process_floor_threshold,
        "response_loss_enabled": s.response_loss_enabled,
        "response_loss_production_enabled": (
            s.response_loss_enabled
            and bool(
                _d2_cfg.mapping.Q_FA_rule["aggravation"].get(
                    "production_enabled", False
                )
            )
        ),
        "response_loss_peers": s.response_loss_peers,
    }
    for sid, s in _d2_cfg.sensors.items()
    if sid in _d2_cfg.scored_channels
}

# Engineering-default thresholds — P2: sourced from d2_mapping.yaml via D2Config
_m = _d2_cfg.mapping
ENG_DEFAULTS = {
    "missing_rate_breaks":    _m.piecewise_breaks["Q_TI"]["missing_rate"],
    "irregular_rate_breaks":  _m.piecewise_breaks["Q_TI"]["irregular_rate"],
    "L_max_breaks_min":       _m.piecewise_breaks["Q_GS"]["L_max_min"],
    "gap_count_breaks":       _m.piecewise_breaks["Q_GS"]["gap_run_count"],
    "info_empty_breaks":      _m.piecewise_breaks["Q_FA"]["info_empty_cov"],
    "veto_Lmax_min":          _m.safety_floor["L_max_minutes"],
    "veto_missing_rate":      _m.safety_floor["missing_rate"],
    "veto_irregular_rate":    _m.safety_floor["irregular_rate"],
    # RLE thresholds (D2-lenient vs D1-strict)
    "tau_rle_D2_min":         _m.freeze_detection["tau_rle_D2_min"],
    "tau_rle_D1_min":         _m.freeze_detection["tau_rle_D1_min"],
    "tau_iqr_DO":             _m.freeze_detection["tau_iqr_DO"],
    "tau_iqr_ORP":            _m.freeze_detection["tau_iqr_ORP"],
    "precision_DO":           next(s.precision for s in _d2_cfg.sensors.values() if s.sensor_type == "DO"),
    "precision_ORP":          next(s.precision for s in _d2_cfg.sensors.values() if s.sensor_type == "ORP"),
    # Aggregation
    "w_QTI": _m.aggregation["weights"]["Q_TI"],
    "w_QGS": _m.aggregation["weights"]["Q_GS"],
    "w_QFA": _m.aggregation["weights"]["Q_FA"],
    "lambda_blend": _m.aggregation["lambda_blend"],
    # Short/long gap boundary
    "short_gap_max_min": _m.imputation["short_gap_max_min"],
    "long_gap_min_min":  _m.imputation["long_gap_min_min"],
}

CALIBRATION_ID = f"NorthBank_D2_v2_{datetime.now().strftime('%Y%m%d')}"
RUN_ID         = f"D2V2_{datetime.now().strftime('%Y%m%d_%H%M')}"
INPUT_PROVENANCE = {"source": "uninitialised"}
CACHE_KEY = "uninitialised"


# ─── Utilities ────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _sha256_paths(paths) -> str:
    h = hashlib.sha256()
    for path in sorted(map(Path, paths), key=lambda p: str(p)):
        h.update(str(path).encode("utf-8"))
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(block)
    return h.hexdigest()


def _cache_path(stem: str) -> Path:
    return CACHE / f"{stem}_{CACHE_KEY[:16]}.pkl"


def _source_temporal_integrity_rates() -> dict[str, float]:
    """Return source-file timestamp rates that have no channel-local location."""
    audit = INPUT_PROVENANCE.get("contract", {}).get("timestamp_audit", {})
    rows = sum(int(facts.get("rows", 0) or 0) for facts in audit.values())
    duplicate = sum(
        int(facts.get("duplicate_timestamp_rows", 0) or 0)
        for facts in audit.values()
    )
    out_of_order = sum(
        int(facts.get("out_of_order_transitions", 0) or 0)
        for facts in audit.values()
    )
    if rows <= 0:
        return {"duplicate_rate": 0.0, "out_of_order_rate": 0.0, "available": False}
    return {
        "duplicate_rate": duplicate / rows,
        "out_of_order_rate": out_of_order / max(rows - len(audit), 1),
        "available": True,
    }


def piecewise_score(x: pd.Series, breaks: list, reverse: bool = True) -> pd.Series:
    """Map a series to [1-5] using piecewise-linear function.

    breaks: 4 thresholds defining 5 zones.
    reverse=True: higher x → lower score (risk metric).
    """
    x = x.copy().fillna(x.median())
    score = pd.Series(np.nan, index=x.index, dtype=float)
    b0, b1, b2, b3 = breaks
    if reverse:
        score[x <= b0]              = 5.0
        score[(x > b0) & (x <= b1)] = 4.0 + (b1 - x[(x > b0) & (x <= b1)]) / (b1 - b0)
        score[(x > b1) & (x <= b2)] = 3.0 + (b2 - x[(x > b1) & (x <= b2)]) / (b2 - b1)
        score[(x > b2) & (x <= b3)] = 2.0 + (b3 - x[(x > b2) & (x <= b3)]) / (b3 - b2)
        score[x > b3]               = 1.0
    else:
        score[x >= b3]              = 5.0
        score[(x >= b2) & (x < b3)] = 4.0 + (x[(x >= b2) & (x < b3)] - b2) / (b3 - b2)
        score[(x >= b1) & (x < b2)] = 3.0 + (x[(x >= b1) & (x < b2)] - b1) / (b2 - b1)
        score[(x >= b0) & (x < b1)] = 2.0 + (x[(x >= b0) & (x < b1)] - b0) / (b1 - b0)
        score[x < b0]               = 1.0
    return score.clip(1.0, 5.0)


def consecutive_run_len(series: pd.Series) -> pd.Series:
    """Cumulative length of consecutive True/1 runs (resets to 0 at False/0)."""
    s = series.astype(int)
    groups = (s != s.shift()).cumsum()
    cum = s * (s.groupby(groups).cumcount() + 1)
    return cum.astype(float)


# ─── 1. Load raw Excel data ───────────────────────────────────────────────────

def load_raw_excel() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load D2 observations from the canonical 1.1 time-base contract.

    Direct Excel loading remains an explicit compatibility fallback.  D2 never
    consumes 1.1 innovations or D1 scores as availability evidence.
    """
    global INPUT_PROVENANCE, CACHE_KEY
    pq = _DECOMP / "outputs" / "parquet"
    contract_path = pq / "time_base_contract.json"
    if contract_path.exists():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract.get("schema_version") != "time-base-contract-v1":
            raise ValueError(f"Unsupported 1.1 time-base contract: {contract.get('schema_version')}")
        raw_path = pq / contract["raw_values_file"]
        flags_path = pq / contract["flags_file"]
        missing_files = [p for p in (raw_path, flags_path) if not p.exists()]
        if missing_files:
            raise FileNotFoundError(f"Incomplete 1.1 time-base contract: {missing_files}")
        df_aln = pd.read_parquet(raw_path)
        grid = pd.date_range(
            pd.Timestamp(_d2_cfg.time_grid["expected_start"]),
            pd.Timestamp(_d2_cfg.time_grid["expected_end"]),
            freq=_d2_cfg.time_grid["freq"],
        )
        df_aln = df_aln.reindex(grid)
        absent = sorted(set(ALL_CHANNELS) - set(df_aln.columns))
        if absent:
            raise ValueError(f"1.1 time base is missing D2 channels: {absent}")
        df_raw = df_aln.copy()
        hash_paths = [
            contract_path, raw_path, flags_path,
            _ROOT / "configs" / "d2_mapping.yaml",
            _ROOT / "configs" / "d2_sensors.yaml",
            _ROOT / "configs" / "d2_windows.yaml",
            _ROOT / "configs" / "d2_study_design.yaml",
            _ROOT / "src" / "d2_availability" / "process_floor.py",
            _ROOT / "src" / "d2_availability" / "scorer.py",
            _ROOT / "src" / "utils" / "config_loader.py",
            Path(__file__),
        ]
        CACHE_KEY = _sha256_paths(hash_paths)
        INPUT_PROVENANCE = {
            "source": "1.1_time_base_contract",
            "contract_path": str(contract_path),
            "contract": contract,
            "input_hash": CACHE_KEY,
        }
        log(f"[1] Loaded 1.1 canonical time base: {df_aln.shape}, hash={CACHE_KEY[:12]}")
        return df_raw, df_aln

    log("[1] 1.1 contract unavailable; loading legacy raw Excel sources")
    paths = [
        _ROOT / "beian_min_1_DO_25-08-26-04.xlsx",
        _ROOT / "beian_min_2_ORP-08-26-04.xlsx",
        _ROOT / "beian_min_3_QR+QIR-08-26-04.xlsx",
    ]
    do, orp, flw = [pd.read_excel(p, index_col=0, parse_dates=True) for p in paths]
    df_raw = do.join(orp, how="outer").join(flw, how="outer")
    df_raw.index = pd.to_datetime(df_raw.index)
    df_raw = df_raw.sort_index()
    grid = pd.date_range(pd.Timestamp(_d2_cfg.time_grid["expected_start"]),
                         pd.Timestamp(_d2_cfg.time_grid["expected_end"]),
                         freq=_d2_cfg.time_grid["freq"])
    df_aln = df_raw.reindex(grid)
    CACHE_KEY = _sha256_paths(paths + [
        _ROOT / "configs" / "d2_mapping.yaml",
        _ROOT / "configs" / "d2_sensors.yaml",
        _ROOT / "configs" / "d2_windows.yaml",
        _ROOT / "configs" / "d2_study_design.yaml",
        _ROOT / "src" / "d2_availability" / "process_floor.py",
        _ROOT / "src" / "d2_availability" / "scorer.py",
        _ROOT / "src" / "utils" / "config_loader.py",
        Path(__file__),
    ])
    INPUT_PROVENANCE = {"source": "legacy_excel_fallback", "input_hash": CACHE_KEY}
    return df_raw, df_aln


# ─── 2. Preprocess flags (minute-level) ──────────────────────────────────────

def compute_preprocess_flags(df_raw: pd.DataFrame, df_aln: pd.DataFrame) -> dict:
    """Return dict of {channel: flags_df} with minute-level boolean flags.

    Flags: present_raw, missing, duplicate, out_of_order, imputed, long_gap,
           info_empty, freeze_candidate, raw_value, aligned_value
    """
    cache_path = _cache_path("d2_flags_min")
    if cache_path.exists():
        log("[2] Loading preprocess flags from cache")
        with open(cache_path, "rb") as f: return pickle.load(f)

    log("[2] Computing minute-level preprocess flags...")
    t0 = time.time()

    flags_all = {}
    for ch in SCORED_CHANNELS:
        grid = df_aln.index
        s_type = "DO" if ch.startswith("DO") else "ORP"

        # ── present_raw / missing / duplicate
        present_raw = df_aln[ch].notna().astype(bool)
        missing     = ~present_raw
        duplicate   = pd.Series(False, index=grid, dtype=bool)

        # Source-order anomalies are retained in the 1.1 contract audit.  They
        # have no reliable minute location after canonical alignment.
        out_of_order = pd.Series(False, index=grid, dtype=bool)

        # ── irregular_interval (minutes where abs(interval) != 60s on grid)
        #    after alignment, consecutive present rows are always 60s apart
        #    irregular = rows directly after a missing-→-present transition
        was_missing  = missing.astype(int)
        gap_end_flag = (was_missing != was_missing.shift(1).fillna(0)).astype(bool) & ~missing
        irregular_interval = gap_end_flag  # transition from missing back to present

        # ── Short-gap imputation (≤ 5 min → linear interpolation)
        raw_vals = df_aln[ch].copy()
        groups = missing.ne(missing.shift(fill_value=False)).cumsum()
        run_size = missing.groupby(groups).transform("sum")
        short_gap_flag = missing & run_size.le(ENG_DEFAULTS["short_gap_max_min"])
        long_gap_flag  = missing & run_size.gt(ENG_DEFAULTS["short_gap_max_min"])

        # Interpolate short gaps
        imputed_vals = raw_vals.copy()
        imputed_vals[missing] = np.nan
        candidate = imputed_vals.interpolate(method="time", limit_area="inside")
        imputed_vals.loc[short_gap_flag] = candidate.loc[short_gap_flag]
        imputed_flag = short_gap_flag & imputed_vals.notna()

        # Route availability evidence by process semantics. Low IQR remains
        # diagnostic on process-floor channels and cannot trigger QFA Veto.
        filled = imputed_vals.fillna(imputed_vals.ffill().bfill())  # for metrics
        prec   = ENG_DEFAULTS[f"precision_{s_type}"]
        tau_iqr = ENG_DEFAULTS[f"tau_iqr_{s_type}"]
        tau_rle = ENG_DEFAULTS["tau_rle_D2_min"]

        # Criterion 1: RLE of near-identical values
        diff_abs     = (filled - filled.shift(1)).abs().fillna(prec + 1)
        is_same_val  = diff_abs < prec
        rle_same     = consecutive_run_len(is_same_val)
        observed_diff = (raw_vals - raw_vals.shift(1)).abs().fillna(prec + 1)
        same_observed = (
            observed_diff.lt(prec)
            & present_raw
            & present_raw.shift(1, fill_value=False)
        )
        hard_rle_same = consecutive_run_len(same_observed)
        # Criterion 2: Rolling IQR (30-min window)
        q75 = filled.rolling("30min", min_periods=15).quantile(0.75)
        q25 = filled.rolling("30min", min_periods=15).quantile(0.25)
        iqr_val  = (q75 - q25).fillna(tau_iqr + 1)
        sensor_meta = _d2_cfg.sensors[ch]
        availability = route_availability_evidence(
            aligned_value=imputed_vals,
            missing=missing,
            long_gap=long_gap_flag,
            rle_run_min=rle_same,
            hard_rle_run_min=hard_rle_same,
            rolling_iqr=iqr_val,
            low_iqr_threshold=tau_iqr,
            lenient_rle_min=tau_rle,
            hard_rle_min=ENG_DEFAULTS["tau_rle_D1_min"],
            availability_mode=sensor_meta.availability_mode,
            process_floor_threshold=sensor_meta.process_floor_threshold,
        )

        flags_all[ch] = pd.DataFrame({
            "present_raw":        present_raw.astype(np.int8),
            "missing":            missing.astype(np.int8),
            "duplicate":          duplicate.astype(np.int8),
            "out_of_order":       out_of_order.astype(np.int8),
            "irregular_interval": irregular_interval.astype(np.int8),
            "imputed":            imputed_flag.astype(np.int8),
            "long_gap":           long_gap_flag.astype(np.int8),
            # Backward-compatible alias used by event extraction.
            "info_empty":         availability["qfa_unavailable"].astype(np.int8),
            "qfa_unavailable":    availability["qfa_unavailable"].astype(np.int8),
            "low_iqr_diagnostic": availability["low_iqr_diagnostic"].astype(np.int8),
            "soft_rle_diagnostic": availability["soft_rle_diagnostic"].astype(np.int8),
            "soft_stasis":        availability["soft_stasis"].astype(np.int8),
            "floor_occupancy":    availability["floor_occupancy"].astype(np.int8),
            "resolution_limited": availability["resolution_limited"].astype(np.int8),
            "sensor_freeze":      availability["sensor_freeze"].astype(np.int8),
            "freeze_candidate":   availability["sensor_freeze"].astype(np.int8),
            "raw_value":          raw_vals,
            "aligned_value":      imputed_vals,
            "rle_run_min":        rle_same,
            "hard_rle_run_min":   hard_rle_same,
            "rolling_iqr":        iqr_val,
        })

    log(f"    [{time.time()-t0:.1f}s] Done. Channels: {len(flags_all)}")
    with open(cache_path, "wb") as f: pickle.dump(flags_all, f)
    return flags_all


# ─── 3. Gap run table ─────────────────────────────────────────────────────────

def compute_gap_runs(flags_all: dict) -> pd.DataFrame:
    """Build a channel-specific gap table from observed-value masks."""
    rows = []
    run_count = 0
    for ch in SCORED_CHANNELS:
        missing = flags_all[ch]["missing"].astype(bool)
        groups = missing.ne(missing.shift(fill_value=False)).cumsum()
        for _, segment in missing[missing].groupby(groups[missing]):
            start, end = segment.index[0], segment.index[-1]
            dur = int(len(segment))
            run_count += 1
            if dur <= ENG_DEFAULTS["short_gap_max_min"]:
                gtype, action = "short_gap", "linear_interp"
            elif dur <= 30:
                gtype, action = "medium_gap", "no_impute"
            elif dur <= 360:
                gtype, action = "long_gap", "no_impute"
            else:
                gtype, action = "critical_gap", "no_impute"
            rows.append({
                "gap_id": f"GAP_{run_count:05d}", "sensor_scope": ch,
                "start_ts": start, "end_ts": end, "duration_min": dur,
                "gap_type": gtype, "action_policy": action,
                "cross_hour": start.hour != end.hour,
                "cross_day": start.date() != end.date(),
                "veto_triggered": dur > ENG_DEFAULTS["veto_Lmax_min"],
            })

    return pd.DataFrame(rows)


# ─── 4. Interpolation ledger ──────────────────────────────────────────────────

def build_interpolation_ledger(flags_all: dict, gap_df: pd.DataFrame) -> pd.DataFrame:
    """Record each imputed gap segment across channels."""
    rows = []
    seg_id = 0
    for ch in SCORED_CHANNELS:
        fl = flags_all[ch]
        imputed = fl["imputed"].astype(bool)
        groups = imputed.ne(imputed.shift(fill_value=False)).cumsum()
        for _, segment in imputed[imputed].groupby(groups[imputed]):
            start, end = segment.index[0], segment.index[-1]
            dur = int(len(segment))
            seg_id += 1
            before = start - pd.Timedelta(minutes=1)
            after = end + pd.Timedelta(minutes=1)
            rows.append({
                "segment_id": f"IMP_{seg_id:05d}", "sensor_id": ch,
                "start_ts": start, "end_ts": end, "gap_duration_min": dur,
                "method": "linear",
                "boundary_value_start": fl["raw_value"].get(before, np.nan),
                "boundary_value_end": fl["raw_value"].get(after, np.nan),
                "max_allowed_downstream": "report" if dur <= 3 else "review_only",
                "usable_tag_impact": "none" if dur <= 3 else "minor",
            })

    return pd.DataFrame(rows)


# ─── 5. Window statistics (hourly, 24 h rolling) ─────────────────────────────

def compute_window_stats(flags_all: dict) -> dict:
    """Compute 24 h integrity/gap and configured 6 h QFA statistics.

    Returns dict[channel] = DataFrame (hourly index) with columns:
        missing_rate, duplicate_rate, out_of_order_rate, irregular_rate,
        L_max_min, gap_run_count, info_empty_cov, freeze_cand_cov
    """
    cache_path = _cache_path("d2_win_stats")
    if cache_path.exists():
        log("[5] Loading window stats from cache")
        with open(cache_path, "rb") as f: return pickle.load(f)

    log("[5] Computing 24 h integrity/gap and 6 h QFA statistics...")
    t0 = time.time()
    stats_all = {}
    W = _d2_cfg.main_window.length
    MP = int(pd.Timedelta(W) / pd.Timedelta(_d2_cfg.time_grid["freq"]))
    W_FA = _d2_cfg.freeze_window.length
    MP_FA = int(pd.Timedelta(W_FA) / pd.Timedelta(_d2_cfg.time_grid["freq"]))
    source_rates = _source_temporal_integrity_rates()

    for ch in SCORED_CHANNELS:
        fl = flags_all[ch]

        # Rolling means of binary flags
        miss_rate  = fl["missing"].rolling(W, min_periods=MP).mean()
        dup_rate   = pd.Series(source_rates["duplicate_rate"], index=fl.index)
        oor_rate   = pd.Series(source_rates["out_of_order_rate"], index=fl.index)
        irr_rate   = fl["irregular_interval"].rolling(W, min_periods=MP).mean()
        ie_cov = fl["qfa_unavailable"].rolling(W_FA, min_periods=MP_FA).mean()
        fc_cov = fl["sensor_freeze"].rolling(W_FA, min_periods=MP_FA).mean()
        low_iqr_cov = fl["low_iqr_diagnostic"].rolling(W_FA, min_periods=MP_FA).mean()
        soft_rle_cov = fl["soft_rle_diagnostic"].rolling(W_FA, min_periods=MP_FA).mean()
        soft_stasis_cov = fl["soft_stasis"].rolling(W_FA, min_periods=MP_FA).mean()
        floor_cov = fl["floor_occupancy"].rolling(W_FA, min_periods=MP_FA).mean()
        resolution_cov = fl["resolution_limited"].rolling(W_FA, min_periods=MP_FA).mean()

        # L_max: max consecutive missing run in 24 h window
        rle_missing = consecutive_run_len(fl["missing"].astype(bool))
        L_max_roll  = rle_missing.rolling(W, min_periods=MP).max()

        # Gap run count: starts of new gaps within window
        gap_start_flag = (fl["missing"].astype(int).diff() > 0).astype(float)
        gap_run_cnt    = gap_start_flag.rolling(W, min_periods=MP).sum()

        # Gap-run lengths are sampled only at run ends; quantiles over every
        # cumulative RLE point would over-weight long gaps.
        gap_end = fl["missing"].astype(bool) & ~fl["missing"].astype(bool).shift(-1, fill_value=False)
        completed_gap_len = rle_missing.where(gap_end)
        p95_gap = completed_gap_len.rolling(W, min_periods=1).quantile(0.95).fillna(0)

        # Resample to hourly (take end-of-hour value)
        hourly = pd.DataFrame({
            "missing_rate":    miss_rate,
            "duplicate_rate":  dup_rate,
            "out_of_order_rate": oor_rate,
            "irregular_rate":  irr_rate,
            "info_empty_cov":  ie_cov,
            "freeze_cand_cov": fc_cov,
            "sensor_freeze_cov": fc_cov,
            "low_iqr_cov":     low_iqr_cov,
            "soft_rle_cov":    soft_rle_cov,
            "soft_stasis_cov": soft_stasis_cov,
            "floor_occupancy": floor_cov,
            "resolution_limited": resolution_cov,
            "L_max_min":       L_max_roll,
            "gap_run_count":   gap_run_cnt,
            "P95_gap_min":     p95_gap,
        }).resample("1h").last()

        stats_all[ch] = hourly.dropna(subset=["missing_rate"])

    log(f"    [{time.time()-t0:.1f}s] Done. Shape per channel: {list(stats_all.values())[0].shape}")
    with open(cache_path, "wb") as f: pickle.dump(stats_all, f)
    return stats_all


# ─── 6. Response-loss (Tier 1, V1) ───────────────────────────────────────────

def compute_response_loss_tier1(flags_all: dict, calib: dict) -> dict:
    """V1: Tier 1 response_loss (in-pool neighbors only).

    For each 30-min sub-window of the hourly output:
      var_ref  = mean variance of Tier-1 neighbors in sub-window
      var_tgt  = variance of target in sub-window
      response_loss(sw) = 1 if var_ref > bench_P50 AND var_tgt < bench_P5

    Returns dict[channel] = hourly Series of response_loss_rate.
    """
    cache_path = _cache_path(f"d2_response_loss_{calib.get('calibration_id', 'unknown')}")
    if cache_path.exists():
        log("[6] Loading response_loss from cache")
        with open(cache_path, "rb") as f: return pickle.load(f)

    log("[6] Computing topology-qualified response_loss (30-min sub-windows)...")
    t0 = time.time()
    rl_all = {}

    for ch in SCORED_CHANNELS:
        sensor_meta = _d2_cfg.sensors[ch]
        if not sensor_meta.response_loss_enabled:
            idx = flags_all[ch].index
            rl_all[ch] = pd.Series(0.0, index=idx).resample("1h").last().rename(ch)
            continue
        s_type = POOL_TOPOLOGY[ch]["type"]
        bench_var_P50 = calib["bench_var_P50"].get(ch, calib["bench_var_P50_default"].get(s_type, 0.01))
        bench_var_P05 = calib["bench_var_P05"].get(ch, calib["bench_var_P05_default"].get(s_type, 0.0005))

        tgt   = flags_all[ch]["aligned_value"]
        peers = sensor_meta.response_loss_peers
        refs  = pd.concat([flags_all[p]["aligned_value"]
                           for p in peers if p in flags_all], axis=1)

        # 30-min rolling variance
        var_tgt = tgt.rolling("30min", min_periods=15).var().fillna(bench_var_P50)
        var_ref = refs.rolling("30min", min_periods=15).var().mean(axis=1).fillna(bench_var_P50)

        rl_flag = ((var_ref > bench_var_P50) & (var_tgt < bench_var_P05)).astype(float)
        rl_rate = rl_flag.rolling("1h", min_periods=30).mean().resample("1h").last()
        rl_all[ch] = rl_rate.rename(ch)

    log(f"    [{time.time()-t0:.1f}s] Done")
    with open(cache_path, "wb") as f: pickle.dump(rl_all, f)
    return rl_all


# ─── 7. Calibration profile ───────────────────────────────────────────────────

def load_or_generate_calibration(stats_all: dict, flags_all: dict) -> dict:
    """Load or generate a D2-internal calibration profile.

    D1 is reserved for external event concordance and is never used to fit D2
    mappings or veto thresholds.
    """
    calib_yaml = _ROOT / "d2_calibration.yaml"
    if calib_yaml.exists():
        with open(calib_yaml, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        if (loaded.get("calibration_basis") == "blocked_development_reference_v2" and
                loaded.get("mapping_version") == _d2_cfg.mapping.mapping_version and
                loaded.get("study_design_version") == _d2_cfg.study_design.version and
                loaded.get("input_hash") == INPUT_PROVENANCE.get("input_hash")):
            log("[7] Loading frozen development-only D2 reference profile")
            return loaded
        log("[7] Existing calibration predates the 1.1→D2 contract; regenerating")

    log("[7] Generating D2-internal calibration profile...")
    calib = {"calibration_id": CALIBRATION_ID, "plant_id": "NorthBank_LCH",
             "generated_date": datetime.now().strftime("%Y-%m-%d"),
             "effective_period": ["2025-08-01", "2026-04-13"],
             "calibration_basis": "blocked_development_reference_v2",
             "study_design_version": _d2_cfg.study_design.version,
             "mapping_version": _d2_cfg.mapping.mapping_version,
             "input_hash": INPUT_PROVENANCE.get("input_hash")}
    development = _d2_cfg.study_design.periods["development"]
    validation = _d2_cfg.study_design.periods["internal_validation"]
    terminal = _d2_cfg.study_design.periods["terminal_test"]
    bench_stats = {
        ch: frame.loc[pd.Timestamp(development.start):pd.Timestamp(development.end)].copy()
        for ch, frame in stats_all.items()
    }
    n_bench = min(len(frame) for frame in bench_stats.values())

    # Compute thresholds from benchmark stats (or fall back to engineering defaults)
    def get_percentiles(col, channels):
        vals = []
        for ch in channels:
            if ch in bench_stats and col in bench_stats[ch].columns:
                vals.extend(bench_stats[ch][col].dropna().tolist())
        if len(vals) < 10:
            return None
        vals = np.array(vals)
        return {q: float(np.percentile(vals, q*100))
                for q in [0.25, 0.50, 0.75, 0.95, 0.99]}

    def safe_pct(col, channels, fallback):
        p = get_percentiles(col, channels)
        return p if p is not None else fallback

    calib["benchmark_windows"] = {
        "selection_rule": "blocked_development_period_only; D1_not_used",
        "fit_start": development.start,
        "fit_end": development.end,
        "total_benchmark_hours": int(n_bench),
        "total_reference_sensor_hours": int(sum(len(frame) for frame in bench_stats.values())),
    }
    calib["validation_periods"] = {
        "internal_validation": {"start": validation.start, "end": validation.end},
        "terminal_test": {"start": terminal.start, "end": terminal.end},
        "external_site_validation": _d2_cfg.study_design.external_site_validation,
    }
    calib["mapping_contract"] = {
        "source": "configs/d2_mapping.yaml",
        "fitted_from_observations": False,
        "status": "prespecified_engineering_contract",
    }
    calib["descriptive_reference_percentiles"] = {
        "Q_temporal_integrity": {
            "missing_rate":    safe_pct("missing_rate",   SCORED_CHANNELS,
                                        {0.25: 0.001, 0.50: 0.003, 0.75: 0.008, 0.95: 0.02, 0.99: 0.05}),
            "duplicate_rate":  {0.25: 0.0, 0.50: 0.0, 0.75: 0.0, 0.95: 0.0, 0.99: 0.001},
            "out_of_order_rate": {0.25: 0.0, 0.50: 0.0, 0.75: 0.0, 0.95: 0.001, 0.99: 0.005},
            "irregular_rate":  safe_pct("irregular_rate", SCORED_CHANNELS,
                                        {0.25: 0.0, 0.50: 0.0, 0.75: 0.001, 0.95: 0.002, 0.99: 0.005}),
        },
        "Q_gap_severity": {
            "L_max_minutes":  safe_pct("L_max_min",    SCORED_CHANNELS,
                                       {0.25: 0, 0.50: 1, 0.75: 2, 0.95: 5, 0.99: 30}),
            "gap_run_count":  safe_pct("gap_run_count", SCORED_CHANNELS,
                                       {0.25: 0, 0.50: 0, 0.75: 1, 0.95: 3, 0.99: 8}),
        },
        "Q_freeze_avail": {
            "info_empty_cov": safe_pct("info_empty_cov", SCORED_CHANNELS,
                                       {0.25: 0.01, 0.50: 0.03, 0.75: 0.08, 0.95: 0.15, 0.99: 0.30}),
            "tau_rle_D2_min":  ENG_DEFAULTS["tau_rle_D2_min"],
            "tau_iqr_DO":      ENG_DEFAULTS["tau_iqr_DO"],
            "tau_iqr_ORP":     ENG_DEFAULTS["tau_iqr_ORP"],
        },
    }
    # Veto thresholds are prespecified engineering limits, not fitted quantiles.
    def _apply_floor(bench_p, floor):
        bench_p = float(bench_p) if bench_p is not None else 0.0
        if bench_p <= 0 or bench_p < floor:
            return {"value": floor, "source": "floor_applied",
                    "bench_p": bench_p, "engineering_floor": floor}
        return {"value": bench_p, "source": "benchmark",
                "bench_p": bench_p, "engineering_floor": floor}

    calib["veto_thresholds"] = {
        "L_max_minutes":  {"value": 360, "source": "prespecified_engineering", "engineering_floor": 360},
        "missing_rate":   {"value": 0.15, "source": "prespecified_engineering", "engineering_floor": 0.15},
        "irregular_rate": {"value": 0.10, "source": "prespecified_engineering", "engineering_floor": 0.10},
    }

    # Variance benchmarks for response_loss (sensor-type level)
    bench_var = {"DO": {}, "ORP": {}}
    for ch in SCORED_CHANNELS:
        s_type = POOL_TOPOLOGY[ch]["type"]
        if ch in flags_all:
            fit_start = pd.Timestamp(development.start)
            fit_end = pd.Timestamp(development.end)
            all_vals = flags_all[ch]["aligned_value"].loc[fit_start:fit_end].dropna()
            if len(all_vals) > 1440:
                var_series = all_vals.rolling(30).var().dropna()
                bench_var[s_type][ch] = {
                    "P05": float(var_series.quantile(0.05)),
                    "P50": float(var_series.quantile(0.50)),
                }
    calib["bench_var"] = bench_var

    calib["tier_availability"] = {}
    for ch, topo in POOL_TOPOLOGY.items():
        sensor_meta = _d2_cfg.sensors[ch]
        tier1 = sensor_meta.response_loss_peers
        calib["tier_availability"][ch] = {
            "tier1": tier1 if sensor_meta.response_loss_enabled else [],
            "tier2": [],
            "tier3": [],
            "tier4": {"allowed": False, "reason": "QR_QIR_quality_unverified"},
            "response_loss_diagnostic_eligible": sensor_meta.response_loss_enabled,
            "response_loss_production_enabled": POOL_TOPOLOGY[ch][
                "response_loss_production_enabled"
            ],
            "availability_mode": sensor_meta.availability_mode,
            "peer_qualification": "same_variable_same_process_position_parallel_pool",
        }
    calib["topology"] = {
        "pools": [1, 2], "has_parallel_pools": True,
        "sensor_count_per_pool": {"DO": 4, "ORP": 3},
    }

    with open(calib_yaml, "w", encoding="utf-8") as f:
        yaml.dump(calib, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    log(f"    Saved {calib_yaml}")
    return calib


def _calib_veto(calib: dict, key: str, default: float) -> float:
    # P0-A: handle both dict (P0-B structure) and raw float; 0 is degenerate
    raw = calib.get("veto_thresholds", {}).get(key)
    if isinstance(raw, dict):
        return float(raw.get("value", default))
    if raw is None or float(raw) <= 0:
        return float(default)
    return float(raw)


def _build_bench_var_lookup(calib: dict) -> tuple[dict, dict, dict, dict]:
    """Extract per-channel and per-type variance benchmarks from calibration."""
    bv = calib.get("bench_var", {})
    p50_ch, p05_ch = {}, {}
    for s_type, ch_dict in bv.items():
        for ch, vals in ch_dict.items():
            p50_ch[ch] = vals.get("P50", 0.01)
            p05_ch[ch] = vals.get("P05", 0.001)
    p50_default = {"DO": 0.01, "ORP": 2.0}
    p05_default = {"DO": 0.001, "ORP": 0.05}
    return p50_ch, p05_ch, p50_default, p05_default


# ─── 8. Sub-score computation ─────────────────────────────────────────────────

def compute_subscores(stats_all: dict, rl_all: dict, calib: dict) -> dict:
    """Map window stats → Q_TI, Q_GS, Q_FA (hourly, per channel).

    Returns dict[channel] = DataFrame with Q_TI, Q_GS, Q_FA and raw stats.
    """
    log("[8] Computing Q_TI, Q_GS, Q_FA...")
    subs_all = {}

    ti_scorer = TemporalIntegrityScorer(_d2_cfg)
    gs_scorer = GapSeverityScorer(_d2_cfg)
    fa_scorer = FreezeAvailabilityScorer(_d2_cfg)

    for ch in SCORED_CHANNELS:
        st = stats_all[ch].copy()
        rl = rl_all.get(ch, pd.Series(0.0, index=st.index))

        Q_TI = ti_scorer.score(st)
        Q_GS = gs_scorer.score(st)
        sensor_meta = _d2_cfg.sensors[ch]
        Q_FA, Q_main = fa_scorer.score(
            st,
            rl,
            allow_response_loss=sensor_meta.response_loss_enabled,
        )
        rl_aligned = rl.reindex(st.index).fillna(0.0)
        Q_miss = piecewise_score(st["missing_rate"], _d2_cfg.mapping.piecewise_breaks["Q_TI"]["missing_rate"])
        Q_lmax = piecewise_score(st["L_max_min"], _d2_cfg.mapping.piecewise_breaks["Q_GS"]["L_max_min"])

        subs_all[ch] = pd.DataFrame({
            "Q_TI":          Q_TI,
            "Q_GS":          Q_GS,
            "Q_FA":          Q_FA,
            "Q_miss_comp":   Q_miss,
            "Q_lmax_comp":   Q_lmax,
            "Q_main_FA":     Q_main,
            "rl_rate":       rl_aligned,
            "missing_rate":  st["missing_rate"],
            "duplicate_rate": st["duplicate_rate"],
            "out_of_order_rate": st["out_of_order_rate"],
            "irregular_rate": st["irregular_rate"],
            "L_max_min":     st["L_max_min"],
            "P95_gap_min":   st["P95_gap_min"],
            "gap_run_count": st["gap_run_count"],
            "info_empty_cov": st["info_empty_cov"],
            "freeze_cand_cov": st["freeze_cand_cov"],
            "sensor_freeze_cov": st["sensor_freeze_cov"],
            "low_iqr_cov": st["low_iqr_cov"],
            "soft_rle_cov": st.get(
                "soft_rle_cov", pd.Series(0.0, index=st.index)
            ),
            "soft_stasis_cov": st.get(
                "soft_stasis_cov", pd.Series(0.0, index=st.index)
            ),
            "floor_occupancy": st["floor_occupancy"],
            "resolution_limited": st["resolution_limited"],
        })

    log("    Sub-scores computed.")
    return subs_all


# ─── 9. D2 aggregation + veto ─────────────────────────────────────────────────

def aggregate_d2(subs_all: dict, calib: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate Q_TI, Q_GS, Q_FA → D2_total with veto rules.

    Returns (scores_df, veto_log_df) — both hourly, multi-channel.
    """
    log("[9] D2 aggregation + veto rules...")
    aggregator = D2Aggregator(_d2_cfg, calib)
    all_D2, all_veto = {}, {}
    for ch in SCORED_CHANNELS:
        s = subs_all[ch]
        scored = aggregator.aggregate(s["Q_TI"], s["Q_GS"], s["Q_FA"], s)
        D2_total = scored["D2_total"]
        veto_flag = scored["veto_flag"].astype(bool)

        # Grade & usable_tag
        def assign_grade(d):
            if d >= 4.5: return "A"
            if d >= 3.5: return "B"
            if d >= 2.5: return "C"
            if d >= 1.5: return "D"
            return "E"

        def assign_usable(d, vf, ice):
            if vf and d < 2.0: return "invalid"
            if vf: return "review_only"
            if ice > 0.20: return "report_only"
            return "train_ok"

        grade     = D2_total.map(assign_grade)
        usable_tag = pd.Series([assign_usable(d, vf, ice)
                                 for d, vf, ice in zip(D2_total, veto_flag, s["info_empty_cov"])],
                                index=D2_total.index)

        # Dominant limitation
        component_scores = s[["Q_TI", "Q_GS", "Q_FA"]]
        dom = component_scores.idxmin(axis=1).map({
            "Q_TI": "temporal_integrity", "Q_GS": "gap_severity",
            "Q_FA": "freeze_availability",
        })
        dom[component_scores.min(axis=1) >= 4.5] = "ok"

        all_D2[ch] = pd.DataFrame({
            "Q_TI":            scored["Q_TI"],
            "Q_GS":            scored["Q_GS"],
            "Q_FA":            scored["Q_FA"],
            "D2_base":         scored["D2_base"],
            "D2_pre":          scored["D2_pre"],
            "D2_total":        D2_total,
            "grade":           grade,
            "usable_tag":      usable_tag,
            "veto_flag":       veto_flag.astype(int),
            "veto_reason":     scored["veto_reason"],
            "dominant_limitation": dom,
        })
        all_veto[ch] = veto_flag

    log("    Aggregation done.")
    return all_D2, all_veto


def ie_breaks_ref():
    return ENG_DEFAULTS["info_empty_breaks"][1]   # 8% threshold for "concern"


# ─── 10. Freeze availability events ───────────────────────────────────────────

def extract_freeze_events(
    flags_all: dict,
    subs_all: dict,
    *,
    calibration_id: str | None = None,
) -> pd.DataFrame:
    """Extract production hard-availability events with descriptive D1 linkage."""
    # P1-C: load D1 event index (non-blocking)
    d1_events = None
    for p in [_D1 / "outputs" / "data" / "D1_event_windows.xlsx",
              _D1 / "artifacts" / "data" / "D1_event_windows.xlsx",
              _D1 / "D1_event_windows.xlsx"]:
        if p.exists():
            d1_events = pd.read_excel(p, sheet_name="all_events")
            d1_events = d1_events.rename(columns={
                "start": "start_ts", "end": "end_ts",
                "dominant_fault": "fault_type",
            })
            required = {"sensor_id", "start_ts", "end_ts"}
            if not required.issubset(d1_events.columns):
                log(f"    [P1-C] Ignoring incompatible D1 event schema: {p.name}")
                d1_events = None
                continue
            if "event_id" not in d1_events:
                d1_events.insert(0, "event_id", [f"D1E_{i:05d}" for i in range(1, len(d1_events) + 1)])
            d1_events["start_ts"] = pd.to_datetime(d1_events["start_ts"])
            d1_events["end_ts"]   = pd.to_datetime(d1_events["end_ts"])
            log(f"    [P1-C] Loaded D1 event index: {len(d1_events)} events")
            break
    if d1_events is None:
        log("    [P1-C] D1 event index unavailable; relation_to_D1='no_d1_index'")

    def _link_d1(ev_start, ev_end, ch):
        if d1_events is None or len(d1_events) == 0:
            return None, None, "no_d1_index"
        e = d1_events[d1_events["sensor_id"] == ch]
        # P1-C 修订：不按 fault_type 筛选，链接任意 D1 异常事件；
        # fault_type 作为描述性元数据记录（D1 当时检测到什么故障类型）。
        if len(e) == 0:
            return None, None, "d2_only"
        ov = e[(e["end_ts"] >= ev_start) & (e["start_ts"] <= ev_end)]
        if len(ov) == 0:
            return None, None, "d2_only"
        best = ov.assign(_d=(ov["end_ts"] - ov["start_ts"]).dt.total_seconds()) \
                 .sort_values("_d", ascending=False).iloc[0]
        d1_s, d1_e = best["start_ts"], best["end_ts"]
        if ev_start >= d1_s and ev_end <= d1_e:
            rel = "subset"
        elif ev_start <= d1_s and ev_end >= d1_e:
            rel = "superset"
        else:
            rel = "overlap"
        d1_ftype = str(best["fault_type"]) if "fault_type" in best.index else "unknown"
        return best["event_id"], d1_ftype, rel

    rows = []
    ev_id = 0
    for ch in SCORED_CHANNELS:
        fl = flags_all[ch]
        ie = fl["qfa_unavailable"].astype(bool)
        in_ev = False
        ev_start = None
        for ts, val in ie.items():
            if val and not in_ev:
                in_ev    = True
                ev_start = ts
            elif not val and in_ev:
                in_ev = False
                dur   = int((ts - ev_start).total_seconds() // 60)
                if dur >= 10:
                    ev_id += 1
                    h_start = ev_start.floor("h")
                    h_end   = ts.ceil("h")
                    sub_win = subs_all[ch].loc[h_start:h_end] if ch in subs_all else pd.DataFrame()
                    ie_cov  = float(sub_win["info_empty_cov"].mean()) if len(sub_win) else np.nan
                    rl_rate = float(sub_win["rl_rate"].mean())         if len(sub_win) else np.nan
                    q_main  = float(sub_win["Q_main_FA"].mean())       if len(sub_win) else np.nan
                    q_final = float(sub_win["Q_FA"].mean())            if len(sub_win) else np.nan
                    rle_col = "hard_rle_run_min" if POOL_TOPOLOGY[ch]["availability_mode"] == "process_floor" else "rle_run_min"
                    rle_max = float(fl[rle_col].loc[ev_start:ts].max())
                    event_slice = fl.loc[ev_start:ts]
                    if event_slice["long_gap"].astype(bool).any():
                        event_type = "long_gap"
                    elif event_slice["missing"].astype(bool).any():
                        event_type = "missing"
                    else:
                        event_type = "hard_observed_stasis"
                    d1_id, d1_ftype, rel = _link_d1(ev_start, ts, ch)
                    rows.append({
                        "event_id":               f"FAE_{ev_id:04d}",
                        "event_type":             event_type,
                        "evidence_class":          "production_hard_availability",
                        "sensor_id":              ch,
                        "start_ts":               ev_start,
                        "end_ts":                 ts,
                        "duration_min":           dur,
                        "info_empty_coverage":    ie_cov,
                        "rle_max_min":            rle_max,
                        "response_loss_rate":     rl_rate,
                        "response_loss_tier_used": 1 if POOL_TOPOLOGY[ch]["response_loss_production_enabled"] else 0,
                        "response_loss_diagnostic_available": 1 if POOL_TOPOLOGY[ch]["response_loss_enabled"] else 0,
                        "Q_main_before_agg":      q_main,
                        "Q_freeze_avail_final":   q_final,
                        "linked_D1_event_id":     d1_id,    # P1-C
                        "linked_D1_fault_type":   d1_ftype, # P1-C 修订：D1 故障类型
                        "relation_to_D1":         rel,      # P1-C
                        "review_priority":        "high" if dur > 120 else "medium",
                        "calibration_id":         calibration_id or CALIBRATION_ID,
                    })
    return pd.DataFrame(rows)


# ─── 11. Timestamp audit ──────────────────────────────────────────────────────

def build_timestamp_audit(df_raw: pd.DataFrame, df_aln: pd.DataFrame) -> pd.DataFrame:
    """Record timestamp alignment facts."""
    raw_diffs = df_raw.index.to_series().diff().dt.total_seconds()
    unusual   = raw_diffs[(raw_diffs != 60) & raw_diffs.notna()]
    rows = []
    for ts, diff in unusual.items():
        rows.append({
            "ts_raw":         ts,
            "interval_sec":   diff,
            "expected_sec":   60,
            "deviation_sec":  diff - 60,
            "gap_min":        (diff - 60) / 60,
            "action":         "aligned_to_grid" if diff > 60 else "interval_compressed",
            "aligned_ts":     ts.floor("min"),
        })
    audit_df = pd.DataFrame(rows)
    summary_rows = [
        ("input_source", INPUT_PROVENANCE.get("source")),
        ("grid_rows", len(df_aln)),
        ("grid_start", df_aln.index.min()),
        ("grid_end", df_aln.index.max()),
        ("duplicate_after_canonicalisation", int(df_raw.index.duplicated().sum())),
        ("intervals_ne_60s_after_canonicalisation", len(unusual)),
    ]
    contract = INPUT_PROVENANCE.get("contract", {})
    for source, facts in contract.get("timestamp_audit", {}).items():
        for key in ("rows", "invalid_timestamp_rows", "duplicate_timestamp_rows",
                    "out_of_order_transitions", "timestamp_min", "timestamp_max"):
            summary_rows.append((f"source_{source}_{key}", facts.get(key)))
    for ch in SCORED_CHANNELS:
        summary_rows.append((f"missing_cells_{ch}", int(df_aln[ch].isna().sum())))
    summary = pd.DataFrame(summary_rows, columns=["metric", "value"])
    return audit_df, summary


# ─── 12. Sensor availability profile ──────────────────────────────────────────

def build_sensor_profile(all_D2: dict, subs_all: dict) -> pd.DataFrame:
    rows = []
    for ch in SCORED_CHANNELS:
        d2   = all_D2[ch]["D2_total"]
        sub  = subs_all[ch]
        rows.append({
            "sensor_id":              ch,
            "pool_id":                POOL_TOPOLOGY[ch]["pool"],
            "sensor_type":            POOL_TOPOLOGY[ch]["type"],
            "process_zone":           POOL_TOPOLOGY[ch]["process_zone"],
            "availability_mode":      POOL_TOPOLOGY[ch]["availability_mode"],
            "process_floor_threshold": POOL_TOPOLOGY[ch]["process_floor_threshold"],
            "response_loss_diagnostic_eligible": POOL_TOPOLOGY[ch]["response_loss_enabled"],
            "response_loss_production_enabled": POOL_TOPOLOGY[ch]["response_loss_production_enabled"],
            "mean_D2":                float(d2.mean()),
            "median_D2":              float(d2.median()),
            "p05_D2":                 float(d2.quantile(0.05)),
            "p25_D2":                 float(d2.quantile(0.25)),
            "p75_D2":                 float(d2.quantile(0.75)),
            "p95_D2":                 float(d2.quantile(0.95)),
            "low_score_rate_lt3":     float((d2 < 3.0).mean()),
            "low_score_rate_lt2":     float((d2 < 2.0).mean()),
            "mean_Q_TI":              float(sub["Q_TI"].mean()),
            "mean_Q_GS":              float(sub["Q_GS"].mean()),
            "mean_Q_FA":              float(sub["Q_FA"].mean()),
            "mean_missing_rate":      float(sub["missing_rate"].mean()),
            "mean_info_empty_cov":    float(sub["info_empty_cov"].mean()),
            "mean_floor_occupancy":   float(sub["floor_occupancy"].mean()),
            "mean_resolution_limited": float(sub["resolution_limited"].mean()),
            "mean_sensor_freeze_cov": float(sub["sensor_freeze_cov"].mean()),
            "mean_low_iqr_cov":       float(sub["low_iqr_cov"].mean()),
            "mean_soft_rle_cov":      float(sub["soft_rle_cov"].mean()),
            "mean_soft_stasis_cov":   float(sub["soft_stasis_cov"].mean()),
            "max_L_max_min":          float(sub["L_max_min"].max()),
            "veto_rate":              float(all_D2[ch]["veto_flag"].mean()),
            "grade_A_rate":           float((all_D2[ch]["grade"] == "A").mean()),
            "grade_B_rate":           float((all_D2[ch]["grade"] == "B").mean()),
            "grade_C_rate":           float((all_D2[ch]["grade"] == "C").mean()),
            "grade_D_E_rate":         float((all_D2[ch]["grade"].isin(["D", "E"])).mean()),
            "response_loss_diagnostic": 1 if POOL_TOPOLOGY[ch]["response_loss_enabled"] else 0,
            "calibration_id":         CALIBRATION_ID,
        })
    return pd.DataFrame(rows).sort_values("mean_D2", ascending=False)


# ─── 13. Mapping params ───────────────────────────────────────────────────────

def build_mapping_params(calib: dict) -> pd.DataFrame:
    records = []
    cfg_breaks = _d2_cfg.mapping.piecewise_breaks
    entries = [
        ("Q_TI", metric, breaks, "d2_mapping.yaml")
        for metric, breaks in cfg_breaks["Q_TI"].items()
    ] + [
        ("Q_GS", metric, breaks, "d2_mapping.yaml")
        for metric, breaks in cfg_breaks["Q_GS"].items()
    ] + [
        ("Q_FA", metric, breaks, "d2_mapping.yaml")
        for metric, breaks in cfg_breaks["Q_FA"].items()
    ]
    for subscore, metric, breaks, src in entries:
        records.append({
            "mapping_id":         f"{subscore}_{metric}",
            "subscore_name":      subscore,
            "input_metric":       metric,
            "mapping_type":       "piecewise_linear",
            "break_1":            breaks[0],
            "break_2":            breaks[1],
            "break_3":            breaks[2],
            "break_4":            breaks[3],
            "score_zone_1_to_2":  f">{breaks[3]}",
            "score_zone_2_to_3":  f"{breaks[2]}-{breaks[3]}",
            "score_zone_3_to_4":  f"{breaks[1]}-{breaks[2]}",
            "score_zone_4_to_5":  f"≤{breaks[0]}",
            "calibration_source": src,
            "mapping_version":    _d2_cfg.mapping.mapping_version,
            "calibration_id":     calib.get("calibration_id", CALIBRATION_ID),
            "effective_date":     datetime.now().strftime("%Y-%m-%d"),
        })
    floor_policy = _d2_cfg.mapping.process_floor_policy
    for ch in SCORED_CHANNELS:
        sensor = _d2_cfg.sensors[ch]
        if sensor.availability_mode != "process_floor":
            continue
        records.append({
            "mapping_id": f"Q_FA_{ch}_process_floor",
            "subscore_name": "Q_FA",
            "input_metric": "qfa_unavailable",
            "mapping_type": "process_floor_route",
            "break_1": None,
            "break_2": None,
            "break_3": None,
            "break_4": None,
            "score_zone_1_to_2": None,
            "score_zone_2_to_3": None,
            "score_zone_3_to_4": None,
            "score_zone_4_to_5": None,
            "calibration_source": "d2_sensors.yaml+d2_mapping.yaml",
            "mapping_version": _d2_cfg.mapping.mapping_version,
            "calibration_id": calib.get("calibration_id", CALIBRATION_ID),
            "effective_date": datetime.now().strftime("%Y-%m-%d"),
            "sensor_id": ch,
            "qfa_window": _d2_cfg.freeze_window.length,
            "production_evidence": ",".join(floor_policy["production_evidence"]),
            "process_floor_threshold": sensor.process_floor_threshold,
            "response_loss_enabled": sensor.response_loss_enabled,
        })
    return pd.DataFrame(records)


# ─── 14. Export outputs ───────────────────────────────────────────────────────

def export_outputs(all_D2, subs_all, gap_df, freeze_events, ledger_df,
                   audit_df, audit_summary, profile_df, mapping_df, calib,
                   audit_log_df=None):
    log("[14] Exporting outputs to artifacts/data/...")
    DATA = ART / "data"

    # Helper: combine channels into long-format
    def wide_to_long(d, cols):
        frames = []
        for ch, df in d.items():
            tmp = df[cols].copy()
            tmp.insert(0, "sensor_id", ch)
            frames.append(tmp)
        return pd.concat(frames)

    # 1. D2_main_scores_hourly.xlsx
    score_cols = ["Q_TI", "Q_GS", "Q_FA", "D2_base", "D2_pre", "D2_total",
                  "grade", "usable_tag", "veto_flag", "veto_reason", "dominant_limitation"]
    scores_long = wide_to_long(all_D2, score_cols)
    scores_long.insert(1, "calibration_id", CALIBRATION_ID)
    scores_long.insert(2, "run_id",          RUN_ID)
    with pd.ExcelWriter(DATA / "D2_main_scores_hourly.xlsx", engine="openpyxl") as w:
        scores_long.to_excel(w, sheet_name="D2_scores")
        # Wide-format D2_total for quick comparison
        wide_d2 = pd.DataFrame({ch: all_D2[ch]["D2_total"] for ch in SCORED_CHANNELS})
        wide_d2.to_excel(w, sheet_name="D2_total_wide")
        wide_q = pd.DataFrame({ch: subs_all[ch]["Q_TI"] for ch in SCORED_CHANNELS})
        wide_q.to_excel(w, sheet_name="Q_TI_wide")
        wide_q2 = pd.DataFrame({ch: subs_all[ch]["Q_GS"] for ch in SCORED_CHANNELS})
        wide_q2.to_excel(w, sheet_name="Q_GS_wide")
        wide_q3 = pd.DataFrame({ch: subs_all[ch]["Q_FA"] for ch in SCORED_CHANNELS})
        wide_q3.to_excel(w, sheet_name="Q_FA_wide")
    log("    [OK] D2_main_scores_hourly.xlsx")

    # 2. D2_preprocess_flags_hourly.xlsx
    flag_cols = [
        "missing_rate", "irregular_rate", "info_empty_cov",
        "sensor_freeze_cov", "low_iqr_cov", "floor_occupancy",
        "soft_rle_cov", "soft_stasis_cov", "resolution_limited",
        "L_max_min", "gap_run_count",
    ]
    flags_long = wide_to_long(subs_all, flag_cols)
    flags_long.insert(0, "sensor_id", flags_long.pop("sensor_id"))
    flags_long.to_excel(DATA / "D2_preprocess_flags_hourly.xlsx")
    log("    [OK] D2_preprocess_flags_hourly.xlsx")

    # 3. D2_gap_run_table.xlsx
    gap_df.to_excel(DATA / "D2_gap_run_table.xlsx", index=False)
    log("    [OK] D2_gap_run_table.xlsx")

    # 4. D2_freeze_availability_events.xlsx
    freeze_events.to_excel(DATA / "D2_freeze_availability_events.xlsx", index=False)
    log("    [OK] D2_freeze_availability_events.xlsx")

    # 5. D2_interpolation_ledger.xlsx
    ledger_df.to_excel(DATA / "D2_interpolation_ledger.xlsx", index=False)
    log("    [OK] D2_interpolation_ledger.xlsx")

    # 6. D2_mapping_params.xlsx
    mapping_df.to_excel(DATA / "D2_mapping_params.xlsx", index=False)
    log("    [OK] D2_mapping_params.xlsx")

    # 7. D2_sensor_availability_profile.xlsx
    profile_df.to_excel(DATA / "D2_sensor_availability_profile.xlsx", index=False)
    log("    [OK] D2_sensor_availability_profile.xlsx")

    # 8. D2_timestamp_audit.xlsx
    with pd.ExcelWriter(DATA / "D2_timestamp_audit.xlsx", engine="openpyxl") as w:
        audit_df.to_excel(w, sheet_name="irregular_timestamps", index=False)
        audit_summary.to_excel(w, sheet_name="summary", index=False)
    log("    [OK] D2_timestamp_audit.xlsx")

    # 9. D2_audit_log.xlsx (P1-E)
    if audit_log_df is not None:
        audit_log_df.to_excel(DATA / "D2_audit_log.xlsx", index=False)
        log("    [OK] D2_audit_log.xlsx")

    log("    All outputs saved.")


# ─── P1-D: Audit log ──────────────────────────────────────────────────────────

def _file_sha256_16(p: Path) -> str:
    import hashlib
    if not p.exists():
        return "n/a"
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def build_audit_log(calib: dict, n_hours: int, elapsed: float, veto_rate: dict) -> pd.DataFrame:
    """Generate D2_audit_log single-sheet with run metadata and input hashes."""
    src = _ROOT / "run_d2_pipeline.py"
    contract_path = _DECOMP / "outputs" / "parquet" / "time_base_contract.json"
    inputs = [contract_path] if contract_path.exists() else [
        _ROOT / "beian_min_1_DO_25-08-26-04.xlsx",
        _ROOT / "beian_min_2_ORP-08-26-04.xlsx",
        _ROOT / "beian_min_3_QR+QIR-08-26-04.xlsx",
    ]
    rows = [
        ("run_id",             RUN_ID),
        ("calibration_id",     calib.get("calibration_id", CALIBRATION_ID)),
        ("mapping_version",    _d2_cfg.mapping.mapping_version),
        ("study_design_version", _d2_cfg.study_design.version),
        ("calibration_basis", calib.get("calibration_basis")),
        ("temporal_integrity_source_scope", "source_file_global_plus_channel_missingness"),
        ("response_loss_role", "diagnostic_only"),
        ("external_site_validation", _d2_cfg.study_design.external_site_validation["status"]),
        ("qfa_window",         _d2_cfg.freeze_window.length),
        ("process_floor_channels", ",".join(
            ch for ch in SCORED_CHANNELS
            if _d2_cfg.sensors[ch].availability_mode == "process_floor"
        )),
        ("input_source",       INPUT_PROVENANCE.get("source")),
        ("input_hash",         INPUT_PROVENANCE.get("input_hash")),
        ("script_sha16",       _file_sha256_16(src)),
        ("n_channels",         len(SCORED_CHANNELS)),
        ("n_hours_output",     n_hours),
        ("elapsed_sec",        round(elapsed, 2)),
        ("benchmark_hours",    calib.get("benchmark_windows", {}).get("total_benchmark_hours", 0)),
        ("veto_rate_mean_pct", round(float(np.mean(list(veto_rate.values()))) * 100, 2)),
        ("veto_floor_applied", any(isinstance(v, dict) and v.get("source") == "floor_applied"
                                   for v in calib.get("veto_thresholds", {}).values())),
        ("ts_generated",       datetime.now().isoformat(timespec="seconds")),
    ]
    for p in inputs:
        rows.append((f"input_{p.name}_sha16", _file_sha256_16(p)))
    return pd.DataFrame(rows, columns=["key", "value"])


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global CALIBRATION_ID
    t_total = time.time()
    log("=" * 72)
    log("D2 Temporal Continuity & Information Availability  —  V2 Pipeline")
    log(f"Run ID: {RUN_ID}")
    log("=" * 72)

    # 1. Load raw data
    df_raw, df_aln = load_raw_excel()

    # 2. Preprocess flags (minute-level)
    flags_all = compute_preprocess_flags(df_raw, df_aln)

    # 3. Gap runs
    log("[3] Building gap run table...")
    gap_df = compute_gap_runs(flags_all)
    log(f"    {len(gap_df)} gap runs  |  max={gap_df['duration_min'].max():.0f} min  "
        f"|  veto triggers: {gap_df['veto_triggered'].sum()}")

    # 4. Interpolation ledger
    log("[4] Building interpolation ledger...")
    ledger_df = build_interpolation_ledger(flags_all, gap_df)
    log(f"    {len(ledger_df)} imputed segments across {len(SCORED_CHANNELS)} channels")

    # 5. Window stats
    stats_all = compute_window_stats(flags_all)

    # 7. Calibration (needs stats for benchmark percentiles)
    # Provide temporary bench_var lookup using engineering defaults
    calib_tmp = {
        "bench_var_P50":         {},
        "bench_var_P05":         {},
        "bench_var_P50_default": {"DO": 0.010, "ORP": 2.0},
        "bench_var_P05_default": {"DO": 0.001, "ORP": 0.05},
    }
    calib_raw = load_or_generate_calibration(stats_all, flags_all)
    CALIBRATION_ID = calib_raw.get("calibration_id", CALIBRATION_ID)
    # Merge bench_var from calib_raw into calib_tmp for response_loss
    bv50, bv05, bv50d, bv05d = _build_bench_var_lookup(calib_raw)
    calib_full = {**calib_tmp,
                  "bench_var_P50":         bv50,
                  "bench_var_P05":         bv05,
                  "bench_var_P50_default": bv50d,
                  "bench_var_P05_default": bv05d,
                  **calib_raw}

    # 6. Response loss (Tier 1)
    rl_all = compute_response_loss_tier1(flags_all, calib_full)

    # 8. Sub-scores
    subs_all = compute_subscores(stats_all, rl_all, calib_raw)

    # 9. D2 aggregation + veto
    all_D2, all_veto = aggregate_d2(subs_all, calib_raw)

    # 10. Freeze availability events
    log("[10] Extracting freeze availability events...")
    freeze_events = extract_freeze_events(
        flags_all, subs_all, calibration_id=CALIBRATION_ID
    )
    log(f"    {len(freeze_events)} production hard-availability events across all channels")

    # 11. Timestamp audit
    log("[11] Building timestamp audit...")
    audit_df, audit_summary = build_timestamp_audit(df_raw, df_aln)

    # 12. Sensor profile
    log("[12] Building sensor availability profile...")
    profile_df = build_sensor_profile(all_D2, subs_all)

    # 13. Mapping params
    mapping_df = build_mapping_params(calib_raw)

    # Summary log
    log("\n[Summary] Per-channel D2 means:")
    for ch in SCORED_CHANNELS:
        d2m = all_D2[ch]["D2_total"].mean()
        qti = subs_all[ch]["Q_TI"].mean()
        qgs = subs_all[ch]["Q_GS"].mean()
        qfa = subs_all[ch]["Q_FA"].mean()
        veto_rate = all_D2[ch]["veto_flag"].mean() * 100
        log(f"  {ch:10s}  D2={d2m:.3f}  Q_TI={qti:.2f}  Q_GS={qgs:.2f}  "
            f"Q_FA={qfa:.2f}  veto={veto_rate:.1f}%")

    # 14. Export (P1-E: build audit log just before export)
    veto_rate_per_ch = {ch: float(all_D2[ch]["veto_flag"].mean()) for ch in SCORED_CHANNELS}
    audit_log_df = build_audit_log(
        calib_raw,
        n_hours=len(list(all_D2.values())[0]),
        elapsed=time.time() - t_total,
        veto_rate=veto_rate_per_ch,
    )
    export_outputs(all_D2, subs_all, gap_df, freeze_events, ledger_df,
                   audit_df, audit_summary, profile_df, mapping_df, calib_raw,
                   audit_log_df=audit_log_df)

    # Save state
    state = {
        "all_D2":       all_D2,
        "subs_all":     subs_all,
        "stats_all":    stats_all,
        "flags_all":    flags_all,
        "gap_df":       gap_df,
        "freeze_events": freeze_events,
        "ledger_df":    ledger_df,
        "profile_df":   profile_df,
        "mapping_df":   mapping_df,
        "calib":        calib_raw,
        "rl_all":       rl_all,
        "scored_channels": SCORED_CHANNELS,
        "run_id":       RUN_ID,
        "calibration_id": CALIBRATION_ID,
        "elapsed_sec":  time.time() - t_total,
    }
    pkl_out = ART / "d2_state.pkl"
    with open(pkl_out, "wb") as f: pickle.dump(state, f)
    log(f"\n[State] Saved {pkl_out} ({pkl_out.stat().st_size/1e6:.1f} MB)")

    elapsed = time.time() - t_total
    log(f"\n{'='*72}")
    log(f"D2 V2 pipeline complete in {elapsed:.1f}s")
    log(f"{'='*72}")
    return state


if __name__ == "__main__":
    main()
