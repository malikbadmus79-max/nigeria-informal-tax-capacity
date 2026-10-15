import copy

import numpy as np
import pandas as pd
import pytest

from taxcap.features import (HOUSEHOLD_FILES, FeatureSpec, _merge_rare, build_features, check_excluded,
                              household_coverage, summary)
from taxcap.frame import build_frame
from taxcap.load import load_config
from taxcap.split import LockedTestSetError, Split, make_split, training_target_shares


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def frame(design_frames, cfg):
    ent, cover = design_frames
    return build_frame(ent, cover, cfg)


@pytest.fixture
def split(frame, cfg):
    return make_split(frame, cfg)


@pytest.fixture
def table(frame, split, design_frames, household_frames):
    return build_features(frame, design_frames[0], household_frames, split.train_mask)


# features ----------------------------------------------------------------------------------

def test_feature_sets(table):
    assert table.set_b == table.set_a + ["local_authority_payments"]
    assert "local_authority_payments" not in table.set_a
    for col in ["target_cpi", "target_nominal", "weight", "psu", "stratum"]:
        assert col in table.data.columns
        assert col not in table.set_b


def test_excluded_variables_absent_from_both_sets(table, cfg):
    never = cfg["features"]["never"]
    for s in ["A", "B"]:
        cols = table.features(s)
        specs = [sp for sp in table.specs if sp.name in cols]
        assert len(specs) == len(cols)
        for sp in specs:
            assert not set(sp.variables) & set(never["variables"])
            assert sp.file not in never["files"]
        for c in cols:
            assert not set(c.lower().split("_")) & set(never["name_patterns"]), c
    for banned in ["profit", "income_nominal", "income_cpi", "above_cpi", "months", "s10q6", "pays_local_authorities"]:
        assert banned not in table.set_b


@pytest.mark.parametrize("name, spec", [
    ("profit", FeatureSpec("profit", "sect8b_harvestw5", ("s8q30",), "numeric")),
    ("asset_value", FeatureSpec("asset_value", "sect10_plantingw5", ("s10q6",), "numeric")),
    ("owner_age", FeatureSpec("owner_age", "sect1_harvestw5", ("s1q6",), "numeric")),
    ("consumption", FeatureSpec("consumption", "totcons_final", ("totcons",), "numeric")),
])
def test_check_excluded_rejects_excluded_features(table, cfg, name, spec):
    bad = copy.copy(table)
    bad.data = table.data.assign(**{name: 0.0})
    bad.specs = table.specs + [spec]
    bad.set_a = table.set_a + [name]
    bad.set_b = table.set_b + [name]
    with pytest.raises(ValueError):
        check_excluded(bad, cfg)


def test_feature_coding(table, design_frames, household_frames):
    ent = design_frames[0]
    d = table.data
    e = ent.loc[d.index]
    # employees: "0. NONE" = 0, counts added
    exp = e["s8q13a"].str.extract(r"^(\d+)")[0].astype(float) + e["s8q13b"].str.extract(r"^(\d+)")[0].astype(float)
    assert np.allclose(d["non_household_employees"], exp)
    # years in operation: "0. IN THE LAST 12 MONTHS" = 0
    assert (d.loc[e["s8q4b"].str.startswith("0."), "years_in_operation"] == 0).all()
    # any-member indicator is missing when no member answered
    last = household_frames["sect5b_plantingw5"]["hhid"].max()
    assert d.loc[d.index[ent.loc[d.index, "hhid"] == last], "any_member_mobile_phone"].isna().all()
    # durable item 3341 (Other) excluded; count of item types owned is consistent
    assert "asset_3341" not in d.columns
    assert np.allclose(d["asset_types_owned"], d[["asset_301", "asset_312"]].sum(axis=1))
    # household size counts current members only
    assert set(d["household_size"]) <= {2.0, 3.0}


def test_rare_categories_merged_into_other(cfg):
    codes = pd.Series([5.0] * 150 + [1.0] * 48 + [9.0] * 1 + [7.0] * 1)   # 9 and 7 each 0.5% < 1%
    out = _merge_rare(codes, np.ones(len(codes), dtype=bool), cfg)
    assert set(out) == {"5", "1", "96"}
    assert (out == "96").sum() == 2


def test_rare_category_frequencies_use_training_rows_only(cfg):
    # code 3 is common overall but appears only in test rows: unseen in training, so it maps to 96;
    # code 9 is rare in training but common in test: rare by training frequency, so it maps to 96
    codes = pd.Series([5.0] * 199 + [9.0] * 1 + [3.0] * 50 + [9.0] * 50 + [np.nan] * 2)
    train = np.array([True] * 200 + [False] * 102)
    out = _merge_rare(codes, train, cfg)
    assert set(out[train]) == {"5", "96"}
    assert set(out[~train].dropna()) == {"96"}
    assert out.isna().sum() == 2   # missing stays missing


