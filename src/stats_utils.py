"""Small statistical helpers shared by the analytics modules."""
from __future__ import annotations

import numpy as np
from scipy import stats


def wilson_ci(successes, trials, z: float = 1.96):
    """Wilson score interval for a binomial proportion. Works on scalars or arrays."""
    k = np.asarray(successes, dtype=float)
    n = np.asarray(trials, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(n > 0, k / n, np.nan)
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return np.clip(centre - half, 0, 1), np.clip(centre + half, 0, 1)


def two_proportion_ztest(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """Two-sided z-test for p1 == p2. Returns (z, p_value)."""
    if min(n1, n2) == 0:
        return np.nan, np.nan
    p_pool = (k1 + k2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return np.nan, np.nan
    z = (k1 / n1 - k2 / n2) / se
    return float(z), float(2 * stats.norm.sf(abs(z)))


def safe_div(a, b):
    return float(a) / float(b) if b else np.nan
