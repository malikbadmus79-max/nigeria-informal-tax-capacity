import ast
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from taxcap import evaluate
from taxcap.load import PROJECT_ROOT, load_config
from taxcap.model import rates


@pytest.fixture
def cfg():
    return load_config()


def git(repo, *args):
    subprocess.run(["git", "-c", "user.email=t@example.org", "-c", "user.name=test", *args], cwd=repo,
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "model_selection.yaml").write_text("preferred: {model: logistic_regression}\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "config/model_selection.yaml")
    git(tmp_path, "commit", "-q", "-m", "freeze")
    return tmp_path


def test_refuses_when_selection_differs_from_commit(repo):
    evaluate.check_selection_committed(repo)   # unchanged: passes
    path = repo / "config" / "model_selection.yaml"
    path.write_text("preferred: {model: hist_gradient_boosting}\n")
    with pytest.raises(evaluate.EvaluationRefused):
        evaluate.check_selection_committed(repo)
    git(repo, "add", "config/model_selection.yaml")   # staged but not committed: still refused
    with pytest.raises(evaluate.EvaluationRefused):
        evaluate.check_selection_committed(repo)


def test_refuses_when_selection_untracked(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "model_selection.yaml").write_text("x: 1\n")
    git(tmp_path, "init", "-q")
    with pytest.raises(evaluate.EvaluationRefused):
        evaluate.check_selection_committed(tmp_path)


def test_refuses_on_test_hash_mismatch(tmp_path):
    class FakeSplit:
        def test_psu_hash(self):
            return "abc"
    p = tmp_path / "split_summary.csv"
    pd.DataFrame({"zone": ["all"], "set": ["test"], "measure": [evaluate.HASH_MEASURE], "value": ["xyz"]}).to_csv(p, index=False)
    with pytest.raises(evaluate.EvaluationRefused):
        evaluate.check_test_hash(FakeSplit(), p)
    pd.DataFrame({"zone": ["all"], "set": ["test"], "measure": [evaluate.HASH_MEASURE], "value": ["abc"]}).to_csv(p, index=False)
    evaluate.check_test_hash(FakeSplit(), p)


def bootstrap_data():
    psu = np.repeat([f"p{i}" for i in range(12)], 5)
    zone = np.repeat([f"z{i % 3}" for i in range(12)], 5)
    return psu, zone


def test_bootstrap_deterministic_and_within_zone():
    psu, zone = bootstrap_data()
    a = evaluate.bootstrap_multiplicities(psu, zone, 200, 7)
    b = evaluate.bootstrap_multiplicities(psu, zone, 200, 7)
    c = evaluate.bootstrap_multiplicities(psu, zone, 200, 8)
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    # rows of one PSU share a count; each zone draws as many PSUs as it has (4 PSUs x 5 rows)
    assert (a[:, psu == "p0"] == a[:, [0]]).all()
    for z in ["z0", "z1", "z2"]:
        assert (a[:, zone == z].sum(axis=1) == 4 * 5).all()


def test_group_rates_reproduce_overall_with_one_group(cfg):
    rng = np.random.default_rng(3)
    n = 300
    psu = np.repeat([f"p{i}" for i in range(30)], 10)
    y = rng.uniform(size=n) < 0.4
    flag = rng.uniform(size=n) < 0.3
    w = rng.uniform(1, 5, n)
    mult = evaluate.bootstrap_multiplicities(psu, np.repeat("z", n), 50, 1)
    g = evaluate.group_rates(y, flag, w, pd.Series("all", index=range(n)), psu, mult, cfg, 0.95)
    overall = rates(y, flag, w)
    for k in evaluate.RATES:
        assert g.loc[g["metric"] == k, "estimate"].iloc[0] == pytest.approx(overall[k])
    assert (g["n_group"] == n).all()


def test_interval_and_calibration():
    iv = evaluate.interval(np.arange(1001) / 1000, 0.5, 0.95)
    assert iv["ci_low"] == pytest.approx(0.025) and iv["ci_high"] == pytest.approx(0.975)
    rng = np.random.default_rng(0)
    p = rng.uniform(size=200)
    y = (rng.uniform(size=200) < p).astype(int)
    cal = evaluate.calibration(y, p, np.ones(200), 10)
    assert len(cal) == 10 and cal["n"].sum() == 200
    assert (cal["min_predicted"].diff().dropna() > 0).all()


def test_importance_groups(cfg):
    cols = ["zone", "asset_301", "asset_312", "asset_types_owned", "wall_material", "roof_material",
            "floor_material", "registered"]
    g = evaluate.importance_groups(cols, cfg)
    assert g["durable_assets"] == ["asset_301", "asset_312", "asset_types_owned"]
    assert g["housing"] == ["wall_material", "roof_material", "floor_material"]
    assert g["zone"] == ["zone"] and g["registered"] == ["registered"]
    assert sum(len(v) for v in g.values()) == len(cols)


def unlocked_test_row_calls(source: str) -> int:
    """Count real calls ``<obj>.test_rows(..., final_evaluation=True)`` in code; docstrings and comments
    are not Call nodes, so they never count."""
    n = 0
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "test_rows"
                and any(k.arg == "final_evaluation" and isinstance(k.value, ast.Constant) and k.value.value is True
                        for k in node.keywords)):
            n += 1
    return n


def test_only_evaluate_calls_the_test_accessor():
    callers = {p.name: unlocked_test_row_calls(p.read_text(encoding="utf-8"))
               for p in (PROJECT_ROOT / "src" / "taxcap").glob("*.py")}
    assert {k: v for k, v in callers.items() if v} == {"evaluate.py": 1}


def test_call_detector_ignores_text_and_finds_calls():
    text_only = '''"""Use split.test_rows(df, final_evaluation=True) only in evaluate."""
# split.test_rows(df, final_evaluation=True)
x = "split.test_rows(df, final_evaluation=True)"
'''
    assert unlocked_test_row_calls(text_only) == 0
    assert unlocked_test_row_calls("split.test_rows(df, final_evaluation=True)") == 1
    assert unlocked_test_row_calls("s.test_rows(df, final_evaluation=False)") == 0
    assert unlocked_test_row_calls("s.test_rows(df)") == 0
