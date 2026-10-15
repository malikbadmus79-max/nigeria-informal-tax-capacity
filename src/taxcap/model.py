"""Model training and selection on training PSUs only (docs/analysis_plan.md sections 10-13).

Run as ``python -m taxcap.model``. Every fit and every metric here uses training rows and the
cross-validation folds from taxcap.split; the test set is never read. Preprocessing (imputation, encoding,
scaling) sits inside each pipeline, so it is fitted on the training part of each fold only.

For each model, feature set and hyperparameter configuration, out-of-fold predicted probabilities are
produced for all training rows; hyperparameters are selected by survey-weighted out-of-fold PR-AUC. The
selected configurations, their operating-point thresholds and the preferred model are frozen in
config/model_selection.yaml, and the selected configurations refitted on all training rows are saved to
artifacts/ (not tracked by git). Only aggregate tables are written to outputs/tables/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import ParameterGrid
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from taxcap.features import FeatureTable
from taxcap.split import Split

TARGET = "target_cpi"   # primary model target (plan section 10.1)
MODELS = ("logistic_regression", "hist_gradient_boosting")
FEATURE_SETS = ("A", "B")
RULES = {"rule_registered": "registered", "rule_any_non_household_employee": "non_household_employees"}
OP_FFR, OP_RECALL = "false_flag_rate_max", "recall_min"


# design matrix and pipelines ----------------------------------------------------------------

def split_kinds(table: FeatureTable, cols: list[str]) -> tuple[list[str], list[str]]:
    kinds = {s.name: s.kind for s in table.specs}
    categorical = [c for c in cols if kinds[c] == "categorical"]
    return categorical, [c for c in cols if c not in categorical]


def design_matrix(df: pd.DataFrame, categorical: list[str], numeric: list[str]) -> pd.DataFrame:
    """Stateless type conversion: categoricals as objects with np.nan for missing, numerics as floats."""
    X = pd.DataFrame(index=df.index)
    for c in categorical:
        X[c] = df[c].astype(object).where(df[c].notna(), np.nan)
    for c in numeric:
        X[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return X


def make_pipeline(model: str, params: dict, categorical: list[str], numeric: list[str], random_state: int) -> Pipeline:
    if model == "logistic_regression":
        pre = ColumnTransformer([
            ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                              ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), categorical),
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")),
                              ("scale", StandardScaler())]), numeric),
        ])
        clf = LogisticRegression(C=params["C"], max_iter=5000)
    elif model == "hist_gradient_boosting":
        pre = ColumnTransformer([
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan,
                                   encoded_missing_value=np.nan), categorical),
            ("num", "passthrough", numeric),   # missing values are handled natively
        ])
        clf = HistGradientBoostingClassifier(
            categorical_features=[True] * len(categorical) + [False] * len(numeric),
            early_stopping=False, random_state=random_state, **params)
    else:
        raise ValueError(f"unknown model: {model}")
    return Pipeline([("pre", pre), ("clf", clf)])


def grid(model: str, cfg: dict) -> list[dict]:
    return list(ParameterGrid(cfg["model"]["grids"][model]))


def _fit(pipe: Pipeline, X: pd.DataFrame, y: pd.Series, w: pd.Series | None) -> Pipeline:
    if w is None:
        return pipe.fit(X, y)
    return pipe.fit(X, y, clf__sample_weight=(w / w.mean()).to_numpy())   # weights rescaled to mean 1


def oof_predict(table: FeatureTable, split: Split, cols: list[str], model: str, params: dict, cfg: dict,
                weighted: bool = False, return_models: bool = False):
    """Out-of-fold probabilities for every training row; each fold's pipeline is fitted on that fold's
    training part only."""
    tr = split.train_rows(table.data)
    categorical, numeric = split_kinds(table, cols)
    X = design_matrix(tr, categorical, numeric)
    y = tr[TARGET].astype(int)
    w = tr["weight"] if weighted else None
    oof = pd.Series(np.nan, index=tr.index)
    fitted = []
    for train_idx, val_idx in split.folds():
        pipe = make_pipeline(model, params, categorical, numeric, int(cfg["model"]["random_state"]))
        _fit(pipe, X.loc[train_idx], y.loc[train_idx], None if w is None else w.loc[train_idx])
        oof.loc[val_idx] = pipe.predict_proba(X.loc[val_idx])[:, 1]
        fitted.append((train_idx, pipe))
    if oof.isna().any():
        raise RuntimeError("some training rows received no out-of-fold prediction")
    return (oof, fitted) if return_models else oof


# weighted metrics ---------------------------------------------------------------------------

def rates(y, flag, w) -> dict:
    y, flag, w = np.asarray(y, bool), np.asarray(flag, bool), np.asarray(w, float)
    tp, fp = w[y & flag].sum(), w[~y & flag].sum()
    pos, neg = w[y].sum(), w[~y].sum()
    return {"recall": tp / pos if pos else np.nan,
            "precision": tp / (tp + fp) if tp + fp else np.nan,
            "false_flag_rate": fp / neg if neg else np.nan}


def operating_point(y, p, w, kind: str, bound: float) -> dict:
    """Threshold t (flag p >= t) for an operating point on weighted rates.

    OP_FFR: the threshold with the highest recall whose false-flag rate is at most bound (ties go to the
    higher threshold). OP_RECALL: the highest threshold whose recall is at least bound.
    """
    y, p, w = np.asarray(y, bool), np.asarray(p, float), np.asarray(w, float)
    order = np.argsort(-p, kind="mergesort")
    ps, ys, ws = p[order], y[order], w[order]
    tp, fp = np.cumsum(ws * ys), np.cumsum(ws * ~ys)
    last = np.r_[np.nonzero(np.diff(ps))[0], len(ps) - 1]   # last index of each distinct threshold
    t, tp, fp = ps[last], tp[last], fp[last]
    pos, neg = (ws * ys).sum(), (ws * ~ys).sum()
    recall, ffr = tp / pos, fp / neg
    precision = tp / (tp + fp)
    if kind == OP_FFR:
        ok = ffr <= bound
    elif kind == OP_RECALL:
        ok = recall >= bound
    else:
        raise ValueError(f"unknown operating point: {kind}")
    if not ok.any():
        return {"threshold": np.nan, "recall": np.nan, "precision": np.nan, "false_flag_rate": np.nan}
    if kind == OP_FFR:
        i = np.flatnonzero(ok)[np.argmax(recall[ok])]   # first max = highest threshold among ties
    else:
        i = np.flatnonzero(ok)[0]   # thresholds run from high to low: the first that reaches the bound
    return {"threshold": float(t[i]), "recall": float(recall[i]), "precision": float(precision[i]),
            "false_flag_rate": float(ffr[i])}


def score_metrics(y, p, w) -> dict:
    return {"pr_auc": float(average_precision_score(y, p, sample_weight=w)),
            "roc_auc": float(roc_auc_score(y, p, sample_weight=w)),
            "brier": float(brier_score_loss(y, p, sample_weight=w))}


def evaluate(y, p, w, cfg: dict) -> dict:
    op = cfg["model"]["operating_points"]
    out = score_metrics(y, p, w)
    for name, kind, bound in [("op_ffr10", OP_FFR, op["max_false_flag_rate"]),
                              ("op_rec50", OP_RECALL, op["min_recall"])]:
        for k, v in operating_point(y, p, w, kind, bound).items():
            out[f"{name}_{k}"] = v
    return out


def evaluate_rule(y, flag, w) -> dict:
    """Rule baselines have one operating point: the rule's own flag."""
    out = score_metrics(y, flag, w)
    r = rates(y, flag, w)
    for name in ["op_ffr10", "op_rec50"]:
        out.update({f"{name}_threshold": np.nan, f"{name}_recall": np.nan, f"{name}_precision": np.nan,
                    f"{name}_false_flag_rate": np.nan})
    out.update({"rule_recall": r["recall"], "rule_precision": r["precision"], "rule_false_flag_rate": r["false_flag_rate"]})
    return out


