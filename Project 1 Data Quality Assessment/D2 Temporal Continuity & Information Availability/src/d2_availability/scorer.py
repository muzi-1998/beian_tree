"""
src/d2_availability/scorer.py
==============================
评分核心:Q_TI / Q_GS / Q_FA 三个独立可测的 Scorer 类 + D2Aggregator。
完全消费 D2Config,无全局变量,可单独单测。

依据:
  - 方案 v2.0 §3.2 子分定义
  - 方案 v2.0 §4 聚合规则
  - 工程目录 v2.0 §3.3 (TemporalIntegrityScorer 等)
"""
from __future__ import annotations
from typing import Dict, Tuple
import numpy as np
import pandas as pd

from ..utils.config_loader import D2Config


# ─── 基础映射函数 ─────────────────────────────────────────────────────────────

def piecewise_score(x: pd.Series, breaks: list) -> pd.Series:
    """分段线性,异常越强 → 分数越低。breaks 为 4 个递增阈值,定义 5 个区间。"""
    x = x.copy().fillna(x.median())
    s = pd.Series(np.nan, index=x.index, dtype=float)
    b0, b1, b2, b3 = breaks
    s[x <= b0]              = 5.0
    m = (x > b0) & (x <= b1); s[m] = 4.0 + (b1 - x[m]) / (b1 - b0)
    m = (x > b1) & (x <= b2); s[m] = 3.0 + (b2 - x[m]) / (b2 - b1)
    m = (x > b2) & (x <= b3); s[m] = 2.0 + (b3 - x[m]) / (b3 - b2)
    s[x > b3]               = 1.0
    return s.clip(1.0, 5.0)


# ─── 三个独立 Scorer ──────────────────────────────────────────────────────────

class TemporalIntegrityScorer:
    """Q_TI:时间轴整体质量。"""
    def __init__(self, cfg: D2Config):
        self.cfg = cfg
        self.b = cfg.mapping.piecewise_breaks["Q_TI"]
        self.w = cfg.mapping.Q_TI_weights

    def score(self, st: pd.DataFrame) -> pd.Series:
        Q_m  = piecewise_score(st["missing_rate"],      self.b["missing_rate"])
        Q_d  = piecewise_score(st["duplicate_rate"],    self.b["duplicate_rate"])
        Q_o  = piecewise_score(st["out_of_order_rate"], self.b["out_of_order"])
        Q_i  = piecewise_score(st["irregular_rate"],    self.b["irregular_rate"])
        return (self.w["missing"]      * Q_m +
                self.w["duplicate"]    * Q_d +
                self.w["out_of_order"] * Q_o +
                self.w["irregular"]    * Q_i).clip(1, 5)


class GapSeverityScorer:
    """Q_GS:断点严重度(P1-A 修订:含 P95_gap 三项)。"""
    def __init__(self, cfg: D2Config):
        self.cfg = cfg
        self.b = cfg.mapping.piecewise_breaks["Q_GS"]
        self.w = cfg.mapping.Q_GS_weights

    def score(self, st: pd.DataFrame) -> pd.Series:
        Q_L = piecewise_score(st["L_max_min"],     self.b["L_max_min"])
        Q_P = piecewise_score(st["P95_gap_min"],   self.b["P95_gap_min"])
        Q_C = piecewise_score(st["gap_run_count"], self.b["gap_run_count"])
        return (self.w["L_max"]         * Q_L +
                self.w["P95_gap"]       * Q_P +
                self.w["gap_run_count"] * Q_C).clip(1, 5)


