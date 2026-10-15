import ast
import inspect

import numpy as np
import pandas as pd
import pytest

from taxcap import charts

ZONES = ["1. North Central", "2. North East", "3. North West", "4. South East", "5. South South", "6. South West"]
CI = dict(se=0.01, ci_low=0.1, ci_high=0.3)


def write(d, name, rows):
    pd.DataFrame(rows).to_csv(d / f"{name}.csv", index=False)


@pytest.fixture
def tables(tmp_path):
    d = tmp_path / "tables"
    d.mkdir()
    write(d, "est_headline", [{"price_basis": b, "estimate": e, "ci_low": e - .03, "ci_high": e + .03, "n": 3000}
                              for b, e in [("nominal", .2), ("cpi", .44)]])
    write(d, "est_sensitivity", [{"scenario": s, "price_basis": b, "measure": "share above threshold",
                                  "estimate": e + k * .01} for k, s in enumerate(["primary", "x12", "fixed"])
                                 for b, e in [("nominal", .2), ("cpi", .44)]])
    write(d, "est_domains", [{"domain_type": "zone", "domain": z, "price_basis": b, "estimate": .1 + .05 * i,
                              "ci_low": .05 + .05 * i, "ci_high": .15 + .05 * i, "n": 500}
                             for i, z in enumerate(ZONES) for b in ["nominal", "cpi"]])
    reg = "share officially registered with the government (s8q11)"
    pay = "share payments to government or non-government local authorities to allow operation (s8q11b)"
    rows = [{"measure": m, "group": "all enterprises in the analysis sample", "price_basis": "either",
             "estimate": .3, **CI, "n": 3000} for m in [reg, pay]]
    for b in ["nominal", "cpi"]:
        for m in [reg, pay]:
            for g in ["above threshold", "at or below threshold"]:
                rows.append({"measure": m, "group": g, "price_basis": b, "estimate": .25, **CI, "n": 1000})
        rows.append({"measure": "share pays (s8q11b) and not registered (s8q11)", "group": "at or below threshold",
                     "price_basis": b, "estimate": .2, **CI, "n": 1000})
    write(d, "est_registration_payments", rows)
    met = []
    for model, fs, role in [("logistic_regression", "A", "headline"), ("hist_gradient_boosting", "A", "secondary")]:
        for k in ["pr_auc", "roc_auc", "brier"] + [f"{op}_{r}" for op in ["ffr10", "rec50"]
                                                   for r in ["recall", "precision", "false_flag_rate"]]:
            met.append({"model": model, "feature_set": fs, "role": role, "metric": k, "estimate": .5, **CI})
    for k in ["pr_auc", "rule_recall", "rule_precision", "rule_false_flag_rate"]:
        met.append({"model": "rule_registered", "feature_set": "-", "role": "baseline", "metric": k, "estimate": .2, **CI})
    write(d, "test_metrics", met)
    write(d, "split_summary", [{"zone": "all", "set": "test", "measure": "enterprises", "value": 665}])
    og = []
    for gt, groups in [("owner_gender", ["female", "male", "missing or unlinked"]), ("urban_rural", ["rural", "urban"]),
                       ("zone", ZONES)]:
        for g in groups:
            for metric in ["prevalence", "recall", "precision", "false_flag_rate"]:
                og.append({"group_type": gt, "group": g, "metric": metric, "estimate": .2, **CI, "n_group": 100,
                           "unreliable": g == "male"})
    write(d, "oof_groups", og)
    write(d, "test_importance", [{"rank": i + 1, "feature_group": f, "columns": 1, "mean_drop_pr_auc": .05 - .01 * i,
                                  "sd_drop_pr_auc": .005} for i, f in enumerate(["premises", "durable_assets", "zone"])])
    p = np.linspace(.05, .95, 10)
    write(d, "test_calibration", [{"decile": i + 1, "n": 66, "weighted_mean_predicted": x,
                                   "weighted_observed": x + .02} for i, x in enumerate(p)])
    return d


def test_every_figure_produced(tables, tmp_path):
    out = tmp_path / "figs"
    paths = charts.run(out_dir=out, tables_dir=tables)
    assert sorted(p.name for p in paths) == sorted(charts.FIGURES_PRODUCED)
    for name in charts.FIGURES_PRODUCED:
        assert (out / name).stat().st_size > 10_000


def test_charts_never_reads_survey_data():
    src = inspect.getsource(charts)
    assert "data_raw" not in src and "read_table" not in src and "zipfile" not in src
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert not any(m and m.startswith("taxcap") for m in imported)


def test_price_basis_labels_and_wording():
    assert charts.BASES["nominal"][0] == "if incomes have not grown since 2023/24"
    assert charts.BASES["cpi"][0] == "if incomes kept pace with inflation"
    src = inspect.getsource(charts).lower()
    assert " tax" not in src.replace("taxcap", "") and "levy" not in src and "levies" not in src
