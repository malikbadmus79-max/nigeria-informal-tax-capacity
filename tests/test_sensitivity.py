import numpy as np
import pandas as pd
import pytest

from taxcap import sensitivity
from taxcap.audit import ID_COLUMNS, months_in_window
from taxcap.frame import FrameOptions, build_frame, to_owner_level
from taxcap.load import load_config


@pytest.fixture
def cfg():
    return load_config()


def by_scenario(ent, cover, cfg):
    return {sc.name: sc for sc in sensitivity.scenarios(cfg)}


def estimates(sc, fr):
    t = pd.DataFrame(sensitivity.scenario_rows(sc, fr))
    return t.set_index(["price_basis", "measure"])


def test_every_planned_scenario_present(design_frames, cfg):
    names = [sc.name for sc in sensitivity.scenarios(cfg)]
    assert names == ["primary", "profit_x12", "fixed_window", "unprinted_flags_missing", "include_closed",
                     "owner_level", "cpi_unrevised_aug_2025", "strata_zone_urban_rural"]


def test_strata_scenario_changes_variance_only(design_frames, cfg):
    ent, cover = design_frames
    sc = by_scenario(ent, cover, cfg)
    primary = estimates(sc["primary"], sc["primary"].build(ent, cover, cfg))
    strata = estimates(sc["strata_zone_urban_rural"], sc["strata_zone_urban_rural"].build(ent, cover, cfg))
    assert np.allclose(primary["estimate"], strata["estimate"], rtol=0, atol=0)
    assert (primary["n"] == strata["n"]).all()
    assert not np.allclose(primary["se"], strata["se"])


def test_strata_scenario_uses_zone_by_urban_rural(design_frames, cfg):
    ent, cover = design_frames
    fr = build_frame(ent, cover, cfg, FrameOptions(strata_rule="zone_sector"))
    assert fr.psu_strata.nunique() == 4   # 2 zones x urban/rural


def test_profit_x12_equals_primary_when_every_enterprise_operated_12_months(design_frames, cfg):
    ent, cover = design_frames
    full = ent.copy()
    for k in range(3, 16):
        full[f"s8q9__{k}"] = 1.0   # every window month flagged, for February and March interviews
    primary = build_frame(full, cover, cfg)
    x12 = build_frame(full, cover, cfg, FrameOptions(months_rule="profit_x12"))
    for b in ["nominal", "cpi"]:
        pd.testing.assert_series_equal(primary.data[f"income_{b}"], x12.data[f"income_{b}"])
    pd.testing.assert_series_equal(primary.data["in_sample"], x12.data["in_sample"])


def test_profit_x12_keeps_primary_sample_and_uses_12_months(design_frames, cfg):
    ent, cover = design_frames
    primary = build_frame(ent, cover, cfg)
    x12 = build_frame(ent, cover, cfg, FrameOptions(months_rule="profit_x12"))
    pd.testing.assert_series_equal(primary.data["in_sample"], x12.data["in_sample"])
    s = x12.data["in_sample"]
    assert (x12.data.loc[s, "income_nominal"] == x12.data.loc[s, "profit"] * 12).all()
    assert (x12.data.loc[s, "income_nominal"] >= primary.data.loc[s, "income_nominal"]).all()


def test_fixed_window_months(design_frames, cfg):
    ent, cover = design_frames
    fr = build_frame(ent, cover, cfg, FrameOptions(months_rule="fixed_window"))
    expected = months_in_window(ent, cover, cfg, "fixed_calendar_window")
    pd.testing.assert_series_equal(fr.data["months"], expected.loc[fr.data.index], check_names=False)


