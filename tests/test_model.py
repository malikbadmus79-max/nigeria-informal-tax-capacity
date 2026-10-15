import copy
import inspect

import numpy as np
import pandas as pd
import pytest
import yaml

from taxcap import model
from taxcap.features import FeatureSpec, FeatureTable
from taxcap.load import load_config
from taxcap.split import Split


@pytest.fixture
def cfg():
    c = copy.deepcopy(load_config())
    c["model"]["grids"] = {   # small grids keep the tests fast
        "logistic_regression": {"C": [0.1, 1.0]},
        "hist_gradient_boosting": {"learning_rate": [0.1], "max_leaf_nodes": [15], "min_samples_leaf": [20],
                                   "l2_regularization": [0, 1]},
    }
    return c


def synthetic_table(seed=0, n_psu=60, per=10):
    rng = np.random.default_rng(seed)
    n = n_psu * per
    psu = np.repeat([f"p{i:02d}" for i in range(n_psu)], per)
    zone = np.repeat([f"{i % 3 + 1}. Z" for i in range(n_psu)], per)
    cat = rng.choice(["a", "b", "c"], n)
    num = rng.normal(size=n)
    reg = (rng.uniform(size=n) < 0.2).astype(float)
    emp = rng.poisson(0.5, n).astype(float)
    pay = (rng.uniform(size=n) < 0.4).astype(float)
    logit = -0.5 + 1.2 * num + 0.8 * (cat == "a") + 1.0 * reg + 0.4 * emp
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-logit))).astype(float)
    num[::37] = np.nan   # some missing values for the imputer
    d = pd.DataFrame({"cat": pd.Series(cat, dtype="string"), "num": num, "registered": reg,
                      "non_household_employees": emp, "local_authority_payments": pay,
                      "target_cpi": y, "target_nominal": y, "weight": rng.uniform(50, 500, n),
                      "psu": psu, "stratum": zone, "zone": zone})
    specs = [FeatureSpec("cat", "synthetic", ("cat",), "categorical"),
             FeatureSpec("num", "synthetic", ("num",), "numeric"),
             FeatureSpec("registered", "synthetic", ("s8q11",), "binary"),
             FeatureSpec("non_household_employees", "synthetic", ("s8q13a", "s8q13b"), "count"),
             FeatureSpec("local_authority_payments", "synthetic", ("s8q11b",), "binary")]
    set_a = ["cat", "num", "registered", "non_household_employees"]
    return FeatureTable(d, specs, set_a, set_a + ["local_authority_payments"])


@pytest.fixture
def table():
    return synthetic_table()


@pytest.fixture
def split(table, cfg):
    return Split(table.data["psu"], table.data["zone"], table.data["target_cpi"], cfg)


def test_preprocessing_fitted_within_folds_only(table, split, cfg):
    t = copy.copy(table)
    t.data = table.data.copy()
    tr = split.train_rows(t.data)
    one_psu = tr["psu"].iloc[0]
    t.data.loc[t.data["psu"] == one_psu, "cat"] = "only_here"   # a category present in one training PSU only
    oof, fitted = model.oof_predict(t, split, t.set_a, "logistic_regression", {"C": 1.0}, cfg, return_models=True)
    X = model.design_matrix(split.train_rows(t.data), *model.split_kinds(t, t.set_a))
    full_mean = X["num"].mean()
    for train_idx, pipe in fitted:
        num_pipe = pipe.named_steps["pre"].named_transformers_["num"]
        part = X.loc[train_idx, ["num", "registered", "non_household_employees"]]
        imputed = part.fillna(part.median())
        assert np.allclose(num_pipe.named_steps["scale"].mean_, imputed.mean().to_numpy())
        cats = pipe.named_steps["pre"].named_transformers_["cat"].named_steps["onehot"].categories_[0]
        assert ("only_here" in cats) == (one_psu in set(t.data.loc[train_idx, "psu"]))
    assert not any(np.isclose(p.named_steps["pre"].named_transformers_["num"].named_steps["scale"].mean_[0], full_mean)
                   for _, p in fitted)


def test_model_module_cannot_reach_test_rows(table, split, cfg, monkeypatch):
    src = inspect.getsource(model)
    assert "final_evaluation" not in src and "test_rows" not in src

    def refuse(*args, **kwargs):
        raise AssertionError("model.py touched the test set")
    monkeypatch.setattr(Split, "test_rows", refuse)
    _, _, selected = model.cross_validate(table, split, cfg)
    model.fit_selected(table, split, selected, cfg)
    oof = model.oof_predict(table, split, table.set_a, "logistic_regression", {"C": 1.0}, cfg)
    assert set(oof.index) == set(split.train_rows(table.data).index)
    assert not set(oof.index) & set(table.data.index[~split.train_mask])


