import pandas as pd
import pytest

from taxcap.frame import EXCLUDED_NO_FLAGS, EXCLUDED_ZERO_MONTHS, build_frame, modal_stratum
from taxcap.load import load_config


@pytest.fixture
def cfg():
    return load_config()


def counts(fr):
    return fr.exclusions.set_index("step")["count"]


def test_build_frame_population_and_exclusions(audit_frames, cfg):
    ent, _, cover = audit_frames
    fr = build_frame(ent, cover, cfg)
    c = counts(fr)
    assert c["enterprises in sect8b"] == 4
    assert c["currently operating (s8q3 = 1)"] == 3
    assert c[f"excluded: {EXCLUDED_ZERO_MONTHS}"] == 1   # flags only s8q9__0, __1 and __16
    assert c[f"excluded: {EXCLUDED_NO_FLAGS}"] == 1      # all s8q9 flags missing
    assert c["analysis sample"] == 1
    assert len(fr.data) == 3


def test_build_frame_income_and_flags(audit_frames, cfg):
    ent, _, cover = audit_frames
    fr = build_frame(ent, cover, cfg)
    row = fr.data[fr.data["in_sample"]].iloc[0]
    ratio = cfg["price_adjustment"]["cpi_ratio"]
    assert row["months"] == 12
    assert row["income_nominal"] == 50 * 12
    assert row["income_cpi"] == pytest.approx(50 * 12 * ratio)
    assert row["above_nominal"] == 0 and row["above_cpi"] == 0
    assert row["pays_local_authorities"] == 1 and row["registered"] == 0
    assert row["sector_group"] == "food_retail" and row["urban_rural"] == "rural"
    assert row["stratum"] == 1
    # excluded rows carry no income or threshold flag
    assert fr.data.loc[~fr.data["in_sample"], "above_nominal"].isna().all()


def test_negative_profit_is_zero_income(audit_frames, cfg):
    ent, _, cover = audit_frames
    ent = ent.assign(s8q30=[-10, 0, 0, 0])
    fr = build_frame(ent, cover, cfg)
    assert fr.data.loc[fr.data["in_sample"], "income_nominal"].iloc[0] == 0


def test_threshold_is_strictly_above(audit_frames, cfg):
    ent, _, cover = audit_frames
    t = cfg["tax_rules"]["pit_exemption_naira"]
    fr = build_frame(ent.assign(s8q30=[t / 12, 0, 0, 0]), cover, cfg)
    assert fr.data.loc[fr.data["in_sample"], "above_nominal"].iloc[0] == 0   # exactly at the threshold
    assert fr.data.loc[fr.data["in_sample"], "above_cpi"].iloc[0] == 1


def test_modal_stratum_with_tie_to_lowest():
    psu = pd.Series(["a", "a", "a", "b", "b", "c", "c"])
    strata = pd.Series([1, 2, 2, 3, 3, 2, 1])
    out = modal_stratum(psu, strata)
    assert out.to_dict() == {"a": 2, "b": 3, "c": 1}