# cross-validation and selection -------------------------------------------------------------

def cross_validate(table: FeatureTable, split: Split, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    tr = split.train_rows(table.data)
    y, w = tr[TARGET].astype(int), tr["weight"]
    results, selected_rows, selected = [], [], {}
    for fs in FEATURE_SETS:
        cols = table.features(fs)
        for model in MODELS:
            best = None
            for i, params in enumerate(grid(model, cfg)):
                oof = oof_predict(table, split, cols, model, params, cfg)
                pr = float(average_precision_score(y, oof, sample_weight=w))
                results.append({"model": model, "feature_set": fs, "config": i, "params": json.dumps(params, sort_keys=True),
                                "weighted_oof_pr_auc": pr})
                if best is None or pr > best[0]:   # strict: ties keep the earlier configuration
                    best = (pr, i, params, oof)
            pr, i, params, oof = best
            m = evaluate(y, oof, w, cfg)
            selected[(model, fs)] = {"params": params, "config": i, "metrics": m}
            selected_rows.append({"model": model, "feature_set": fs, "training": "unweighted",
                                  "params": json.dumps(params, sort_keys=True), **m})
            oof_w = oof_predict(table, split, cols, model, params, cfg, weighted=True)
            selected_rows.append({"model": model, "feature_set": fs, "training": "weighted (sensitivity)",
                                  "params": json.dumps(params, sort_keys=True), **evaluate(y, oof_w, w, cfg)})
    for rule, col in RULES.items():
        flag = (pd.to_numeric(tr[col], errors="coerce").fillna(0) > 0).astype(int)
        selected_rows.append({"model": rule, "feature_set": "-", "training": "none (rule)", "params": "",
                              **evaluate_rule(y, flag, w)})
    cv_results = pd.DataFrame(results)
    cv_results["selected"] = [selected[(r.model, r.feature_set)]["config"] == r.config for r in cv_results.itertuples()]
    cv_selected = pd.DataFrame(selected_rows)
    cv_selected["no_skill_pr_auc"] = float((w * y).sum() / w.sum())
    return cv_results, cv_selected, selected


def preferred_model(selected: dict, cfg: dict) -> dict:
    fs = cfg["model"]["preferred_feature_set"]
    tie = float(cfg["model"]["near_tie_pr_auc"])
    lr = selected[("logistic_regression", fs)]["metrics"]["pr_auc"]
    hgb = selected[("hist_gradient_boosting", fs)]["metrics"]["pr_auc"]
    model = "hist_gradient_boosting" if hgb - lr > tie else "logistic_regression"
    return {"model": model, "feature_set": fs,
            "rule": f"highest weighted out-of-fold PR-AUC on feature set {fs}; logistic regression preferred "
                    f"unless gradient boosting is higher by more than {tie}"}


def fit_selected(table: FeatureTable, split: Split, selected: dict, cfg: dict) -> dict:
    """Refit each selected configuration on all training rows (unweighted)."""
    tr = split.train_rows(table.data)
    y = tr[TARGET].astype(int)
    fitted = {}
    for (model, fs), s in selected.items():
        categorical, numeric = split_kinds(table, table.features(fs))
        pipe = make_pipeline(model, s["params"], categorical, numeric, int(cfg["model"]["random_state"]))
        fitted[(model, fs)] = _fit(pipe, design_matrix(tr, categorical, numeric), y, None)
    return fitted


REVISIONS = [
    "2026-10-15: second operating point changed from precision >= 0.50 to recall >= 0.50 (highest threshold with "
    "weighted out-of-fold recall >= 0.50), after cross-validation and before any test evaluation. At a weighted "
    "prevalence of 0.44 the precision rule selected near-total flagging (false-flag rate about 0.77). "
    "Hyperparameters and the preferred model are unchanged.",
]


def assert_selection_unchanged(previous: dict, record: dict) -> None:
    """Hyperparameters and the preferred model must match a previously frozen selection."""
    for model, sets in previous["models"].items():
        for fs, old in sets.items():
            new = record["models"][model][fs]["params"]
            if new != old["params"]:
                raise RuntimeError(f"hyperparameters changed for {model} {fs}: {old['params']} -> {new}")
    if {k: previous["preferred"][k] for k in ("model", "feature_set")} != \
            {k: record["preferred"][k] for k in ("model", "feature_set")}:
        raise RuntimeError(f"preferred model changed: {previous['preferred']} -> {record['preferred']}")


def selection_record(selected: dict, preferred: dict, split: Split, cfg: dict, artifacts: dict) -> dict:
    def clean(v):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)

    models = {}
    for (model, fs), s in selected.items():
        m = s["metrics"]
        models.setdefault(model, {})[fs] = {
            "params": {k: (float(v) if isinstance(v, (float, np.floating)) else int(v) if isinstance(v, (int, np.integer)) else v)
                       for k, v in s["params"].items()},
            "weighted_oof_pr_auc": clean(m["pr_auc"]),
            "thresholds": {"false_flag_rate_at_most_0.10": clean(m["op_ffr10_threshold"]),
                           "recall_at_least_0.50": clean(m["op_rec50_threshold"])},
            "artifact": artifacts.get((model, fs)),
        }
    return {
        "frozen_on": dt.date.today().isoformat(),
        "note": "Selected on out-of-fold predictions for training PSUs only; the test set was not accessed.",
        "revisions": REVISIONS,
        "target": TARGET,
        "selection_metric": cfg["model"]["selection_metric"],
        "training": "unweighted (plan section 12)",
        "test_psu_sha256": split.test_psu_hash(),
        "models": models,
        "preferred": preferred,
    }