def test_selection_is_deterministic(table, split, cfg):
    a = model.cross_validate(table, split, cfg)
    b = model.cross_validate(table, split, cfg)
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])
    assert model.preferred_model(a[2], cfg) == model.preferred_model(b[2], cfg)


def test_operating_point_thresholds_meet_constraints(table, split, cfg):
    tr = split.train_rows(table.data)
    y, w = tr["target_cpi"].astype(int), tr["weight"]
    _, cv_selected, selected = model.cross_validate(table, split, cfg)
    op = cfg["model"]["operating_points"]
    for (m, fs), s in selected.items():
        oof = model.oof_predict(table, split, table.features(fs), m, s["params"], cfg)
        met = s["metrics"]
        if not np.isnan(met["op_ffr10_threshold"]):
            r = model.rates(y, oof >= met["op_ffr10_threshold"], w)
            assert r["false_flag_rate"] <= op["max_false_flag_rate"] + 1e-12
            assert r["recall"] == pytest.approx(met["op_ffr10_recall"])
        t = met["op_rec50_threshold"]
        r = model.rates(y, oof >= t, w)
        assert r["recall"] >= op["min_recall"] - 1e-12
        assert r["recall"] == pytest.approx(met["op_rec50_recall"])
        assert r["precision"] == pytest.approx(met["op_rec50_precision"])
        higher = np.unique(oof[oof > t])
        if higher.size:   # the next higher threshold falls below the recall bound
            assert model.rates(y, oof >= higher.min(), w)["recall"] < op["min_recall"]
    assert len(cv_selected) == 2 * 2 * 2 + 2   # models x sets x (unweighted, weighted) + 2 rules


def test_operating_point_by_hand():
    y = np.array([1, 1, 0, 1, 0, 0, 0, 0, 0, 0])
    p = np.array([.9, .8, .7, .6, .5, .4, .3, .2, .1, .05])
    w = np.ones(10)
    a = model.operating_point(y, p, w, model.OP_FFR, 0.10)    # at most 0.7 of 7 negatives flagged: none
    assert a["threshold"] == 0.8 and a["recall"] == pytest.approx(2 / 3) and a["false_flag_rate"] == 0
    b = model.operating_point(y, p, w, model.OP_RECALL, 0.5)   # t = 0.8 is the highest with recall >= 0.5
    assert b["threshold"] == 0.8 and b["recall"] == pytest.approx(2 / 3) and b["precision"] == 1
    c = model.operating_point(y, p, w, model.OP_RECALL, 0.9)   # needs all three positives: t = 0.6
    assert c["threshold"] == 0.6 and c["recall"] == 1 and c["false_flag_rate"] == pytest.approx(1 / 7)


def test_preferred_model_near_tie_rule(cfg):
    def sel(lr, hgb):
        return {("logistic_regression", "A"): {"metrics": {"pr_auc": lr}},
                ("hist_gradient_boosting", "A"): {"metrics": {"pr_auc": hgb}}}
    assert model.preferred_model(sel(0.60, 0.605), cfg)["model"] == "logistic_regression"
    assert model.preferred_model(sel(0.60, 0.62), cfg)["model"] == "hist_gradient_boosting"
    assert model.preferred_model(sel(0.62, 0.60), cfg)["model"] == "logistic_regression"


def test_selection_record_is_plain_yaml(table, split, cfg):
    _, _, selected = model.cross_validate(table, split, cfg)
    rec = model.selection_record(selected, model.preferred_model(selected, cfg), split, cfg, {})
    text = yaml.safe_dump(rec)
    back = yaml.safe_load(text)
    assert set(back["models"]) == set(model.MODELS)
    assert back["test_psu_sha256"] == split.test_psu_hash()


def test_assert_selection_unchanged(table, split, cfg):
    _, _, selected = model.cross_validate(table, split, cfg)
    rec = model.selection_record(selected, model.preferred_model(selected, cfg), split, cfg, {})
    model.assert_selection_unchanged(copy.deepcopy(rec), rec)
    changed = copy.deepcopy(rec)
    changed["models"]["logistic_regression"]["A"]["params"]["C"] = 999.0
    with pytest.raises(RuntimeError):
        model.assert_selection_unchanged(changed, rec)
    other = copy.deepcopy(rec)
    other["preferred"]["model"] = "hist_gradient_boosting" if rec["preferred"]["model"] == "logistic_regression" \
        else "logistic_regression"
    with pytest.raises(RuntimeError):
        model.assert_selection_unchanged(other, rec)