def test_unprinted_flags_missing_scales_to_12(design_frames, cfg):
    ent, cover = design_frames
    primary = build_frame(ent, cover, cfg)
    fr = build_frame(ent, cover, cfg, FrameOptions(months_rule="unprinted_missing"))
    march = ent["hhid"].isin(cover.loc[cover["InterviewStart"].str.startswith("2024-03"), "hhid"])
    m = fr.data["months"]
    feb_rows = fr.data.index[~march.loc[fr.data.index]]
    pd.testing.assert_series_equal(m.loc[feb_rows], primary.data.loc[feb_rows, "months"])  # no flag 15 or 16 in window
    # March interviews: window flags 4 to 15; usable flags 4 to 14 (11 months)
    flags = ent.loc[fr.data.index, [f"s8q9__{k}" for k in range(4, 15)]].sum(axis=1)
    mar_rows = fr.data.index[march.loc[fr.data.index]]
    assert np.allclose(m.loc[mar_rows], flags.loc[mar_rows] * 12 / 11)


def test_include_closed_adds_only_closed_enterprises(design_frames, cfg):
    ent, cover = design_frames
    primary = build_frame(ent, cover, cfg)
    closed = build_frame(ent, cover, cfg, FrameOptions(status_codes=(1, 3, 4)))
    added = closed.data.index.difference(primary.data.index)
    assert len(added) > 0
    assert ent.loc[added, "s8q3"].str.startswith(("3.", "4.")).all()
    common = primary.data.index
    pd.testing.assert_series_equal(primary.data["income_nominal"], closed.data.loc[common, "income_nominal"])
    pd.testing.assert_series_equal(primary.psu_strata, closed.psu_strata)


def test_owner_level_splits_two_owner_income_equally(design_frames, cfg):
    ent, cover = design_frames
    fr = build_frame(ent, cover, cfg)
    owners = to_owner_level(fr).data.set_index(["hhid", "indiv"])
    s = fr.data[fr.data["in_sample"]]
    single_ent_hh = s.groupby("hhid").size().loc[lambda x: x == 1].index
    two = s[s["owner_2"].notna() & s["hhid"].isin(single_ent_hh)]
    assert len(two) > 0
    for _, e in two.iterrows():
        for person in [e["owner_1"], e["owner_2"]]:
            for b in ["nominal", "cpi"]:
                assert owners.loc[(e["hhid"], person), f"income_{b}"] == pytest.approx(e[f"income_{b}"] / 2)


def test_owner_level_sums_each_persons_enterprises(design_frames, cfg):
    ent, cover = design_frames
    fr = build_frame(ent, cover, cfg)
    p = to_owner_level(fr).data
    s = fr.data[fr.data["in_sample"]]
    # splitting moves income between persons but neither creates nor loses any
    assert len(p) > s["owner_1"].notna().sum() - s["hhid"].duplicated().sum()
    assert p["income_nominal"].sum() == pytest.approx(s["income_nominal"].sum())


def test_unrevised_cpi_changes_cpi_basis_only(design_frames, cfg):
    ent, cover = design_frames
    sc = by_scenario(ent, cover, cfg)["cpi_unrevised_aug_2025"]
    fr = sc.build(ent, cover, cfg)
    primary = build_frame(ent, cover, cfg)
    pd.testing.assert_series_equal(fr.data["income_nominal"], primary.data["income_nominal"])
    ratio = cfg["price_adjustment"]["sensitivities"]["unrevised_aug_2025"]["cpi_ratio"]
    s = fr.data["in_sample"]
    assert np.allclose(fr.data.loc[s, "income_cpi"], primary.data.loc[s, "income_nominal"] * ratio)
    assert sc.bases == ("cpi",)


def test_run_scenarios_table(design_frames, cfg):
    ent, cover = design_frames
    t = sensitivity.run_scenarios(ent, cover, cfg)
    assert not ID_COLUMNS & set(t.columns)
    assert set(t["scenario"]) == {sc.name for sc in sensitivity.scenarios(cfg)}
    assert len(t) == 2 * (2 * 7 + 1)   # cpi_unrevised reports the CPI basis only
    ok = t[t["ci_estimable"]]
    assert ((ok["ci_low"] >= 0) & (ok["ci_high"] <= 1)).all()
    assert not t["measure"].str.contains("tax|lev", case=False).any()
