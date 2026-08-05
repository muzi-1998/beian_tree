"""run_d2_pipeline.py
D2 Temporal Continuity & Information Availability - V4 (single-plant)

Channels : 14 scored (DO_1_1..4, DO_2_1..4, ORP_1_1..3, ORP_2_1..3)
           4 support (QR/QIR — excluded from D2 main chain)
Main window : 24 h trailing, step 1 h → hourly output
Calibration : prespecified engineering mapping + development-only reference profile

V4 outputs (artifacts/data/):
  D2_main_scores_hourly.xlsx          - hourly Q_TI, Q_GS, Q_HA, D2_total and diagnostics
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
    D2Aggregator, HardAvailabilityScorer, FreezeAvailabilityScorer, GapSeverityScorer,
    TemporalIntegrityScorer,
)
from src.d2_availability.process_floor import route_availability_evidence
from src.utils.timestamp_quality import (
    audit_timestamp_sources,
    source_for_channel,
    verify_source_files,
)
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
                _d2_cfg.mapping.Q_HA_rule["aggravation"].get(
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
    "true_irregular_rate_breaks": _m.piecewise_breaks["Q_TI"]["true_irregular_rate"],
    "L_max_breaks_min":       _m.piecewise_breaks["Q_GS"]["L_max_min"],
    "gap_count_breaks":       _m.piecewise_breaks["Q_GS"]["gap_run_count"],
    "hard_stasis_breaks":     _m.piecewise_breaks["Q_HA"]["hard_stasis_fraction_observed"],
    "veto_Lmax_min":          _m.safety_floor["L_max_minutes"],
    "veto_missing_rate":      _m.safety_floor["missing_rate"],
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
    "w_QHA": _m.aggregation["weights"]["Q_HA"],
    "lambda_blend": _m.aggregation["lambda_blend"],
    # Short/long gap boundary
    "short_gap_max_min": _m.imputation["short_gap_max_min"],
    "long_gap_min_min":  _m.imputation["long_gap_min_min"],
}

CALIBRATION_ID = f"NorthBank_D2_v4_{datetime.now().strftime('%Y%m%d')}"
RUN_ID         = f"D2V4_{datetime.now().strftime('%Y%m%d_%H%M')}"
INPUT_PROVENANCE = {"source": "uninitialised"}
SOURCE_TIMESTAMP_AUDIT = {"events": pd.DataFrame(), "hourly": pd.DataFrame(), "summary": pd.DataFrame()}
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


def piecewise_score(x: pd.Series, breaks: list, reverse: bool = True) -> pd.Series:
    """Map a series to [1-5] using piecewise-linear function.

    breaks: 5 thresholds defining a continuous 5-to-1 mapping.
    reverse=True: higher x → lower score (risk metric).
    """
    x = x.copy()
    score = pd.Series(np.nan, index=x.index, dtype=float)
    b0, b1, b2, b3, b4 = breaks
    if reverse:
        score[x <= b0]              = 5.0
        score[(x > b0) & (x <= b1)] = 4.0 + (b1 - x[(x > b0) & (x <= b1)]) / (b1 - b0)
        score[(x > b1) & (x <= b2)] = 3.0 + (b2 - x[(x > b1) & (x <= b2)]) / (b2 - b1)
        score[(x > b2) & (x <= b3)] = 2.0 + (b3 - x[(x > b2) & (x <= b3)]) / (b3 - b2)
        score[(x > b3) & (x <= b4)] = 1.0 + (b4 - x[(x > b3) & (x <= b4)]) / (b4 - b3)
        score[x > b4]               = 1.0
    else:
        score[x >= b4]              = 5.0
        score[(x >= b3) & (x < b4)] = 4.0 + (x[(x >= b3) & (x < b4)] - b3) / (b4 - b3)
        score[(x >= b2) & (x < b3)] = 3.0 + (x[(x >= b2) & (x < b3)] - b2) / (b3 - b2)
        score[(x >= b1) & (x < b2)] = 2.0 + (x[(x >= b1) & (x < b2)] - b1) / (b2 - b1)
        score[(x >= b0) & (x < b1)] = 1.0 + (x[(x >= b0) & (x < b1)] - b0) / (b1 - b0)
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
    global INPUT_PROVENANCE, SOURCE_TIMESTAMP_AUDIT, CACHE_KEY
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
            _ROOT / "src" / "utils" / "timestamp_quality.py",
            Path(__file__),
        ]
        CACHE_KEY = _sha256_paths(hash_paths)
        raw_source_dir = _DECOMP / "Raw data"
        verify_source_files(contract, raw_source_dir)
        timestamp_cache = _cache_path("d2_source_timestamp_audit")
        if timestamp_cache.exists():
            with open(timestamp_cache, "rb") as handle:
                SOURCE_TIMESTAMP_AUDIT = pickle.load(handle)
        else:
            ts_cfg = _d2_cfg.mapping.timestamp_quality
            SOURCE_TIMESTAMP_AUDIT = audit_timestamp_sources(
                contract,
                raw_source_dir,
                expected_start=pd.Timestamp(_d2_cfg.time_grid["expected_start"]),
                expected_end=pd.Timestamp(_d2_cfg.time_grid["expected_end"]),
                expected_interval_sec=float(ts_cfg["expected_interval_sec"]),
                jitter_tolerance_sec=float(ts_cfg["jitter_tolerance_sec"]),
                gap_interval_min_sec=float(ts_cfg["gap_interval_min_sec"]),
            )
            with open(timestamp_cache, "wb") as handle:
                pickle.dump(SOURCE_TIMESTAMP_AUDIT, handle)
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
        _DECOMP / "Raw data" / "beian_min_1_DO_25-08-26-04.xlsx",
        _DECOMP / "Raw data" / "beian_min_2_ORP-08-26-04.xlsx",
        _DECOMP / "Raw data" / "beian_min_3_QR+QIR-08-26-04.xlsx",
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
        _ROOT / "src" / "utils" / "timestamp_quality.py",
        Path(__file__),
    ])
    INPUT_PROVENANCE = {"source": "legacy_excel_fallback", "input_hash": CACHE_KEY}
    return df_raw, df_aln


# ─── 2. Preprocess flags (minute-level) ──────────────────────────────────────

def compute_preprocess_flags(df_raw: pd.DataFrame, df_aln: pd.DataFrame) -> dict:
    """Return dict of {channel: flags_df} with minute-level boolean flags.

    Flags: present_raw, missing, value_gap_recovery, imputed, long_gap,
           info_empty, freeze_candidate, raw_value, aligned_value. Raw-source
           timestamp defects are audited before alignment in a separate table.
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

        # Source-order anomalies are retained in the 1.1 contract audit.  They
        # have no reliable minute location after canonical alignment.

        # Value-gap recovery after canonical alignment is a Q_GS diagnostic.
        was_missing  = missing.astype(int)
        gap_end_flag = (was_missing != was_missing.shift(1).fillna(0)).astype(bool) & ~missing
        value_gap_recovery = gap_end_flag

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
            "value_gap_recovery": value_gap_recovery.astype(np.int8),
            "imputed":            imputed_flag.astype(np.int8),
            "long_gap":           long_gap_flag.astype(np.int8),
            "info_empty":         availability["any_information_unavailable"].astype(np.int8),
            "continuity_unavailable": availability["continuity_unavailable"].astype(np.int8),
            "hard_availability_loss": availability["hard_availability_loss"].astype(np.int8),
            "qha_unavailable":    availability["hard_availability_loss"].astype(np.int8),
            "qfa_unavailable":    availability["hard_availability_loss"].astype(np.int8),
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
    """Compute 24 h continuity and configured 6 h hard-availability statistics.

    Returns dict[channel] = DataFrame (hourly index) with columns:
        missing_rate, duplicate_rate, out_of_order_rate, true_irregular_rate,
        value_gap_recovery_rate, source_gap_recovery_rate,
        L_max_min, gap_run_count, hard_stasis_fraction_observed
    """
    cache_path = _cache_path("d2_win_stats")
    if cache_path.exists():
        log("[5] Loading window stats from cache")
        with open(cache_path, "rb") as f: return pickle.load(f)

    log("[5] Computing 24 h continuity and 6 h Q_HA statistics...")
    t0 = time.time()
    stats_all = {}
    W = _d2_cfg.main_window.length
    MP = int(pd.Timedelta(W) / pd.Timedelta(_d2_cfg.time_grid["freq"]))
    W_FA = _d2_cfg.freeze_window.length
    MP_FA = int(pd.Timedelta(W_FA) / pd.Timedelta(_d2_cfg.time_grid["freq"]))
    timestamp_hourly = SOURCE_TIMESTAMP_AUDIT.get("hourly", pd.DataFrame())
    n_hours = int(pd.Timedelta(W) / pd.Timedelta("1h"))

    for ch in SCORED_CHANNELS:
        fl = flags_all[ch]

        # Rolling means of binary flags
        miss_rate  = fl["missing"].rolling(W, min_periods=MP).mean()
        value_gap_recovery_rate = fl["value_gap_recovery"].rolling(W, min_periods=MP).mean()
        source = source_for_channel(ch)
        if not timestamp_hourly.empty:
            source_counts = timestamp_hourly.loc[
                timestamp_hourly["source"].eq(source)
            ].drop(columns="source")
            rolling_counts = source_counts.rolling(n_hours, min_periods=n_hours).sum()
            denominator = rolling_counts["valid_transition"].replace(0, np.nan)
            dup_hourly = rolling_counts["duplicate"].div(denominator)
            oor_hourly = rolling_counts["out_of_order"].div(denominator)
            irregular_hourly = rolling_counts["true_irregular"].div(denominator)
            source_gap_hourly = rolling_counts["gap_recovery"].div(denominator)
        else:
            empty_idx = pd.date_range(
                fl.index.min().floor("h"), fl.index.max().floor("h"), freq="1h"
            )
            dup_hourly = pd.Series(np.nan, index=empty_idx)
            oor_hourly = pd.Series(np.nan, index=empty_idx)
            irregular_hourly = pd.Series(np.nan, index=empty_idx)
            source_gap_hourly = pd.Series(np.nan, index=empty_idx)
        legacy_info_empty_cov = fl["info_empty"].rolling(W_FA, min_periods=MP_FA).mean()
        hard_stasis_minutes = fl["sensor_freeze"].rolling(W_FA, min_periods=MP_FA).sum()
        observed_minutes = fl["present_raw"].rolling(W_FA, min_periods=MP_FA).sum()
        hard_stasis_fraction_observed = hard_stasis_minutes.div(
            observed_minutes.where(observed_minutes > 0)
        )
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
            "value_gap_recovery_rate": value_gap_recovery_rate,
            "info_empty_cov":  legacy_info_empty_cov,
            "hard_stasis_fraction_observed": hard_stasis_fraction_observed,
            "qha_observed_fraction": observed_minutes.div(float(MP_FA)),
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
        hourly["duplicate_rate"] = dup_hourly.reindex(hourly.index)
        hourly["out_of_order_rate"] = oor_hourly.reindex(hourly.index)
        hourly["true_irregular_rate"] = irregular_hourly.reindex(hourly.index)
        hourly["source_gap_recovery_rate"] = source_gap_hourly.reindex(hourly.index)

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
        if (loaded.get("calibration_basis") == "blocked_development_reference_v3" and
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
             "calibration_basis": "blocked_development_reference_v4_hard_only",
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
            "duplicate_rate": safe_pct(
                "duplicate_rate", SCORED_CHANNELS,
                {0.25: 0.0, 0.50: 0.0, 0.75: 0.0, 0.95: 0.0, 0.99: 0.0},
            ),
            "out_of_order_rate": safe_pct(
                "out_of_order_rate", SCORED_CHANNELS,
                {0.25: 0.0, 0.50: 0.0, 0.75: 0.0, 0.95: 0.0, 0.99: 0.0},
            ),
            "true_irregular_rate": safe_pct(
                "true_irregular_rate", SCORED_CHANNELS,
                {0.25: 0.0, 0.50: 0.0, 0.75: 0.001, 0.95: 0.002, 0.99: 0.005},
            ),
            "gap_recovery_rate_diagnostic": safe_pct(
                "source_gap_recovery_rate", SCORED_CHANNELS,
                {0.25: 0.0, 0.50: 0.0, 0.75: 0.001, 0.95: 0.002, 0.99: 0.005},
            ),
        },
        "Q_gap_severity": {
            "L_max_minutes":  safe_pct("L_max_min",    SCORED_CHANNELS,
                                       {0.25: 0, 0.50: 1, 0.75: 2, 0.95: 5, 0.99: 30}),
            "gap_run_count":  safe_pct("gap_run_count", SCORED_CHANNELS,
                                       {0.25: 0, 0.50: 0, 0.75: 1, 0.95: 3, 0.99: 8}),
        },
        "Q_hard_availability": {
            "hard_stasis_fraction_observed": safe_pct(
                "hard_stasis_fraction_observed", SCORED_CHANNELS,
                {0.25: 0.0, 0.50: 0.0, 0.75: 0.0, 0.95: 0.02, 0.99: 0.08},
            ),
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
    """Map window stats to Q_TI, Q_GS and hard-only Q_HA (hourly, per channel).

    Returns dict[channel] = DataFrame with strict subscores and diagnostic evidence.
    """
    log("[8] Computing Q_TI, Q_GS, Q_HA and sensitive diagnostics...")
    subs_all = {}

    ti_scorer = TemporalIntegrityScorer(_d2_cfg)
    gs_scorer = GapSeverityScorer(_d2_cfg)
    ha_scorer = HardAvailabilityScorer(_d2_cfg)
    sensitive_cfg = _d2_cfg.mapping.dynamic_information_sufficiency

    for ch in SCORED_CHANNELS:
        st = stats_all[ch].copy()
        rl = rl_all.get(ch, pd.Series(0.0, index=st.index))

        Q_TI = ti_scorer.score(st)
        Q_TI_observed_weight = ti_scorer.observed_weight(st)
        Q_GS = gs_scorer.score(st)
        sensor_meta = _d2_cfg.sensors[ch]
        Q_HA, Q_main = ha_scorer.score(
            st,
            rl,
            allow_response_loss=sensor_meta.response_loss_enabled,
        )
        rl_aligned = rl.reindex(st.index).fillna(0.0)
        intrinsic_soft = st["soft_stasis_cov"].ge(
            float(sensitive_cfg["intrinsic_window_fraction"])
        )
        peer_response_loss = (
            bool(sensor_meta.response_loss_enabled)
            & rl_aligned.ge(float(sensitive_cfg["response_loss_rate"]))
        )
        soft_evidence_family_count = (
            intrinsic_soft.astype(int) + peer_response_loss.astype(int)
        )
        joint_soft = soft_evidence_family_count.ge(
            int(sensitive_cfg["minimum_independent_families"])
        )
        quasi_freeze_suspect = consecutive_run_len(joint_soft).ge(
            int(sensitive_cfg["persistence_hours"])
        )
        sensitive_risk = pd.Series("none", index=st.index, dtype=object)
        sensitive_risk.loc[intrinsic_soft & ~peer_response_loss] = "intrinsic_low_dynamics_only"
        sensitive_risk.loc[peer_response_loss & ~intrinsic_soft] = "peer_response_loss_only"
        sensitive_risk.loc[joint_soft] = "joint_soft_evidence"
        sensitive_risk.loc[quasi_freeze_suspect] = "sustained_quasi_freeze_suspect"
        Q_miss = piecewise_score(st["missing_rate"], _d2_cfg.mapping.piecewise_breaks["Q_TI"]["missing_rate"])
        Q_irregular = piecewise_score(
            st["true_irregular_rate"],
            _d2_cfg.mapping.piecewise_breaks["Q_TI"]["true_irregular_rate"],
        )
        Q_duplicate = piecewise_score(
            st["duplicate_rate"],
            _d2_cfg.mapping.piecewise_breaks["Q_TI"]["duplicate_rate"],
        )
        Q_out_of_order = piecewise_score(
            st["out_of_order_rate"],
            _d2_cfg.mapping.piecewise_breaks["Q_TI"]["out_of_order_rate"],
        )
        Q_lmax = piecewise_score(st["L_max_min"], _d2_cfg.mapping.piecewise_breaks["Q_GS"]["L_max_min"])

        subs_all[ch] = pd.DataFrame({
            "Q_TI":          Q_TI,
            "Q_GS":          Q_GS,
            "Q_HA":          Q_HA,
            "Q_FA":          Q_HA,
            "Q_miss_comp":   Q_miss,
            "Q_true_irregular_comp": Q_irregular,
            "Q_duplicate_comp": Q_duplicate,
            "Q_out_of_order_comp": Q_out_of_order,
            "Q_TI_observed_weight": Q_TI_observed_weight,
            "Q_lmax_comp":   Q_lmax,
            "Q_main_HA":     Q_main,
            "Q_main_FA":     Q_main,
            "rl_rate":       rl_aligned,
            "missing_rate":  st["missing_rate"],
            "duplicate_rate": st["duplicate_rate"],
            "out_of_order_rate": st["out_of_order_rate"],
            "true_irregular_rate": st["true_irregular_rate"],
            "source_gap_recovery_rate": st["source_gap_recovery_rate"],
            "value_gap_recovery_rate": st["value_gap_recovery_rate"],
            "L_max_min":     st["L_max_min"],
            "P95_gap_min":   st["P95_gap_min"],
            "gap_run_count": st["gap_run_count"],
            "info_empty_cov": st["info_empty_cov"],
            "hard_stasis_fraction_observed": st["hard_stasis_fraction_observed"],
            "qha_observed_fraction": st["qha_observed_fraction"],
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
            "intrinsic_soft_evidence": intrinsic_soft.astype(int),
            "peer_response_loss_evidence": peer_response_loss.astype(int),
            "soft_evidence_family_count": soft_evidence_family_count,
            "quasi_freeze_suspect": quasi_freeze_suspect.astype(int),
            "D2_sensitive_risk": sensitive_risk,
        })

    log("    Sub-scores computed.")
    return subs_all


# ─── 9. D2 aggregation + veto ─────────────────────────────────────────────────

def aggregate_d2(subs_all: dict, calib: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate Q_TI, Q_GS and Q_HA to D2_total with veto rules.

    Returns (scores_df, veto_log_df) — both hourly, multi-channel.
    """
    log("[9] D2 aggregation + veto rules...")
    aggregator = D2Aggregator(_d2_cfg, calib)
    all_D2, all_veto = {}, {}
    for ch in SCORED_CHANNELS:
        s = subs_all[ch]
        scored = aggregator.aggregate(s["Q_TI"], s["Q_GS"], s["Q_HA"], s)
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
        component_scores = s[["Q_TI", "Q_GS", "Q_HA"]]
        dom = component_scores.idxmin(axis=1).map({
            "Q_TI": "temporal_integrity", "Q_GS": "gap_severity",
            "Q_HA": "hard_information_availability",
        })
        dom[component_scores.min(axis=1) >= 4.5] = "ok"
        sensitive_usable_tag = usable_tag.copy()
        sensitive_mask = s["quasi_freeze_suspect"].astype(bool) & sensitive_usable_tag.eq("train_ok")
        sensitive_usable_tag.loc[sensitive_mask] = "diagnostic_review"

        all_D2[ch] = pd.DataFrame({
            "Q_TI":            scored["Q_TI"],
            "Q_GS":            scored["Q_GS"],
            "Q_HA":            scored["Q_HA"],
            "Q_FA":            scored["Q_FA"],
            "D2_base":         scored["D2_base"],
            "D2_pre":          scored["D2_pre"],
            "D2_total":        D2_total,
            "D2_Strict":       D2_total,
            "D2_Sensitive_risk": s["D2_sensitive_risk"],
            "D2_Sensitive_flag": s["quasi_freeze_suspect"].astype(int),
            "grade":           grade,
            "usable_tag":      usable_tag,
            "sensitive_usable_tag": sensitive_usable_tag,
            "veto_flag":       veto_flag.astype(int),
            "veto_reason":     scored["veto_reason"],
            "dominant_limitation": dom,
        })
        all_veto[ch] = veto_flag

    log("    Aggregation done.")
    return all_D2, all_veto


def hard_stasis_breaks_ref():
    return ENG_DEFAULTS["hard_stasis_breaks"][1]


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
                    raw_stasis_start = ev_start - pd.Timedelta(
                        minutes=int(ENG_DEFAULTS["tau_rle_D1_min"])
                    )
                    h_start = raw_stasis_start.floor("h")
                    h_end   = ts.ceil("h")
                    sub_win = subs_all[ch].loc[h_start:h_end] if ch in subs_all else pd.DataFrame()
                    ie_cov  = float(sub_win["info_empty_cov"].mean()) if len(sub_win) else np.nan
                    rl_rate = float(sub_win["rl_rate"].mean())         if len(sub_win) else np.nan
                    q_main  = float(sub_win["Q_main_FA"].mean())       if len(sub_win) else np.nan
                    q_final = float(sub_win["Q_HA"].mean())            if len(sub_win) else np.nan
                    rle_col = "hard_rle_run_min" if POOL_TOPOLOGY[ch]["availability_mode"] == "process_floor" else "rle_run_min"
                    rle_max = float(fl[rle_col].loc[ev_start:ts].max())
                    event_slice = fl.loc[ev_start:ts]
                    event_type = "resolution_equivalent_persistent_stasis"
                    d1_id, d1_ftype, rel = _link_d1(raw_stasis_start, ts, ch)
                    rows.append({
                        "event_id":               f"HAE_{ev_id:04d}",
                        "event_type":             event_type,
                        "evidence_class":          "production_hard_availability",
                        "sensor_id":              ch,
                        "start_ts":               raw_stasis_start,
                        "detection_ts":           ev_start,
                        "end_ts":                 ts,
                        "duration_min":           int((ts - raw_stasis_start).total_seconds() // 60),
                        "detection_latency_min":  int((ev_start - raw_stasis_start).total_seconds() // 60),
                        "info_empty_coverage":    ie_cov,
                        "rle_max_min":            rle_max,
                        "response_loss_rate":     rl_rate,
                        "response_loss_tier_used": 1 if POOL_TOPOLOGY[ch]["response_loss_production_enabled"] else 0,
                        "response_loss_diagnostic_available": 1 if POOL_TOPOLOGY[ch]["response_loss_enabled"] else 0,
                        "Q_main_before_agg":      q_main,
                        "Q_HA_final":             q_final,
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
    """Return pre-alignment timestamp events, hourly evidence, and summary."""
    audit_df = SOURCE_TIMESTAMP_AUDIT.get("events", pd.DataFrame()).copy()
    hourly_df = SOURCE_TIMESTAMP_AUDIT.get("hourly", pd.DataFrame()).copy()
    source_summary = SOURCE_TIMESTAMP_AUDIT.get("summary", pd.DataFrame()).copy()
    summary_rows = [
        ("input_source", INPUT_PROVENANCE.get("source")),
        ("grid_rows", len(df_aln)),
        ("grid_start", df_aln.index.min()),
        ("grid_end", df_aln.index.max()),
        ("timestamp_audit_stage", "raw_source_order_before_sort_and_alignment"),
        ("qti_unavailable_policy", "conditional_weight_normalisation"),
        ("gap_recovery_role", "diagnostic_only_represented_by_Q_GS"),
    ]
    for row in source_summary.to_dict("records"):
        source = row.pop("source")
        for key, value in row.items():
            summary_rows.append((f"source_{source}_{key}", value))
    for ch in SCORED_CHANNELS:
        summary_rows.append((f"missing_cells_{ch}", int(df_aln[ch].isna().sum())))
    summary = pd.DataFrame(summary_rows, columns=["metric", "value"])
    return audit_df, hourly_df, summary


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
            "mean_Q_HA":              float(sub["Q_HA"].mean()),
            "mean_Q_FA":              float(sub["Q_HA"].mean()),
            "mean_Q_TI_observed_weight": float(sub["Q_TI_observed_weight"].mean()),
            "mean_missing_rate":      float(sub["missing_rate"].mean()),
            "mean_true_irregular_rate": float(sub["true_irregular_rate"].mean()),
            "mean_duplicate_rate":    float(sub["duplicate_rate"].mean()),
            "mean_out_of_order_rate": float(sub["out_of_order_rate"].mean()),
            "mean_source_gap_recovery_rate": float(sub["source_gap_recovery_rate"].mean()),
            "mean_info_empty_cov":    float(sub["info_empty_cov"].mean()),
            "mean_hard_stasis_fraction_observed": float(sub["hard_stasis_fraction_observed"].mean()),
            "mean_qha_observed_fraction": float(sub["qha_observed_fraction"].mean()),
            "mean_floor_occupancy":   float(sub["floor_occupancy"].mean()),
            "mean_resolution_limited": float(sub["resolution_limited"].mean()),
            "mean_sensor_freeze_cov": float(sub["sensor_freeze_cov"].mean()),
            "mean_low_iqr_cov":       float(sub["low_iqr_cov"].mean()),
            "mean_soft_rle_cov":      float(sub["soft_rle_cov"].mean()),
            "mean_soft_stasis_cov":   float(sub["soft_stasis_cov"].mean()),
            "sensitive_suspect_rate": float(sub["quasi_freeze_suspect"].mean()),
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
        ("Q_HA", metric, breaks, "d2_mapping.yaml")
        for metric, breaks in cfg_breaks["Q_HA"].items()
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
            "break_5":            breaks[4],
            "score_zone_1":       f">{breaks[4]}",
            "score_zone_1_to_2":  f"{breaks[3]}-{breaks[4]}",
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
            "mapping_id": f"Q_HA_{ch}_process_floor",
            "subscore_name": "Q_HA",
            "input_metric": "hard_stasis_fraction_observed",
            "mapping_type": "process_floor_route",
            "break_1": None,
            "break_2": None,
            "break_3": None,
            "break_4": None,
            "break_5": None,
            "score_zone_1": None,
            "score_zone_1_to_2": None,
            "score_zone_2_to_3": None,
            "score_zone_3_to_4": None,
            "score_zone_4_to_5": None,
            "calibration_source": "d2_sensors.yaml+d2_mapping.yaml",
            "mapping_version": _d2_cfg.mapping.mapping_version,
            "calibration_id": calib.get("calibration_id", CALIBRATION_ID),
            "effective_date": datetime.now().strftime("%Y-%m-%d"),
            "sensor_id": ch,
            "qha_window": _d2_cfg.freeze_window.length,
            "production_evidence": ",".join(floor_policy["production_evidence"]),
            "process_floor_threshold": sensor.process_floor_threshold,
            "response_loss_enabled": sensor.response_loss_enabled,
        })
    return pd.DataFrame(records)


# ─── 14. Export outputs ───────────────────────────────────────────────────────

def export_outputs(all_D2, subs_all, gap_df, freeze_events, ledger_df,
                   audit_df, audit_hourly, audit_summary, profile_df, mapping_df, calib,
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
    score_cols = ["Q_TI", "Q_GS", "Q_HA", "Q_FA", "D2_base", "D2_pre",
                  "D2_total", "D2_Strict", "D2_Sensitive_risk", "D2_Sensitive_flag",
                  "grade", "usable_tag", "sensitive_usable_tag", "veto_flag",
                  "veto_reason", "dominant_limitation"]
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
        wide_q3 = pd.DataFrame({ch: subs_all[ch]["Q_HA"] for ch in SCORED_CHANNELS})
        wide_q3.to_excel(w, sheet_name="Q_HA_wide")
        wide_q3.to_excel(w, sheet_name="Q_FA_compat_wide")
    log("    [OK] D2_main_scores_hourly.xlsx")

    # 2. D2_preprocess_flags_hourly.xlsx
    flag_cols = [
        "missing_rate", "true_irregular_rate", "duplicate_rate",
        "out_of_order_rate", "source_gap_recovery_rate",
        "value_gap_recovery_rate", "Q_TI_observed_weight", "info_empty_cov",
        "hard_stasis_fraction_observed", "qha_observed_fraction",
        "sensor_freeze_cov", "low_iqr_cov", "floor_occupancy",
        "soft_rle_cov", "soft_stasis_cov", "resolution_limited",
        "intrinsic_soft_evidence", "peer_response_loss_evidence",
        "soft_evidence_family_count", "quasi_freeze_suspect", "D2_sensitive_risk",
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
    freeze_events.to_excel(DATA / "D2_hard_availability_events.xlsx", index=False)
    freeze_events.to_excel(DATA / "D2_freeze_availability_events.xlsx", index=False)
    log("    [OK] D2_hard_availability_events.xlsx (+ compatibility alias)")

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
        audit_df.to_excel(w, sheet_name="raw_timestamp_events", index=False)
        audit_hourly.to_excel(w, sheet_name="hourly_source_counts")
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
        ("qha_window",         _d2_cfg.freeze_window.length),
        ("qha_semantics",      "present_raw_and_resolution_equivalent_persistent_stasis"),
        ("qfa_compatibility_alias", "Q_FA_equals_Q_HA"),
        ("sensitive_role",     "diagnostic_only_no_numeric_penalty"),
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
    log("D2 Temporal Continuity & Information Availability - V4 Pipeline")
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
    audit_df, audit_hourly, audit_summary = build_timestamp_audit(df_raw, df_aln)

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
        qha = subs_all[ch]["Q_HA"].mean()
        veto_rate = all_D2[ch]["veto_flag"].mean() * 100
        log(f"  {ch:10s}  D2={d2m:.3f}  Q_TI={qti:.2f}  Q_GS={qgs:.2f}  "
            f"Q_HA={qha:.2f}  veto={veto_rate:.1f}%")

    # 14. Export (P1-E: build audit log just before export)
    veto_rate_per_ch = {ch: float(all_D2[ch]["veto_flag"].mean()) for ch in SCORED_CHANNELS}
    audit_log_df = build_audit_log(
        calib_raw,
        n_hours=len(list(all_D2.values())[0]),
        elapsed=time.time() - t_total,
        veto_rate=veto_rate_per_ch,
    )
    export_outputs(all_D2, subs_all, gap_df, freeze_events, ledger_df,
                   audit_df, audit_hourly, audit_summary, profile_df, mapping_df, calib_raw,
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
        "timestamp_audit": SOURCE_TIMESTAMP_AUDIT,
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
    log(f"D2 V4 pipeline complete in {elapsed:.1f}s")
    log(f"{'='*72}")
    return state


if __name__ == "__main__":
    main()
