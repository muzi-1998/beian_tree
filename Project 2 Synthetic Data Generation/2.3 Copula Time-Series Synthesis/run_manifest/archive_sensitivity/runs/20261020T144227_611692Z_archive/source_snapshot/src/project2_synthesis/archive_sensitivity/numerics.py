"""Reversible prototype, explicit atoms and two-dimensional copula baselines."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, stats


def block_slices(blocks: np.ndarray) -> list[slice]:
    blocks = np.asarray(blocks)
    if len(blocks) == 0:
        return []
    starts = np.r_[0, np.flatnonzero(blocks[1:] != blocks[:-1]) + 1]
    ends = np.r_[starts[1:], len(blocks)]
    return [slice(int(a), int(b)) for a, b in zip(starts, ends)]


def transform(x: np.ndarray, kind: str) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite transform input")
    if kind == "identity":
        return x.copy()
    if kind == "log1p" and (x >= 0).all():
        return np.log1p(x)
    raise ValueError("Unknown transform or inadmissible log1p input")


def inverse_transform(y: np.ndarray, kind: str) -> np.ndarray:
    if kind == "identity":
        return np.asarray(y).copy()
    if kind == "log1p":
        with np.errstate(over="raise", invalid="raise"):
            return np.expm1(y)
    raise ValueError("Unknown transform")


def design_matrix(minutes: np.ndarray, temperature: np.ndarray, periods: list[int],
                  state: dict | None = None) -> tuple[np.ndarray, dict]:
    if len(set(periods)) != len(periods) or any(p <= 0 for p in periods):
        raise ValueError("Harmonic periods must be unique and positive")
    minutes, temperature = np.asarray(minutes, float), np.asarray(temperature, float)
    if state is None:
        state = {"time_center": float(minutes.mean()), "time_scale": float(minutes.std()),
                 "T_center": float(temperature.mean()), "T_scale": float(temperature.std()),
                 "period_minutes": periods}
    if state["time_scale"] <= 0 or state["T_scale"] <= 0:
        raise ValueError("Condition basis has constant time/temperature; do not invent a full-rank fit")
    if state["period_minutes"] != periods:
        raise ValueError("Harmonics differ from fitted state")
    cols = [np.ones(len(minutes)), (minutes - state["time_center"]) / state["time_scale"],
            (temperature - state["T_center"]) / state["T_scale"]]
    for period in periods:
        cols.extend([np.sin(2 * np.pi * minutes / period), np.cos(2 * np.pi * minutes / period)])
    matrix = np.column_stack(cols)
    if not np.isfinite(matrix).all():
        raise ValueError("Nonfinite condition matrix")
    return matrix, state


def fit_temporal(y: np.ndarray, design: np.ndarray, blocks: np.ndarray, order: int) -> dict:
    if order not in {0, 1}:
        raise ValueError("This pilot implements only ARMA(0,0) and ARMA(1,0)")
    beta, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank != design.shape[1]:
        raise ValueError("Rank-deficient deterministic basis")
    baseline = design @ beta
    residual = y - baseline
    eligible = np.ones(len(y), dtype=bool)
    first = np.r_[True, blocks[1:] != blocks[:-1]]
    phi = np.zeros(y.shape[1])
    if order:
        eligible[first] = False
        previous = np.roll(residual, 1, axis=0)
        denom = np.sum(previous[eligible] ** 2, axis=0)
        if np.any(denom <= 0):
            raise ValueError("Degenerate AR fit support")
        phi = np.sum(previous[eligible] * residual[eligible], axis=0) / denom
        if not np.isfinite(phi).all() or np.any(np.abs(phi) >= 1):
            raise ValueError(f"Unstable AR candidate, retained as failure: phi={phi.tolist()}")
    innovations = residual.copy()
    if order:
        innovations[eligible] -= previous[eligible] * phi
        innovations[first] = np.nan
    return {"beta": beta, "phi": phi, "baseline": baseline, "residual": residual,
            "innovations": innovations, "eligible": eligible, "order": order,
            "initial_positions": np.flatnonzero(first), "initial_residuals": residual[first].copy()}


def reconstruct(fit: dict, blocks: np.ndarray) -> np.ndarray:
    residual = np.empty_like(fit["residual"])
    for block in block_slices(blocks):
        if fit["order"] == 0:
            residual[block] = fit["innovations"][block]
        else:
            residual[block.start] = fit["residual"][block.start]
            for i in range(block.start + 1, block.stop):
                residual[i] = fit["phi"] * residual[i - 1] + fit["innovations"][i]
    return fit["baseline"] + residual


@dataclass
class EmpiricalMargin:
    sorted_values: np.ndarray

    @classmethod
    def fit(cls, values: np.ndarray) -> "EmpiricalMargin":
        values = np.asarray(values, dtype=float)
        if not len(values) or not np.isfinite(values).all():
            raise ValueError("Empirical margin requires finite observations")
        return cls(np.sort(values))

    def pit(self, values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        left = np.searchsorted(self.sorted_values, values, side="left")
        right = np.searchsorted(self.sorted_values, values, side="right")
        if np.any(right == left):
            raise ValueError("Training randomized PIT requires observed support values")
        u = (left + rng.random(len(values)) * (right - left)) / len(self.sorted_values)
        return np.clip(u, np.nextafter(0., 1.), np.nextafter(1., 0.))

    def ppf(self, u: np.ndarray) -> np.ndarray:
        u = np.asarray(u, dtype=float)
        if not np.isfinite(u).all() or np.any((u < 0) | (u > 1)):
            raise ValueError("Quantile arguments must be finite and inside [0,1]")
        index = np.minimum((u * len(self.sorted_values)).astype(int), len(self.sorted_values) - 1)
        return self.sorted_values[index]


def copula_logpdf(u: np.ndarray, family: str, rho: float = 0., df: float | None = None) -> np.ndarray:
    if not np.isfinite(u).all() or np.any((u <= 0) | (u >= 1)):
        raise ValueError("Copula observations must be inside the open unit square")
    if family == "independence":
        return np.zeros(len(u))
    if abs(rho) >= 1:
        raise ValueError("Singular copula correlation")
    matrix = np.array([[1., rho], [rho, 1.]])
    if family == "Gaussian":
        z = stats.norm.ppf(u)
        return stats.multivariate_normal.logpdf(z, cov=matrix) - stats.norm.logpdf(z).sum(axis=1)
    if family == "Student_t" and df is not None and df > 0:
        z = stats.t.ppf(u, df)
        return stats.multivariate_t.logpdf(z, shape=matrix, df=df) - stats.t.logpdf(z, df).sum(axis=1)
    raise ValueError("Unknown family or missing Student t degrees of freedom")


def fit_copulas(u: np.ndarray, df_bounds: list[float]) -> list[dict]:
    tau = float(stats.kendalltau(u[:, 0], u[:, 1]).statistic)
    rho = float(np.sin(np.pi * tau / 2))
    models = []
    for family in ["independence", "Gaussian", "Student_t"]:
        model = {"family": family, "rho": 0. if family == "independence" else rho,
                 "df": None, "fit_status": "PASS", "archive_pairs": len(u), "empirical_tau": tau,
                 "selection": "none; conditional exploratory fit, no IID likelihood inference"}
        try:
            if not np.isfinite(rho) or abs(rho) >= 1:
                raise ValueError("Undefined or singular rank correlation")
            if family == "Student_t":
                objective = lambda nu: -float(copula_logpdf(u, family, rho, nu).sum())
                fit = optimize.minimize_scalar(objective, bounds=tuple(df_bounds), method="bounded")
                if not fit.success or not np.isfinite(fit.fun):
                    raise ValueError("Student t numerical search did not converge")
                model.update(df=float(fit.x), numeric_df_bounds=df_bounds,
                             df_distance_to_bound=float(min(fit.x - df_bounds[0], df_bounds[1] - fit.x)),
                             optimizer_evaluations=int(fit.nfev))
            model["training_pseudo_loglikelihood"] = float(copula_logpdf(u, family, model["rho"], model["df"]).sum())
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            model.update(fit_status="FAIL", reason=str(exc))
        models.append(model)
    return models


def draw_copula(model: dict, n: int, rng: np.random.Generator) -> tuple[np.ndarray, int]:
    if model["fit_status"] != "PASS":
        raise ValueError("Cannot sample a failed copula fit")
    family = model["family"]
    if family == "independence":
        u = rng.random((n, 2))
    else:
        matrix = [[1., model["rho"]], [model["rho"], 1.]]
        z = rng.multivariate_normal(np.zeros(2), matrix, size=n)
        if family == "Gaussian":
            u = stats.norm.cdf(z)
        elif family == "Student_t":
            z /= np.sqrt(rng.chisquare(model["df"], size=n) / model["df"])[:, None]
            u = stats.t.cdf(z, model["df"])
        else:
            raise ValueError("Unknown fitted copula")
    clips = int(((u <= 0) | (u >= 1)).sum())
    return np.clip(u, np.nextafter(0., 1.), np.nextafter(1., 0.)), clips


def lagged_correlation(a: np.ndarray, b: np.ndarray, blocks: np.ndarray, lag: int) -> tuple[float | None, int]:
    if lag < 0:
        return lagged_correlation(b, a, blocks, -lag)
    if lag >= len(a):
        return None, 0
    if lag == 0:
        left, right, same = a, b, np.ones(len(a), bool)
    else:
        left, right, same = a[:-lag], b[lag:], blocks[:-lag] == blocks[lag:]
    valid = same & np.isfinite(left) & np.isfinite(right)
    n = int(valid.sum())
    if n < 2 or np.std(left[valid]) == 0 or np.std(right[valid]) == 0:
        return None, n
    return float(np.corrcoef(left[valid], right[valid])[0, 1]), n