class FreezeAvailabilityScorer:
    """Q_FA:主证据 info_empty + 辅助证据 response_loss 加重融合。"""
    def __init__(self, cfg: D2Config):
        self.cfg = cfg
        self.b   = cfg.mapping.piecewise_breaks["Q_FA"]
        self.rule = cfg.mapping.Q_FA_rule

    def score(
        self,
        st: pd.DataFrame,
        rl_rate: pd.Series,
        allow_response_loss: bool = True,
    ) -> Tuple[pd.Series, pd.Series]:
        Q_main = piecewise_score(st["info_empty_cov"], self.b["info_empty_cov"])
        Q_FA   = Q_main.copy()
        rl_aligned = rl_rate.reindex(Q_main.index).fillna(0.0)
        downgrade = (
            allow_response_loss
            & (rl_aligned > self.rule["aggravation"]["trigger_above"])
            & (Q_main <= self.rule["aggravation"]["main_threshold"])
        )
        Q_FA[downgrade] = (Q_main[downgrade] - self.rule["aggravation"]["downgrade_amount"]).clip(lower=1.0)
        return Q_FA, Q_main


# ─── 主聚合器 ─────────────────────────────────────────────────────────────────

class D2Aggregator:
    """方案 §4.2 + §4.3:加权 + 非补偿 + veto 上限。"""
    def __init__(self, cfg: D2Config, calibration: dict):
        self.cfg = cfg
        self.calib = calibration
        self.w = cfg.mapping.aggregation["weights"]
        self.lam = cfg.mapping.aggregation["lambda_blend"]
        self.veto = cfg.mapping.veto_rules
        self.floor = cfg.mapping.safety_floor

    def _veto_value(self, key: str) -> float:
        """读取 calibration 中的 veto 阈值,若退化则回落 safety_floor。"""
        raw = self.calib.get("veto_thresholds", {}).get(key)
        floor_v = self.floor.get(key, 0)
        if isinstance(raw, dict):
            v = raw.get("value", floor_v)
            return float(v) if float(v) > 0 else float(floor_v)
        if raw is None or float(raw) <= 0:
            return float(floor_v)
        return float(raw)

    def aggregate(self, Q_TI, Q_GS, Q_FA, st: pd.DataFrame) -> pd.DataFrame:
        D2_base = (self.w["Q_TI"]*Q_TI + self.w["Q_GS"]*Q_GS + self.w["Q_FA"]*Q_FA).clip(1, 5)
        Q_min   = pd.concat([Q_TI, Q_GS, Q_FA], axis=1).min(axis=1)
        D2_pre  = (self.lam * D2_base + (1 - self.lam) * Q_min).clip(1, 5)

        D2_total = D2_pre.copy()
        veto_flag = pd.Series(False, index=D2_pre.index)
        veto_reason = pd.Series("", index=D2_pre.index)

        # 各 veto 子句
        vL = self._veto_value("L_max_minutes")
        m  = st["L_max_min"] > vL
        D2_total[m] = D2_total[m].clip(upper=self.veto["Lmax_p99"]["upper_cap"])
        veto_flag[m] = True; veto_reason[m] = veto_reason[m] + "L_max_p99|"

        vM = self._veto_value("missing_rate")
        m  = st["missing_rate"] > vM
        D2_total[m] = D2_total[m].clip(upper=self.veto["missing_p99"]["upper_cap"])
        veto_flag[m] = True; veto_reason[m] = veto_reason[m] + "missing_p99|"

        vI = self._veto_value("irregular_rate")
        m  = st["irregular_rate"] > vI
        D2_total[m] = D2_total[m].clip(upper=self.veto["irregular_p95"]["upper_cap"])
        veto_flag[m] = True; veto_reason[m] = veto_reason[m] + "irregular_p95|"

        m  = Q_FA <= self.veto["freeze_severe"]["threshold"]
        D2_total[m] = D2_total[m].clip(upper=self.veto["freeze_severe"]["upper_cap"])
        veto_flag[m] = True; veto_reason[m] = veto_reason[m] + "freeze_severe|"

        veto_reason = veto_reason.str.rstrip("|")
        D2_total = D2_total.clip(1, 5)

        return pd.DataFrame({
            "Q_TI": Q_TI, "Q_GS": Q_GS, "Q_FA": Q_FA,
            "D2_base": D2_base, "D2_pre": D2_pre, "D2_total": D2_total,
            "veto_flag": veto_flag.astype(int), "veto_reason": veto_reason,
        })
