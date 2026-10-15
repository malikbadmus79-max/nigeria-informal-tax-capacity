import numpy as np
import pandas as pd
import pytest

from taxcap import estimate
from taxcap.audit import ID_COLUMNS
from taxcap.frame import AnalysisFrame
from taxcap.load import load_config
from taxcap.survey import Estimate


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def frame(cfg):
    """Twelve operating enterprises in six PSUs and two strata; the last one is excluded."""
    t = cfg["tax_rules"]["pit_exemption_naira"]
    ratio = cfg["price_adjustment"]["cpi_ratio"]
    income = np.array([0.2, 0.5, 0.9, 1.1, 1.5, 3.0, 0.1, 0.7, 0.95, 1.2, 0.4, 0.0]) * t
    d = pd.DataFrame({
        "psu": ["p1", "p1", "p2", "p2", "p3", "p3", "p4", "p4", "p5", "p5", "p6", "p6"],
        "stratum": [1] * 6 + [2] * 6,
        "zone": ["1. X"] * 6 + ["2. Y"] * 6,
        "state": ["1. A"] * 6 + ["2. B"] * 6,
        "urban_rural": ["urban", "rural"] * 6,
        "sector_group": ["food_retail", "transport", "construction"] * 4,
        "weight": [1.0, 2.0, 1.5, 1.0, 2.0, 1.0, 1.0, 1.0, 2.0, 1.5, 1.0, 0.0],
        "in_sample": [True] * 11 + [False],
        "registered": [0, 0, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0],
        "pays_local_authorities": [1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 0],
    })
    d["registered"] = d["registered"].astype(float)
    d["pays_local_authorities"] = d["pays_local_authorities"].astype(float)
    s = d["in_sample"]
    for b, f in [("nominal", 1.0), ("cpi", ratio)]:
        d[f"income_{b}"] = (income * f).astype(float)
        d.loc[~s, f"income_{b}"] = np.nan
        d[f"income_winsorised_{b}"] = d[f"income_{b}"]
        d[f"above_{b}"] = (d[f"income_{b}"] > t).astype(float).where(s)
    psu_strata = pd.Series({"p1": 1, "p2": 1, "p3": 1, "p4": 2, "p5": 2, "p6": 2})
    exclusions = pd.DataFrame({"step": ["analysis sample"], "count": [11]})
    return AnalysisFrame(d, psu_strata, exclusions, pd.DataFrame({"item": [], "value": []}), 1.0, cfg)


def test_tables_have_no_identifiers_and_flag_small_domains(frame):
    tables = estimate.build_tables(frame)
    assert set(tables) == {"headline", "domains", "income", "threshold_band", "registration_payments",
                           "exclusions", "design"}
    for name, t in tables.items():
        assert not ID_COLUMNS & set(t.columns), name
    # 11 enterprises is below the 50-enterprise minimum, so every estimate is flagged
    for name in ["headline", "domains", "income", "threshold_band", "registration_payments"]:
        assert tables[name]["unreliable"].all(), name


def test_headline_matches_weighted_share(frame):
    h = estimate.build_tables(frame)["headline"].set_index("price_basis")
    d = frame.data[frame.data["in_sample"]]
    for b in ["nominal", "cpi"]:
        expected = (d["weight"] * d[f"above_{b}"]).sum() / d["weight"].sum()
        assert h.loc[b, "estimate"] == pytest.approx(expected)
        assert h.loc[b, "n"] == 11 and h.loc[b, "psus"] == 6
    assert h.loc["cpi", "estimate"] >= h.loc["nominal", "estimate"]


def test_threshold_band_counts(frame, cfg):
    t = estimate.build_tables(frame)["threshold_band"].set_index("price_basis")
    # nominal incomes within 0.75 to 1.25 of the threshold: 0.9, 1.1, 0.95, 1.2
    assert t.loc["nominal", "unweighted_count"] == 4


def test_registration_payments_rows(frame):
    r = estimate.build_tables(frame)["registration_payments"]
    assert len(r) == 2 + 2 * (2 * 2 + 1)
    below = r[(r["price_basis"] == "nominal") & r["measure"].str.contains("not registered")]
    d = frame.data[frame.data["in_sample"] & (frame.data["above_nominal"] == 0)]
    y = ((d["pays_local_authorities"] == 1) & (d["registered"] == 0)).astype(float)
    assert below["estimate"].iloc[0] == pytest.approx((d["weight"] * y).sum() / d["weight"].sum())
    assert not r["measure"].str.contains("tax|lev", case=False).any()


def test_unreliable_rule(cfg):
    ok = Estimate(0.5, 0.05, 0.4, 0.6, n=50, psus=10, df=100)
    assert not estimate.unreliable(ok, cfg)
    assert estimate.unreliable(Estimate(0.5, 0.05, 0.4, 0.6, n=49, psus=10, df=100), cfg)
    assert estimate.unreliable(Estimate(0.5, 0.05, 0.4, 0.6, n=50, psus=9, df=100), cfg)
    assert estimate.unreliable(Estimate(0.1, 0.031, 0.0, 0.2, n=50, psus=10, df=100), cfg)
    assert estimate.unreliable(Estimate(0.0, 0.0, 0.0, 0.0, n=500, psus=50, df=100), cfg)


def test_state_rows_are_indicative(frame):
    d = estimate.build_tables(frame)["domains"]
    assert d.loc[d["domain_type"] == "state", "indicative"].all()
    assert not d.loc[d["domain_type"] != "state", "indicative"].any()


def test_same_basis_check_counts_switching_incomes(frame):
    d = estimate.build_tables(frame)["domains"]
    lines = estimate.same_basis_checks(frame, d)
    assert all("enterprises with nominal annual income" in x for x in lines)


def test_all_proportion_cis_within_unit_interval(frame):
    tables = estimate.build_tables(frame)
    for name in ["headline", "domains", "threshold_band", "registration_payments"]:
        t = tables[name]
        ok = t[t["ci_estimable"]]
        assert ((ok["ci_low"] >= 0) & (ok["ci_high"] <= 1)).all(), name
        assert t.loc[~t["ci_estimable"], ["ci_low", "ci_high"]].isna().all().all(), name


def test_domain_shares_average_to_headline(frame):
    tables = estimate.build_tables(frame)
    c = estimate.domain_consistency(frame, tables)
    assert len(c) == len(estimate.CONSISTENCY_DOMAINS) * 2
    assert c["consistent"].all()
    assert (c["abs_difference"] <= 1e-9).all()


def test_domain_consistency_detects_a_wrong_share(frame):
    tables = estimate.build_tables(frame)
    d = tables["domains"].copy()
    d.loc[(d["domain_type"] == "zone") & (d["price_basis"] == "nominal"), "estimate"] += 0.01
    c = estimate.domain_consistency(frame, {**tables, "domains": d}).set_index(["domain_type", "price_basis"])
    assert not c.loc[("zone", "nominal"), "consistent"]
    assert c.loc[("zone", "cpi"), "consistent"]
