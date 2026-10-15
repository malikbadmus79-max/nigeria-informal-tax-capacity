"""Survey-weighted estimates with Taylor-linearised variance.

The design is stratified, with PSUs treated as sampled with replacement within strata. Means and
proportions are ratio estimators, linearised as z_k = d_k (y_k - estimate) / sum(w d). The variance is

    sum over strata h of  n_h / (n_h - 1) * sum over PSUs i in h of (Z_hi - mean_h Z)^2,

where Z_hi is the weighted sum of z over PSU i and n_h counts every design PSU in stratum h. Domain
estimates keep every design PSU, including PSUs with no unit in the domain (their Z_hi is zero).
Confidence intervals use the t distribution with degrees of freedom = design PSUs minus strata. For
proportions the interval is formed on the logit scale, as in the R survey package's svyciprop default:
expit(logit(p) +/- t * SE / (p (1 - p))); it is not estimable when p is 0 or 1.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class Design:
    weight: np.ndarray       # one per unit
    psu: np.ndarray          # PSU code of each unit
    psu_strata: pd.Series    # stratum of every design PSU, indexed by PSU code

    @property
    def n_psu(self) -> int:
        return int(self.psu_strata.size)

    @property
    def n_strata(self) -> int:
        return int(self.psu_strata.nunique())

    @property
    def df(self) -> int:
        return self.n_psu - self.n_strata


def make_design(weight, psu, psu_strata: pd.Series | None = None, strata=None) -> Design:
    """Build a design. psu_strata lists every design PSU and its stratum; when omitted it is taken
    from the units' own strata, which must then be constant within each PSU."""
    w = np.asarray(weight, dtype=float)
    p = np.asarray(psu).astype(str)
    if np.isnan(w).any() or (w < 0).any():
        raise ValueError("weights must be non-missing and non-negative")
    if psu_strata is None:
        if strata is None:
            raise ValueError("give psu_strata or strata")
        s = pd.Series(np.asarray(strata), index=p)
        per_psu = s.groupby(level=0).nunique()
        if (per_psu > 1).any():
            raise ValueError("a PSU spans more than one stratum; pass psu_strata")
        psu_strata = s.groupby(level=0).first()
    psu_strata = psu_strata.copy()
    psu_strata.index = psu_strata.index.astype(str)
    if psu_strata.index.duplicated().any():
        raise ValueError("psu_strata has duplicate PSU codes")
    missing = set(p[w > 0]) - set(psu_strata.index)
    if missing:   # units with zero weight contribute nothing and may sit outside the design
        raise ValueError(f"{len(missing)} PSUs of weighted units are not in psu_strata")
    if (psu_strata.value_counts() < 2).any():
        raise ValueError("every stratum needs at least two PSUs")
    return Design(weight=w, psu=p, psu_strata=psu_strata)


def linearised_variance(design: Design, z: np.ndarray) -> float:
    """Stratified with-replacement variance of a total of the linearised values z."""
    totals = pd.Series(design.weight * np.asarray(z, dtype=float)).groupby(design.psu).sum()
    totals = totals.reindex(design.psu_strata.index, fill_value=0.0)
    h = design.psu_strata
    n_h = h.value_counts()
    dev = totals - totals.groupby(h).transform("mean")
    ss = (dev ** 2).groupby(h).sum()
    return float((n_h / (n_h - 1) * ss).sum())


@dataclass(frozen=True)
class Estimate:
    estimate: float
    se: float
    ci_low: float
    ci_high: float
    n: int          # unweighted units in the domain
    psus: int       # PSUs with at least one unit in the domain
    df: int
    ci_estimable: bool = True

    @property
    def relative_se(self) -> float:
        if self.estimate == 0 or not np.isfinite(self.estimate):
            return float("inf")
        return self.se / abs(self.estimate)

    def as_dict(self) -> dict:
        return {**asdict(self), "relative_se": self.relative_se}


def _domain(design: Design, domain) -> np.ndarray:
    n = design.weight.size
    return np.ones(n, dtype=bool) if domain is None else np.asarray(domain, dtype=bool)


def _t(design: Design, level: float) -> float:
    return float(stats.t.ppf(1 - (1 - level) / 2, design.df))


def mean(design: Design, y, domain=None, level: float = 0.95) -> Estimate:
    """Weighted mean of y over the domain (a ratio estimator)."""
    d = _domain(design, domain)
    y = np.asarray(y, dtype=float)
    if np.isnan(y[d]).any():
        raise ValueError("y is missing for units in the domain")
    y0 = np.where(d, y, 0.0)
    wd = design.weight * d
    total_w = wd.sum()
    if total_w <= 0:
        nan = float("nan")
        return Estimate(nan, nan, nan, nan, int(d.sum()), 0, design.df)
    est = float((wd * y0).sum() / total_w)
    z = d * (y0 - est) / total_w
    se = float(np.sqrt(linearised_variance(design, z)))
    t = _t(design, level)
    return Estimate(est, se, est - t * se, est + t * se, int(d.sum()),
                    int(np.unique(design.psu[d]).size), design.df)


def proportion(design: Design, y, domain=None, level: float = 0.95) -> Estimate:
    """Weighted share of units with y = 1 in the domain; y must be 0 or 1."""
    y = np.asarray(y, dtype=float)
    d = _domain(design, domain)
    if not np.isin(y[d], [0.0, 1.0]).all():
        raise ValueError("proportion needs y coded 0 or 1 in the domain")
    e = mean(design, y, d, level)
    p = e.estimate
    if not (0 < p < 1):
        nan = float("nan")
        return replace(e, ci_low=nan, ci_high=nan, ci_estimable=False)
    half = _t(design, level) * e.se / (p * (1 - p))
    logit = np.log(p / (1 - p))
    return replace(e, ci_low=float(_expit(logit - half)), ci_high=float(_expit(logit + half)))


def _expit(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def weighted_quantile(y, w, q: float) -> float:
    """Smallest y whose cumulative weight share reaches q."""
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    order = np.argsort(y, kind="mergesort")
    y, w = y[order], w[order]
    cum = np.cumsum(w) / w.sum()
    i = int(np.searchsorted(cum, q, side="left"))
    return float(y[min(i, y.size - 1)])


def quantile(design: Design, y, q: float, domain=None, level: float = 0.95) -> Estimate:
    """Weighted quantile with a Woodruff confidence interval.

    The interval inverts the interval for the share of the domain at or below the estimate. The
    reported standard error is the interval width divided by 2t.
    """
    d = _domain(design, domain)
    y = np.asarray(y, dtype=float)
    yd, wd = y[d], design.weight[d]
    est = weighted_quantile(yd, wd, q)
    below = proportion(design, (np.nan_to_num(y) <= est).astype(float), d, level)
    t = _t(design, level)
    lo = weighted_quantile(yd, wd, max(0.0, q - t * below.se))
    hi = weighted_quantile(yd, wd, min(1.0, q + t * below.se))
    return Estimate(est, (hi - lo) / (2 * t), lo, hi, int(d.sum()), int(np.unique(design.psu[d]).size), design.df)
