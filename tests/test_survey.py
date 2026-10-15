import numpy as np
import pandas as pd
import pytest
from scipy import stats

from taxcap.survey import make_design, mean, proportion, quantile, weighted_quantile


def hand_example():
    """Two strata with two PSUs each; six units."""
    return pd.DataFrame({
        "stratum": [1, 1, 1, 2, 2, 2],
        "psu":     ["A", "A", "B", "C", "D", "D"],
        "w":       [2.0, 1.0, 3.0, 1.0, 2.0, 1.0],
        "y":       [1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
    })


def test_proportion_matches_hand_calculation():
    df = hand_example()
    design = make_design(df["w"], df["psu"], strata=df["stratum"])
    e = proportion(design, df["y"])

    # p = sum(w y) / sum(w) = (2 + 3 + 2) / 10
    p = 7 / 10
    # PSU totals of w (y - p) / sum(w)
    z_a = (2 * (1 - p) + 1 * (0 - p)) / 10   # -0.01
    z_b = (3 * (1 - p)) / 10                 #  0.09
    z_c = (1 * (0 - p)) / 10                 # -0.07
    z_d = (2 * (1 - p) + 1 * (0 - p)) / 10   # -0.01
    # stratum h: n_h / (n_h - 1) * sum (z_hi - mean_h)^2, with n_h = 2
    v1 = 2 / 1 * ((z_a - (z_a + z_b) / 2) ** 2 + (z_b - (z_a + z_b) / 2) ** 2)   # 0.01
    v2 = 2 / 1 * ((z_c - (z_c + z_d) / 2) ** 2 + (z_d - (z_c + z_d) / 2) ** 2)   # 0.0036
    var = v1 + v2                                                               # 0.0136

    assert e.estimate == pytest.approx(0.7)
    assert var == pytest.approx(0.0136)
    assert e.se == pytest.approx(np.sqrt(var))
    t = stats.t.ppf(0.975, 4 - 2)   # df = PSUs minus strata
    assert e.df == 2
    # logit interval: expit(logit(p) +/- t * SE / (p (1 - p)))
    half = t * np.sqrt(var) / (0.7 * 0.3)
    expit = lambda x: 1 / (1 + np.exp(-x))
    assert e.ci_low == pytest.approx(expit(np.log(0.7 / 0.3) - half))
    assert e.ci_high == pytest.approx(expit(np.log(0.7 / 0.3) + half))
    assert e.n == 6 and e.psus == 4


def test_one_stratum_one_unit_per_psu_matches_weighted_proportion_formula():
    rng = np.random.default_rng(1)
    n = 40
    w = rng.uniform(0.5, 5, n)
    y = (rng.uniform(size=n) < 0.3).astype(float)
    design = make_design(w, [f"u{i}" for i in range(n)], strata=np.ones(n))
    e = proportion(design, y)

    p = (w * y).sum() / w.sum()
    var = n / (n - 1) * (w ** 2 * (y - p) ** 2).sum() / w.sum() ** 2
    assert e.estimate == pytest.approx(p)
    assert e.se == pytest.approx(np.sqrt(var))
    assert e.df == n - 1


def test_domain_estimate_uses_all_psus():
    df = hand_example()
    design = make_design(df["w"], df["psu"], strata=df["stratum"])
    dom = df["psu"].isin(["A", "B", "C"]).to_numpy()   # PSU D has no unit in the domain
    e = proportion(design, df["y"], dom)

    # point estimate equals the weighted share within the domain
    sub = df[dom]
    p = (sub["w"] * sub["y"]).sum() / sub["w"].sum()   # 5 / 7
    assert e.estimate == pytest.approx(p)

    # variance: PSU D enters stratum 2 with a zero total, so n_2 stays 2
    tw = sub["w"].sum()
    z = {k: (g["w"] * (g["y"] - p)).sum() / tw for k, g in sub.groupby("psu")}
    z["D"] = 0.0
    v1 = 2 * ((z["A"] - (z["A"] + z["B"]) / 2) ** 2 + (z["B"] - (z["A"] + z["B"]) / 2) ** 2)
    v2 = 2 * ((z["C"] - (z["C"] + z["D"]) / 2) ** 2 + (z["D"] - (z["C"] + z["D"]) / 2) ** 2)
    assert e.se == pytest.approx(np.sqrt(v1 + v2))
    assert e.n == 4 and e.psus == 3 and e.df == 2

    # dropping the empty PSU from the design gives a different variance
    keep = ~df["psu"].eq("D")
    with pytest.raises(ValueError):   # stratum 2 would be left with one PSU
        make_design(df.loc[keep, "w"], df.loc[keep, "psu"], strata=df.loc[keep, "stratum"])


def test_design_psus_without_units_count_in_variance():
    df = hand_example()
    psu_strata = pd.Series({"A": 1, "B": 1, "C": 2, "D": 2, "E": 2})   # PSU E has no sampled unit
    with_e = proportion(make_design(df["w"], df["psu"], psu_strata), df["y"])
    without_e = proportion(make_design(df["w"], df["psu"], strata=df["stratum"]), df["y"])
    assert with_e.estimate == pytest.approx(without_e.estimate)
    assert with_e.se != pytest.approx(without_e.se)
    assert with_e.df == 5 - 2


def test_mean_and_quantile():
    df = hand_example().assign(x=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    design = make_design(df["w"], df["psu"], strata=df["stratum"])
    assert mean(design, df["x"]).estimate == pytest.approx((20 + 20 + 90 + 40 + 100 + 60) / 10)
    q = quantile(design, df["x"], 0.5)
    assert q.estimate == 30.0   # cumulative weight share reaches 0.5 at x = 30
    assert q.ci_low <= q.estimate <= q.ci_high


def test_weighted_quantile():
    assert weighted_quantile([3, 1, 2], [1, 1, 1], 0.5) == 2
    assert weighted_quantile([1, 2], [9, 1], 0.5) == 1


def test_proportion_rejects_non_binary():
    df = hand_example()
    design = make_design(df["w"], df["psu"], strata=df["stratum"])
    with pytest.raises(ValueError):
        proportion(design, df["y"] * 2)


def test_proportion_cis_lie_within_unit_interval():
    rng = np.random.default_rng(7)
    n = 60
    w = rng.uniform(0.5, 5, n)
    psu = [f"p{i // 3}" for i in range(n)]
    strata = [i // 30 for i in range(n)]
    design = make_design(w, psu, strata=strata)
    for share in [0.02, 0.05, 0.3, 0.9, 0.98]:
        y = (rng.uniform(size=n) < share).astype(float)
        for dom in [None, np.arange(n) < 12, np.arange(n) % 5 == 0]:
            e = proportion(design, y, dom)
            if e.ci_estimable:
                assert 0 <= e.ci_low <= e.estimate <= e.ci_high <= 1


def test_proportion_ci_not_estimable_at_zero_or_one():
    df = hand_example()
    design = make_design(df["w"], df["psu"], strata=df["stratum"])
    for y in [np.zeros(6), np.ones(6)]:
        e = proportion(design, y)
        assert not e.ci_estimable and np.isnan(e.ci_low) and np.isnan(e.ci_high)
