"""load_real_data_v11.py
从三个真实 Excel 文件计算 STRICT V1 子分数，生成 run_v11_pipeline.py 所需的两个 pkl 文件。

输入文件：
  beian_min_1_DO_25-08-26-04.xlsx
  beian_min_2_ORP-08-26-04.xlsx
  beian_min_3_QR+QIR-08-26-04.xlsx

输出：
  strict_v1_inputs.pkl  — subs_v1, D1_v1, detectors
  raw_hourly.pkl        — df_h, resid_h
  cache/                — 中间步骤缓存

分辨率策略（严格遵守 d1_pipeline.py 规格）：
  Q_spike  : 在 1min 数据上运行 Hampel(window=21min, k=3.0)
             → rolling("360min", min_periods=60).mean() → resample("1h").mean()
  Q_freeze : 在 1min 数据上运行 CompositeFreezeDetector()
             → comp.resample("1h").max()
  Q_step / Q_drift / Q_regime : 在小时残差上运行（已正确）
"""
from __future__ import annotations
import os, sys, time, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd

from src.config.loader import load_project_config
from src.data.loader import time_align_and_impute, PHYS_RANGE
from src.baseline.deperiodise import harmonic_decomposition_dataframe
from src.baseline.bridge_decomposition_11 import (load_decomposition_11,
                                                  effective_neff, summarise)
from src.detectors import (HampelSpikeDetector, AdjacentKSStepDetector,
                            PLSVirtualSensorDetector, engineered_peers,
                            CompositeFreezeDetector, TwoTierRegimeDetector)
from src.mapping.mapper import apply_mapping

# ── §1.1 Decomposition bridge gate ────────────────────────────────────────────
# When ON (default), D1 consumes §1.1's whitened residual/innovation + the
# whiteness_manifest contract instead of its own un-whitened harmonic baseline,
# and routes the i.i.d.-sensitive detectors (step-KS, regime-KS, PELT) per
# `scoring_mode` (see src/baseline/bridge_decomposition_11.py and
# D1_detector_audit.md §3). Set D1_USE_DECOMP_11=0 to reproduce the legacy path.
USE_DECOMP_11 = os.environ.get("D1_USE_DECOMP_11", "1") == "1"


# ─── 通道定义 ─────────────────────────────────────────────────────────────────
SCORED_CHANNELS = [
    "DO_1_1", "DO_1_2", "DO_1_3", "DO_1_4",
    "DO_2_1", "DO_2_2", "DO_2_3", "DO_2_4",
    "ORP_1_1", "ORP_1_2", "ORP_1_3",
    "ORP_2_1", "ORP_2_2", "ORP_2_3",
]
SUPPORT_CHANNELS = ["QR_1", "QR_2", "QIR_1", "QIR_2"]
ALL_CHANNELS = SCORED_CHANNELS + SUPPORT_CHANNELS