def run(zip_path=None, out_dir=None, config_path=None, artifacts_dir=None, selection_path=None):
    from taxcap.audit import COVER_FILE, ENTERPRISE_FILE, check_no_identifiers
    from taxcap.features import HOUSEHOLD_FILES, build_features
    from taxcap.frame import build_frame
    from taxcap.load import PROJECT_ROOT, load_config, read_table
    from taxcap.split import make_split

    cfg = load_config(config_path)
    ent = read_table(ENTERPRISE_FILE, zip_path=zip_path)
    cover = read_table(COVER_FILE, zip_path=zip_path)
    fr = build_frame(ent, cover, cfg)
    split = make_split(fr, cfg)
    table = build_features(fr, ent, {f: read_table(f, zip_path=zip_path) for f in HOUSEHOLD_FILES}, split.train_mask)

    cv_results, cv_selected, selected = cross_validate(table, split, cfg)
    preferred = preferred_model(selected, cfg)

    artifacts_dir = Path(artifacts_dir) if artifacts_dir else PROJECT_ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for key, pipe in fit_selected(table, split, selected, cfg).items():
        path = artifacts_dir / f"{key[0]}_{key[1]}.joblib"
        joblib.dump(pipe, path)
        artifacts[key] = f"artifacts/{path.name}"

    selection_path = Path(selection_path) if selection_path else PROJECT_ROOT / "config" / "model_selection.yaml"
    record = selection_record(selected, preferred, split, cfg, artifacts)
    if selection_path.exists():   # a rerun may change thresholds, never the frozen hyperparameters or preferred model
        with open(selection_path, encoding="utf-8") as f:
            assert_selection_unchanged(yaml.safe_load(f), record)
    with open(selection_path, "w", encoding="utf-8") as f:
        f.write("# Frozen model selection (written by taxcap.model before any test evaluation). Do not edit.\n")
        yaml.safe_dump(record, f, sort_keys=False)

    tables = {"cv_results": cv_results, "cv_selected": cv_selected}
    check_no_identifiers(tables)
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "outputs" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, t in tables.items():
        t.to_csv(out_dir / f"{name}.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 40, "display.float_format", lambda x: f"{x:.4f}"):
        print(cv_selected.drop(columns=["params"]).to_string(index=False))
    print(f"\nPreferred: {preferred}")
    return cv_results, cv_selected, selected


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", dest="zip_path", default=None)
    ap.add_argument("--out", dest="out_dir", default=None)
    args = ap.parse_args(argv)
    run(zip_path=args.zip_path, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
