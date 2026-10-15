import ast
import inspect

import numpy as np
import pandas as pd
import pytest

from taxcap import fairness
from taxcap.evaluate import bootstrap_multiplicities
from taxcap.load import load_config


@pytest.fixture
def cfg():
    return load_config()


def test_group_prevalence_matches_weighted_share(cfg):
    rng = np.random.default_rng(5)
    n = 200
    psu = np.repeat([f"p{i}" for i in range(20)], 10)
    y = (rng.uniform(size=n) < 0.4).astype(float)
    w = rng.uniform(1, 5, n)
    groups = pd.Series(np.where(np.arange(n) < 120, "a", "b"))
    mult = bootstrap_multiplicities(psu, np.repeat("z", n), 50, 2)
    t = fairness.group_prevalence(y, w, groups, psu, mult, cfg, 0.95).set_index("group")
    for g in ["a", "b"]:
        m = (groups == g).to_numpy()
        assert t.loc[g, "estimate"] == pytest.approx((w[m] * y[m]).sum() / w[m].sum())
        assert t.loc[g, "ci_low"] <= t.loc[g, "estimate"] <= t.loc[g, "ci_high"]
    assert t.loc["a", "n_group"] == 120 and t.loc["b", "n_group"] == 80


def test_oof_reproduction_guard():
    y = np.array([0, 1, 0, 1, 1])
    p = np.array([0.1, 0.8, 0.3, 0.6, 0.9])
    w = np.ones(5)
    fairness.check_oof_reproduces(y, p, w, 1.0)
    with pytest.raises(RuntimeError):
        fairness.check_oof_reproduces(y, p, w, 0.9)


def test_fairness_never_reads_test_rows():
    tree = ast.parse(inspect.getsource(fairness))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "test_rows"]
    assert calls == []