CACHE_DIR = _ROOT / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# ─── 1. 加载并合并三个 Excel 文件 ─────────────────────────────────────────────
def load_and_align() -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (df_h, df_min) — 小时均值数据和原始分钟数据。"""
    cache_h   = CACHE_DIR / "df_h_aligned.pkl"
    cache_min = CACHE_DIR / "df_min_aligned.pkl"

    if cache_h.exists() and cache_min.exists():
        log(f"[1] 从缓存加载: df_h + df_min")
        with open(cache_h, "rb") as f:
            df_h = pickle.load(f)
        with open(cache_min, "rb") as f:
            df_min = pickle.load(f)
        log(f"    df_h={df_h.shape}, df_min={df_min.shape}")
        return df_h, df_min

    log("[1] 加载原始 Excel 数据 (3 个文件)...")
    t = time.time()

    do_path  = _ROOT / "beian_min_1_DO_25-08-26-04.xlsx"
    orp_path = _ROOT / "beian_min_2_ORP-08-26-04.xlsx"
    flw_path = _ROOT / "beian_min_3_QR+QIR-08-26-04.xlsx"

    do  = pd.read_excel(do_path,  index_col=0, parse_dates=True)
    orp = pd.read_excel(orp_path, index_col=0, parse_dates=True)
    flw = pd.read_excel(flw_path, index_col=0, parse_dates=True)
    log(f"    DO: {do.shape}, ORP: {orp.shape}, QR/QIR: {flw.shape}")

    df_raw = do.join(orp, how="outer").join(flw, how="outer")
    df_raw.index.name = "timestamp"
    df_raw = df_raw.sort_index()
    log(f"    合并后: {df_raw.shape}, 时间: {df_raw.index[0]} → {df_raw.index[-1]}")
    log(f"    [{time.time()-t:.1f}s] 加载完成")

    # 物理范围裁剪
    log("[1b] 物理范围裁剪...")
    for c in df_raw.columns:
        if c in PHYS_RANGE:
            lo, hi = PHYS_RANGE[c]
            n_bad = ((df_raw[c] < lo) | (df_raw[c] > hi)).sum()
            if n_bad > 0:
                log(f"     {c}: 裁剪 {n_bad} 条越界值")
            df_raw.loc[(df_raw[c] < lo) | (df_raw[c] > hi), c] = np.nan

    # 短间隙插值 (≤3min)
    log("[1c] 短间隙插值...")
    df_raw = df_raw.interpolate(method="time", limit=3, limit_area="inside")
    null_pct = df_raw.isnull().mean() * 100
    log(f"    剩余缺失率: " + ", ".join(
        f"{c}:{v:.1f}%" for c, v in null_pct[null_pct > 0].items()))

    # 保存分钟级数据（spike/freeze 检测用）
    df_min = df_raw.copy()
    with open(cache_min, "wb") as f:
        pickle.dump(df_min, f)
    log(f"    df_min 缓存至 {cache_min} ({len(df_min)} 行)")

    # 重采样到小时级别（step/drift/regime 及谐波分解用）
    log("[1d] 重采样至小时均值...")
    df_h = df_raw.resample("1h").mean()
    df_h = df_h.ffill(limit=3)
    log(f"    小时数据: {df_h.shape} (共 {len(df_h)} 小时)")
    log(f"    时间范围: {df_h.index[0]} → {df_h.index[-1]}")

    with open(cache_h, "wb") as f:
        pickle.dump(df_h, f)
    log(f"    df_h 缓存至 {cache_h}")
    return df_h, df_min


# ─── 2. 谐波分解 → resid_h ───────────────────────────────────────────────────
def compute_residuals(df_h: pd.DataFrame) -> pd.DataFrame:
    cache_path = CACHE_DIR / "resid_h.pkl"
    if cache_path.exists():
        log(f"[2] 从缓存加载谐波残差: {cache_path}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    log("[2] 谐波分解 (日周期=24h, 周周期=168h, 3阶谐波)...")
    t = time.time()
    resid_h, baseline_h, _ = harmonic_decomposition_dataframe(
        df_h,
        daily_period_min=24,
        weekly_period_min=168,
        n_harmonics=3,
        baseline_window="168h",
        fit_first_days=30,
    )
    log(f"    [{time.time()-t:.1f}s] 完成, 残差形状: {resid_h.shape}")
    log(f"    残差范围: {resid_h.min().min():.2f} ~ {resid_h.max().max():.2f}")

    with open(cache_path, "wb") as f:
        pickle.dump(resid_h, f)
    return resid_h


# ─── 3. 各检测器 ──────────────────────────────────────────────────────────────
def run_spike_detector(df_min: pd.DataFrame, channels: list) -> dict:
    """在 1min 原始数据上运行 Hampel 检测器 (window=21min, k=3.0)。
    严格遵守 d1_pipeline.py 规格: spike 必须在分钟级数据上运行。
    """
    # cache renamed (_causal): the Hampel window is now causal (center=False,
    # audit §2 ①); the old center=True cache must not be reused.
    cache_path = CACHE_DIR / "spike_results_min_causal.pkl"
    if cache_path.exists():
        log(f"[3-spike] 从缓存加载 (分钟级, 因果窗)")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    log(f"[3-spike] Hampel 尖峰检测器 (window=21min, k=3.0) — 在 {len(df_min)} 行分钟数据上运行...")
    t = time.time()
    detector = HampelSpikeDetector(window_min=21, k=3.0)
    results = {}
    for i, c in enumerate(channels, 1):
        results[c] = detector.score(df_min[c].rename(c))
        if i % 4 == 0:
            log(f"    [{time.time()-t:.1f}s] {i}/{len(channels)} 通道完成")
    log(f"    [{time.time()-t:.1f}s] 完成")
    with open(cache_path, "wb") as f:
        pickle.dump(results, f)
    return results


def compute_spike_rate(spike_results: dict, channels: list) -> pd.DataFrame:
    """rolling 360min spike rate → resample to 1h (严格遵守 d1_pipeline.py 规格)。"""
    rates = {}
    for c in channels:
        flag = spike_results[c].aux_flag.astype(float)
        # 与 d1_pipeline.py 完全一致: rolling(360min, min_periods=60) → resample 1h mean
        rate_min = flag.rolling("360min", min_periods=60).mean()
        rates[c] = rate_min.resample("1h").mean()
    return pd.DataFrame(rates)


def run_step_detector(resid_h: pd.DataFrame, channels: list,
                      eff_neff: dict | None = None,
                      cache_tag: str = "") -> tuple[dict, dict]:
    """双窗口 KS 检测（严格遵守 PDF §四方案）。

    KS_24: win_h=12（比较 r[t-24h,t-12h] vs r[t-12h,t]，各12h）
    KS_36: win_h=18（比较 r[t-36h,t-18h] vs r[t-18h,t]，各18h）
    返回 (step_results_24, step_results_36)

    eff_neff: 每通道有效 n_eff 比（来自 §1.1 manifest 的 scoring_mode 路由）。
        iid→1.0（白创新，统计量不变）；autocorr_aware→manifest 比（统计量×√n_eff）；
        floor_freeze→0.0（统计量归零，交由 freeze 评分）。None → 全部 1.0（旧路径）。
    """
    cache_24 = CACHE_DIR / f"step_results_24{cache_tag}.pkl"
    cache_36 = CACHE_DIR / f"step_results_36{cache_tag}.pkl"

    if cache_24.exists() and cache_36.exists():
        log(f"[3-step] 从缓存加载 KS_24 + KS_36{cache_tag}")
        with open(cache_24, "rb") as f:
            res24 = pickle.load(f)
        with open(cache_36, "rb") as f:
            res36 = pickle.load(f)
        return res24, res36

    log(f"[3-step] 双窗口相邻 KS: KS_24 (win_h=24) + KS_36 (win_h=36){cache_tag}...")
    t = time.time()
    res24, res36 = {}, {}
    for i, c in enumerate(channels, 1):
        en = float((eff_neff or {}).get(c, 1.0))   # 有效 n_eff，按通道
        det24 = AdjacentKSStepDetector(win_h=24, alpha=0.001, neff_ratio=en)
        det36 = AdjacentKSStepDetector(win_h=36, alpha=0.001, neff_ratio=en)
        res24[c] = det24.score(resid_h[c].rename(c))
        res36[c] = det36.score(resid_h[c].rename(c))
        if i % 4 == 0:
            log(f"    [{time.time()-t:.1f}s] {i}/{len(channels)} 通道完成")
    log(f"    [{time.time()-t:.1f}s] 完成")
    with open(cache_24, "wb") as f:
        pickle.dump(res24, f)
    with open(cache_36, "wb") as f:
        pickle.dump(res36, f)
    return res24, res36


def confirmation_gate_fusion(Q_24: pd.Series, Q_36: pd.Series) -> tuple[pd.Series, pd.Series]:
    """确认门控融合（PDF §4.2）。

    if Q_24 <= 2.5: Q_final = max(Q_24, Q_36)  # 取"较好"判定，抑制短期扰动
    else:           Q_final = Q_24              # 正常区间直接用24h结果

    step_confirmed = (Q_24 <= 2.0) & (Q_36 <= 2.5)
    """
    Q_final = Q_24.copy()
    mask = Q_24 <= 2.5
    Q_final[mask] = pd.concat([Q_24[mask], Q_36.reindex(Q_24.index)[mask]], axis=1).max(axis=1)
    step_confirmed = (Q_final <= 2.0).astype(np.int8)
    return Q_final.clip(1, 5), step_confirmed


def run_drift_detector(resid_h: pd.DataFrame, channels: list,
                       cache_tag: str = "") -> dict:
    cache_path = CACHE_DIR / f"drift_results{cache_tag}.pkl"
    if cache_path.exists():
        log(f"[3-drift] 从缓存加载{cache_tag}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    log("[3-drift] PLS 虚拟传感器漂移检测器 (train=21天)...")
    t = time.time()
    detector = PLSVirtualSensorDetector(n_components=3, train_days=21)
    results = {}
    for i, c in enumerate(channels, 1):
        peers = engineered_peers(c, list(resid_h.columns))
        if len(peers) < 2:
            peers = [x for x in resid_h.columns if x != c][:6]
        try:
            results[c] = detector.score(resid_h, target=c, peer_cols=peers)
        except Exception as e:
            log(f"    ! PLS 对 {c} 失败: {e}, 使用零填充")
            empty = pd.Series(0.0, index=resid_h.index)
            from src.detectors.base import DetectorResult
            results[c] = DetectorResult(c, "pls_fallback", resid_h.index,
                                        empty, empty.astype(np.int8), {})
        if i % 3 == 0:
            log(f"    [{time.time()-t:.1f}s] {i}/{len(channels)} 通道完成")
    log(f"    [{time.time()-t:.1f}s] 完成")
    with open(cache_path, "wb") as f:
        pickle.dump(results, f)
    return results


def run_freeze_detector(df_min: pd.DataFrame, channels: list) -> dict:
    """在 1min 原始数据上运行 CompositeFreezeDetector()。
    严格遵守 d1_pipeline.py 规格: freeze 必须在分钟级数据上运行。
    metadata["components"] 为分钟级 DataFrame，调用方需 .resample("1h").max() 聚合。
    """
    cache_path = CACHE_DIR / "freeze_results_min.pkl"
    if cache_path.exists():
        log(f"[3-freeze] 从缓存加载 (分钟级)")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    log(f"[3-freeze] CompositeFreezeDetector() — 在 {len(df_min)} 行分钟数据上运行...")
    t = time.time()
    detector = CompositeFreezeDetector()  # 使用默认分钟级参数
    results = {}
    for i, c in enumerate(channels, 1):
        results[c] = detector.score(df_min[c].rename(c))
        if i % 4 == 0:
            log(f"    [{time.time()-t:.1f}s] {i}/{len(channels)} 通道完成")
    log(f"    [{time.time()-t:.1f}s] 完成")
    with open(cache_path, "wb") as f:
        pickle.dump(results, f)
    return results


def run_regime_detector(resid_h: pd.DataFrame, channels: list,
                        eff_neff: dict | None = None,
                        cache_tag: str = "") -> dict:
    cache_path = CACHE_DIR / f"regime_results{cache_tag}.pkl"
    if cache_path.exists():
        log(f"[3-regime] 从缓存加载{cache_tag}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    log(f"[3-regime] 两层制度检测器 (W1+KS, ref=90天, win=7天){cache_tag}...")
    t = time.time()
    results = {}
    for i, c in enumerate(channels, 1):
        en = float((eff_neff or {}).get(c, 1.0))   # 有效 n_eff，按通道（W1/KS×√n_eff）
        detector = TwoTierRegimeDetector(
            ref_days=90, w1_win_days=7, ks_win_days=7,
            w1_update_h=6, ks_update_h=24, ks_alpha=0.001, n_bootstrap=100,
            neff_ratio=en)
        results[c] = detector.score(resid_h[c].rename(c))
        if i % 3 == 0:
            log(f"    [{time.time()-t:.1f}s] {i}/{len(channels)} 通道完成")
    log(f"    [{time.time()-t:.1f}s] 完成")
    with open(cache_path, "wb") as f:
        pickle.dump(results, f)
    return results


# ─── 4. 映射到子分数 [1–5] ────────────────────────────────────────────────────
def compute_subscores(spike_results, step_results_24, step_results_36, drift_results,
                       freeze_results, regime_results,
                       spike_rate_6h, channels, mapping_cfg) -> tuple[dict, dict]:
    """返回 (subs, step_confirmed_dict)。
    subs[c]["Q_step"] 为 Q_step_final（确认门控融合后）。
    step_confirmed_dict[c] 为 step_confirmed 标志序列（供状态机两级触发）。
    """
    log("[4] 将检测器输出映射到 [1–5] 子分数（双窗 Q_step_final）...")
    subs = {}
    step_confirmed_dict = {}
    for c in channels:
        Q_spike = apply_mapping(spike_rate_6h[c].rename("spike_rate_6h"),
                                mapping_cfg.spike)

        # KS_24 → Q_step_24; KS_36 → Q_step_36; 确认门控 → Q_step_final
        Q_step_24 = apply_mapping(
            step_results_24[c].raw_score.fillna(0.08).rename("ks_statistic"),
            mapping_cfg.step)
        Q_step_36 = apply_mapping(
            step_results_36[c].raw_score.fillna(0.08).rename("ks_statistic"),
            mapping_cfg.step)
        Q_step_final, step_confirmed = confirmation_gate_fusion(Q_step_24, Q_step_36)
        step_confirmed_dict[c] = step_confirmed

        drift_z = drift_results[c].raw_score.fillna(0.0).rename("pls_residual_z")
        Q_drift = apply_mapping(drift_z, mapping_cfg.drift)

        # 冻结: 分钟级 components → resample("1h").max() → 与 d1_pipeline.py 完全一致
        comp_min = freeze_results[c].metadata.get("components")
        if comp_min is not None and len(comp_min) > 0:
            comp_h = comp_min.resample("1h").max()
            rle_col  = comp_h.get("rle_run_min",   pd.Series(0.0, index=comp_h.index))
            relv_col = comp_h.get("rel_var",        pd.Series(1.0, index=comp_h.index))
            uniq_col = comp_h.get("unique_ratio",   pd.Series(1.0, index=comp_h.index))
        else:
            rle_col  = pd.Series(0.0, index=Q_step_final.index)
            relv_col = pd.Series(1.0, index=Q_step_final.index)
            uniq_col = pd.Series(1.0, index=Q_step_final.index)

        Q_rle  = apply_mapping(rle_col.rename("rle_max_duration_min"),  mapping_cfg.freeze.rle)
        Q_lv   = apply_mapping(relv_col.rename("relvar_to_ref"),         mapping_cfg.freeze.low_var)
        Q_uq   = apply_mapping(uniq_col.rename("unique_ratio"),          mapping_cfg.freeze.unique)
        cw = mapping_cfg.freeze.combined_weights
        Q_freeze = (cw["rle"]*Q_rle + cw["low_var"]*Q_lv + cw["unique"]*Q_uq).clip(1, 5)

        Q_regime = apply_mapping(regime_results[c].raw_score.fillna(0.0).rename("w1_normalised"),
                                 mapping_cfg.regime)

        idx = Q_step_final.index
        subs[c] = {
            "Q_spike":  Q_spike.reindex(idx).ffill().bfill().clip(1, 5),
            "Q_step":   Q_step_final.reindex(idx).ffill().bfill().clip(1, 5),  # Q_step_final
            "Q_drift":  Q_drift.reindex(idx).ffill().bfill().clip(1, 5),
            "Q_freeze": Q_freeze.reindex(idx).ffill().bfill().clip(1, 5),
            "Q_regime": Q_regime.reindex(idx).ffill().bfill().clip(1, 5),
        }
    return subs, step_confirmed_dict


# ─── 5. STRICT V1 D1 聚合（无状态机）─────────────────────────────────────────
def aggregate_d1_strict(subs: dict, channels: list, weights: dict,
                         lambda_blend: float) -> pd.DataFrame:
    log("[5] STRICT V1 聚合 (加权混合 + Veto，无冷却状态机)...")
    D1_dict = {}
    for c in channels:
        Q_sp = subs[c]["Q_spike"]
        Q_st = subs[c]["Q_step"]
        Q_dr = subs[c]["Q_drift"]
        Q_fr = subs[c]["Q_freeze"]
        Q_re = subs[c]["Q_regime"]

        D1_base = (weights["spike"]  * Q_sp +
                   weights["step"]   * Q_st +
                   weights["drift"]  * Q_dr +
                   weights["freeze"] * Q_fr +
                   weights["regime"] * Q_re)
        min_q = pd.concat([Q_sp, Q_st, Q_dr, Q_fr, Q_re], axis=1).min(axis=1)
        D1_pre = lambda_blend * D1_base + (1 - lambda_blend) * min_q
        D1 = D1_pre.clip(1.0, 5.0)

        # Veto 规则 (STRICT V1)
        D1 = D1.where(Q_fr > 2.0, D1.clip(upper=2.0))
        D1 = D1.where(Q_re > 2.0, D1.clip(upper=2.5))

        D1_dict[c] = D1.clip(1.0, 5.0)

    D1_df = pd.DataFrame(D1_dict)
    log(f"    D1 均值: {D1_df.mean().mean():.3f}, "
        f"范围: {D1_df.min().min():.2f} ~ {D1_df.max().max():.2f}")
    return D1_df


# ─── 6. 将子分数字典重整为 DataFrame 格式 ─────────────────────────────────────
def subs_to_dataframes(subs: dict, channels: list) -> dict:
    q_names = ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]
    result = {}
    for q in q_names:
        result[q] = pd.DataFrame({c: subs[c][q] for c in channels})
    return result


# ─── 主函数 ────────────────────────────────────────────────────────────────────
def main():
    t_total = time.time()
    log("=" * 70)
    log("STRICT V1 数据加载 — 从真实 Excel 文件计算子分数")
    log("规格: spike/freeze 在 1min 数据上检测，step/drift/regime 在小时残差上检测")
    log("=" * 70)

    cfg = load_project_config()
    weights      = cfg.rules["aggregation"]["weights"]
    lambda_blend = cfg.rules["aggregation"]["lambda_blend"]
    log(f"[cfg] weights={weights}, lambda={lambda_blend}")

    # ── 步骤 1: 加载 & 对齐 (返回 df_h 和 df_min)
    df_h, df_min = load_and_align()
    log(f"    df_h: {df_h.shape}, df_min: {df_min.shape}")

    # ── 步骤 2: 残差 / 创新输入源
    resid_h_all = compute_residuals(df_h)   # D1 自带谐波基线（旧路径 / fallback）

    # §1.1 桥接：改输入源 + scoring_mode 分支（audit §3 ROI #1）
    if USE_DECOMP_11:
        log("[2+] §1.1 桥接：以 §1.1 白化残差/创新 + whiteness_manifest 替换 D1 谐波输入源")
        bridge = load_decomposition_11(channels=ALL_CHANNELS,
                                       target_index_h=resid_h_all.index)
        log(f"    {summarise(bridge)}")
        resid_h_11   = bridge["resid_h"]          # §1.1 残差（drift / 状态机残差检验）
        det_in_h     = bridge["detector_input_h"] # iid→创新 / autocorr→残差（step/regime/PELT）
        scoring_mode = bridge["scoring_mode"]
        neff_map     = bridge["neff"]
        eff_neff = {c: effective_neff(c, scoring_mode, neff_map) for c in ALL_CHANNELS}
        resid_for_drift = resid_h_11   # PLS 多变量稳健 → §1.1 残差（全通道含 peer）
        step_in   = det_in_h           # i.i.d. 敏感 → 路由输入
        regime_in = det_in_h
        cache_tag = "_w11"
        for c in SCORED_CHANNELS:
            log(f"      {c:8s} mode={scoring_mode[c]:14s} eff_neff={eff_neff[c]:.4f} "
                f"deflate={eff_neff[c]**0.5:.3f}")
    else:
        log("[2+] 旧路径：D1 自带谐波残差（未白化）— 设 D1_USE_DECOMP_11=0")
        scoring_mode = {c: "iid" for c in ALL_CHANNELS}
        neff_map = {c: 1.0 for c in ALL_CHANNELS}
        eff_neff = {c: 1.0 for c in ALL_CHANNELS}
        resid_for_drift = resid_h_all
        step_in = resid_h_all
        regime_in = resid_h_all
        cache_tag = ""

    # ── 步骤 3: 运行检测器
    # spike/freeze 在分钟级原始数据上运行（不受白化影响；spike 已修因果窗泄漏 audit §2①）
    spike_results  = run_spike_detector(df_min[SCORED_CHANNELS], SCORED_CHANNELS)
    spike_rate_6h  = compute_spike_rate(spike_results, SCORED_CHANNELS)

    # step: 双窗口 KS_24 + KS_36，i.i.d. 敏感 → §1.1 路由输入 + 按通道 n_eff 去敏
    step_results_24, step_results_36 = run_step_detector(
        step_in[SCORED_CHANNELS], SCORED_CHANNELS, eff_neff=eff_neff, cache_tag=cache_tag)
    # drift: PLS 多变量稳健 → §1.1 残差（全通道，含 support 作 peer）
    drift_results  = run_drift_detector(resid_for_drift, SCORED_CHANNELS, cache_tag=cache_tag)
    freeze_results = run_freeze_detector(df_min[SCORED_CHANNELS], SCORED_CHANNELS)
    # regime: 两层 W1+KS，i.i.d. 敏感 → §1.1 路由输入 + 按通道 n_eff 去敏
    regime_results = run_regime_detector(
        regime_in[SCORED_CHANNELS], SCORED_CHANNELS, eff_neff=eff_neff, cache_tag=cache_tag)

    # ── 步骤 4: 子分数映射（返回 subs 和 step_confirmed_dict）
    subs_per_ch, step_confirmed_dict = compute_subscores(
        spike_results, step_results_24, step_results_36, drift_results,
        freeze_results, regime_results,
        spike_rate_6h, SCORED_CHANNELS, cfg.mapping)

    # ── 步骤 5: STRICT V1 D1 聚合
    D1_v1 = aggregate_d1_strict(subs_per_ch, SCORED_CHANNELS, weights, lambda_blend)

    # ── 步骤 6: 整理检测器原始输出（均聚合/对齐到小时索引）
    log("[6] 整理检测器原始输出 DataFrame...")
    idx = D1_v1.index
    detectors_raw = {
        # KS_24 (win_h=12) — 主检测，用于状态机 ks_stat 事件幅度
        "ks_statistic_hourly": pd.DataFrame(
            {c: step_results_24[c].raw_score.reindex(idx).ffill().bfill().fillna(0.08)
             for c in SCORED_CHANNELS}),
        # KS_36 (win_h=18) — 持续确认窗
        "ks_statistic_36h": pd.DataFrame(
            {c: step_results_36[c].raw_score.reindex(idx).ffill().bfill().fillna(0.08)
             for c in SCORED_CHANNELS}),
        # step_confirmed_flag — 两级触发：confirmed step 才进 Refractory
        "step_confirmed_flag": pd.DataFrame(
            {c: step_confirmed_dict[c].reindex(idx).fillna(0).astype(np.int8)
             for c in SCORED_CHANNELS}),
        "w1_normalised_hourly": pd.DataFrame(
            {c: regime_results[c].metadata.get("w1_norm_series",
                regime_results[c].raw_score).reindex(idx).ffill().bfill().fillna(0.0)
             for c in SCORED_CHANNELS}),
        # Hampel z 从分钟级聚合到小时最大值
        "hampel_z_hourly_max": pd.DataFrame(
            {c: spike_results[c].raw_score.resample("1h").max()
                .reindex(idx).ffill().bfill().fillna(0.0)
             for c in SCORED_CHANNELS}),
        "pls_residual_z_hourly": pd.DataFrame(
            {c: drift_results[c].raw_score.reindex(idx).ffill().bfill().fillna(0.0)
             for c in SCORED_CHANNELS}),
        "spike_rate_6h_input": pd.DataFrame(
            {c: spike_rate_6h[c].reindex(idx).ffill().bfill().fillna(0.01)
             for c in SCORED_CHANNELS}),
    }
    # 冻结分量：从分钟级 components 聚合到小时（与 compute_subscores 保持一致用 max）
    for freeze_key, comp_col, default in [
        ("freeze_rle_run_min", "rle_run_min", 0.0),
        ("freeze_rel_var",     "rel_var",     1.0),
        ("freeze_unique_ratio","unique_ratio", 1.0),
    ]:
        rows = {}
        for c in SCORED_CHANNELS:
            comp_min = freeze_results[c].metadata.get("components")
            if comp_min is not None and comp_col in comp_min.columns:
                rows[c] = (comp_min[comp_col].resample("1h").max()
                           .reindex(idx).ffill().bfill().fillna(default))
            else:
                rows[c] = pd.Series(default, index=idx)
        detectors_raw[freeze_key] = pd.DataFrame(rows)

    # ── 步骤 7: 将子分数重整为 DataFrame 格式
    log("[7] 将子分数转为 DataFrame 格式 ...")
    subs_v1 = subs_to_dataframes(subs_per_ch, SCORED_CHANNELS)

    # 打印各通道 D1 汇总
    log("\n[汇总] 各通道 D1 均值:")
    for c in SCORED_CHANNELS:
        s  = subs_v1["Q_spike"][c].mean()
        st = subs_v1["Q_step"][c].mean()
        dr = subs_v1["Q_drift"][c].mean()
        fr = subs_v1["Q_freeze"][c].mean()
        re = subs_v1["Q_regime"][c].mean()
        d1 = D1_v1[c].mean()
        log(f"  {c:10s}  D1={d1:.3f}  spike={s:.2f} step={st:.2f} "
            f"drift={dr:.2f} freeze={fr:.2f} regime={re:.2f}")

    # ── 步骤 8: 保存 pkl 文件
    log("\n[8] 保存 pkl 文件...")
    v1_payload = {
        "subs_v1":   subs_v1,
        "D1_v1":     D1_v1,
        "detectors": detectors_raw,
        # §1.1 contract (audit §3): downstream PELT / cooldown read these to
        # route per-channel input + n_eff. Absent ⇒ legacy i.i.d. behaviour.
        "decomp_11": {
            "active":       bool(USE_DECOMP_11),
            "scoring_mode": scoring_mode,
            "neff":         neff_map,
            "eff_neff":     eff_neff,
        },
    }
    out1 = _ROOT / "strict_v1_inputs.pkl"
    with open(out1, "wb") as f:
        pickle.dump(v1_payload, f)
    log(f"    strict_v1_inputs.pkl: {out1.stat().st_size/1e6:.1f} MB")

    # resid_h: §1.1 residual under the bridge (state-machine residual check),
    #          harmonic residual under the legacy path.
    resid_h_scored = resid_for_drift[SCORED_CHANNELS].reindex(idx).ffill().bfill()
    # whitened_input_h: per-channel routed series (innovation for iid, residual
    # for autocorr_aware) — what downstream PELT should segment instead of the
    # raw residual. Under the legacy path this equals resid_h_scored.
    whitened_input_h = step_in[SCORED_CHANNELS].reindex(idx).ffill().bfill()
    raw_payload = {
        "df_h":    df_h.reindex(idx).ffill().bfill(),
        "resid_h": resid_h_scored,
        "whitened_input_h": whitened_input_h,
        "eff_neff": eff_neff,
        "scoring_mode": scoring_mode,
    }
    out2 = _ROOT / "raw_hourly.pkl"
    with open(out2, "wb") as f:
        pickle.dump(raw_payload, f)
    log(f"    raw_hourly.pkl: {out2.stat().st_size/1e6:.1f} MB")

    elapsed = time.time() - t_total
    log(f"\n{'='*70}")
    log(f"完成! 总耗时 {elapsed/60:.1f} 分钟")
    log(f"数据时间范围: {idx[0]} → {idx[-1]}, 共 {len(idx)} 小时")
    log(f"D1 v1.0 均值: {D1_v1.mean().mean():.3f}")
    log(f"{'='*70}")


if __name__ == "__main__":
    main()