@pytest.mark.parametrize("source", HOUSEHOLD_FILES)
def test_household_absent_from_source_file_gets_nan(frame, split, design_frames, household_frames, source):
    ent = design_frames[0]
    s = frame.data[frame.data["in_sample"]]
    gone = s["hhid"].iloc[0]
    reduced = {**household_frames, source: household_frames[source][household_frames[source]["hhid"] != gone]}
    t = build_features(frame, ent, reduced, split.train_mask)
    cov = household_coverage(frame, reduced).set_index("source_file")
    assert cov.loc[source, "enterprises_without_household_row"] == (s["hhid"] == gone).sum()
    rows = t.data.index[s["hhid"].to_numpy() == gone]
    affected = {
        "sect5b_plantingw5": ["any_member_mobile_phone", "any_member_internet"],
        "sect5a1_plantingw5": ["any_member_account", "any_member_formal_savings"],
        "sect9_harvestw5": ["household_internet_connection", "wall_material", "roof_material", "floor_material"],
        "sect10_plantingw5": [c for c in t.set_a if c.startswith("asset_")],
        "sect1_harvestw5": ["household_size"],
    }[source]
    assert t.data.loc[rows, affected].isna().all().all(), source
    base = build_features(frame, ent, household_frames, split.train_mask)
    other = t.data.index[s["hhid"].to_numpy() != gone]
    pd.testing.assert_frame_equal(t.data.loc[other, affected], base.data.loc[other, affected])


# split -------------------------------------------------------------------------------------

def test_split_deterministic_for_fixed_seed(table, cfg):
    a = Split(table.data["psu"], table.data["zone"], table.data["target_cpi"], cfg)
    b = Split(table.data["psu"], table.data["zone"], table.data["target_cpi"], cfg)
    assert a.test_psu_hash() == b.test_psu_hash()
    assert (a.train_mask == b.train_mask).all()
    assert a.fold_of_training_rows.equals(b.fold_of_training_rows)
    assert len(a.test_psu_hash()) == 64


def test_train_and_test_share_no_psu(table, split):
    train = split.train_rows(table.data)
    test = split.test_rows(table.data, final_evaluation=True)
    assert set(train["psu"]).isdisjoint(set(test["psu"]))
    assert len(train) + len(test) == len(table.data)


def test_folds_share_no_psu_and_cover_training_set(table, split):
    seen = []
    for tr_idx, val_idx in split.folds():
        assert set(table.data.loc[tr_idx, "psu"]).isdisjoint(set(table.data.loc[val_idx, "psu"]))
        seen += list(val_idx)
    train = split.train_rows(table.data)
    assert sorted(seen) == sorted(train.index)
    assert set(table.data.loc[seen, "psu"]).isdisjoint(set(split.test_rows(table.data, True)["psu"]))


def test_every_zone_in_test_set(table, split):
    test = split.test_rows(table.data, final_evaluation=True)
    assert set(test["zone"]) == set(table.data["zone"])


def test_test_accessor_locked(table, split):
    for arg in [False, None, 1, "yes"]:
        with pytest.raises(LockedTestSetError):
            split.test_rows(table.data, final_evaluation=arg)
    with pytest.raises(LockedTestSetError):
        split.test_rows(table.data)


def test_summaries_hold_no_test_target_statistics(table, split):
    s = split.summary()
    assert not s["measure"].str.contains("share above|target", case=False).any()
    t = training_target_shares(table, split)
    assert t["set"].str.startswith("train").all() and len(t) == 2 * (1 + 5)
    f = summary(table, split.train_mask)
    assert {"feature", "source_file", "source_variables", "type", "share_missing_training_set"} <= set(f.columns)
    assert len(f) == len(table.specs)


def test_folds_use_only_training_targets(table, cfg):
    # changing test-row targets leaves the test draw and the folds unchanged
    t = table.data["target_cpi"]
    a = Split(table.data["psu"], table.data["zone"], t, cfg)
    flipped = t.where(a.train_mask, 1 - t)
    b = Split(table.data["psu"], table.data["zone"], flipped, cfg)
    assert a.test_psu_hash() == b.test_psu_hash()
    assert a.fold_of_training_rows.equals(b.fold_of_training_rows)


def test_fold_target_shares_reported_for_training_folds_only(table, split):
    t = training_target_shares(table, split)
    assert set(t["set"]) == {"train"} | {f"train fold {k}" for k in range(5)}


def test_verify_split_against_recorded_hash(split, tmp_path):
    from taxcap.split import HASH_MEASURE, SplitChanged, verify_split
    path = tmp_path / "split_summary.csv"
    assert "no recorded hash" in verify_split(split, path)   # first run records the hash
    pd.DataFrame({"zone": ["all"], "set": ["test"], "measure": [HASH_MEASURE],
                  "value": [split.test_psu_hash()]}).to_csv(path, index=False)
    assert "matches" in verify_split(split, path)
    pd.DataFrame({"zone": ["all"], "set": ["test"], "measure": [HASH_MEASURE], "value": ["0" * 64]}).to_csv(path, index=False)
    with pytest.raises(SplitChanged):
        verify_split(split, path)
