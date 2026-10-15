"""Final test evaluation (docs/analysis_plan.md section 13), run once as ``python -m taxcap.evaluate``.

This is the only module that reads test rows (``Split.test_rows(..., final_evaluation=True)``). Before any
data is loaded it checks that config/model_selection.yaml is tracked by git and unchanged since the last
commit; before any test row is read it checks that the test PSU hash matches split_summary.csv. The frozen
artifacts and thresholds are used as they are: nothing is refitted, retuned or re-thresholded.

All metrics are survey-weighted (wt_cross_wave5). Intervals come from bootstrap replicates that resample
test PSUs with replacement within zone. Only aggregate tables are written, to outputs/tables/test_*.csv.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

from taxcap.audit import code_of
from taxcap.model import RULES, TARGET, design_matrix, rates, score_metrics, split_kinds

SELECTION_FILE = Path("config") / "model_selection.yaml"
HASH_MEASURE = "SHA-256 of sorted test PSU list"
OP_KEYS = {"ffr10": "false_flag_rate_at_most_0.10", "rec50": "recall_at_least_0.50"}
RATES = ("recall", "precision", "false_flag_rate")


class EvaluationRefused(RuntimeError):
    pass


# pre-evaluation checks ----------------------------------------------------------------------

def check_selection_committed(repo: Path, rel_path: Path = SELECTION_FILE) -> None:
    """Refuse unless the selection file is tracked and identical to the committed version."""
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(rel_path).replace("\\", "/")],
                             cwd=repo, capture_output=True, text=True)
    if tracked.returncode != 0:
        raise EvaluationRefused(f"{rel_path} is not tracked by git; commit the frozen selection first")
    diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(rel_path).replace("\\", "/")],
                          cwd=repo, capture_output=True, text=True)
    if diff.returncode != 0:
        raise EvaluationRefused(f"{rel_path} differs from the last commit; the frozen selection was changed")


def check_test_hash(split, summary_path: Path) -> None:
    s = pd.read_csv(summary_path)
    recorded = s.loc[s["measure"] == HASH_MEASURE, "value"]
    if len(recorded) != 1 or str(recorded.iloc[0]) != split.test_psu_hash():
        raise EvaluationRefused("test PSU hash does not match split_summary.csv")


# bootstrap ----------------------------------------------------------------------------------

def bootstrap_multiplicities(psu, zone, n_rep: int, seed: int) -> np.ndarray:
    """(n_rep, n_rows) counts: each replicate draws, within each zone, as many PSUs as the zone has, with
    replacement; a row's count is the number of times its PSU was drawn."""
    psu, zone = np.asarray(psu).astype(str), np.asarray(zone).astype(str)
    psus = np.array(sorted(set(psu)))
    pos = {p: i for i, p in enumerate(psus)}
    psu_zone = pd.Series(zone, index=psu).groupby(level=0).first().reindex(psus)
    rng = np.random.default_rng(seed)
    counts = np.zeros((n_rep, psus.size))
    for z in sorted(psu_zone.unique()):
        idx = np.flatnonzero(psu_zone.to_numpy() == z)
        draws = rng.integers(0, idx.size, size=(n_rep, idx.size))
        np.add.at(counts, (np.repeat(np.arange(n_rep), idx.size), idx[draws].ravel()), 1)
    return counts[:, [pos[p] for p in psu]]


def interval(values, point: float, level: float) -> dict:
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    a = (1 - level) / 2
    if v.size < 2:
        return {"estimate": point, "ci_low": np.nan, "ci_high": np.nan, "se": np.nan, "replicates": int(v.size)}
    return {"estimate": point, "ci_low": float(np.quantile(v, a)), "ci_high": float(np.quantile(v, 1 - a)),
            "se": float(np.std(v, ddof=1)), "replicates": int(v.size)}


# metrics ------------------------------------------------------------------------------------

def scorer_metrics(y, score, w, thresholds: dict | None) -> dict:
    """Score metrics plus rates at each frozen threshold (models) or at the rule's own flag (rules)."""
    y, score, w = np.asarray(y, int), np.asarray(score, float), np.asarray(w, float)
    keep = w > 0
    y, score, w = y[keep], score[keep], w[keep]
    if y.min() == y.max():
        out = {"pr_auc": np.nan, "roc_auc": np.nan, "brier": np.nan}
    else:
        out = score_metrics(y, score, w)
    if thresholds is None:
        for k, v in rates(y, score >= 0.5, w).items():
            out[f"rule_{k}"] = v
    else:
        for op, t in thresholds.items():
            for k, v in rates(y, score >= t, w).items():
                out[f"{op}_{k}"] = v
    return out


def metrics_with_intervals(y, score, w, thresholds, mult: np.ndarray, level: float) -> dict:
    point = scorer_metrics(y, score, w, thresholds)
    reps = [scorer_metrics(y, score, w * m, thresholds) for m in mult]
    return {k: interval([r[k] for r in reps], v, level) for k, v in point.items()}


def group_rates(y, flag, w, groups: pd.Series, psu, mult: np.ndarray, cfg: dict, level: float) -> pd.DataFrame:
    """Recall, precision and false-flag rate by group, with bootstrap intervals and the reliability flag
    (plan section 7.3) applied to the units each rate rests on."""
    r = cfg["estimation"]["reliability"]
    y, flag, w, psu = np.asarray(y, bool), np.asarray(flag, bool), np.asarray(w, float), np.asarray(psu)
    rows = []
    for g in sorted(groups.dropna().unique()):
        in_g = (groups == g).to_numpy()
        base = {"recall": in_g & y, "precision": in_g & flag, "false_flag_rate": in_g & ~y}
        point = rates(y[in_g], flag[in_g], w[in_g])
        reps = [rates(y[in_g], flag[in_g], (w * m)[in_g]) for m in mult]
        for k in RATES:
            iv = interval([x[k] for x in reps], point[k], level)
            n, n_psu = int(base[k].sum()), int(np.unique(psu[base[k]]).size)
            rse = iv["se"] / abs(iv["estimate"]) if iv["estimate"] and np.isfinite(iv["se"]) else np.inf
            rows.append({"group": g, "metric": k, **iv, "n_group": int(in_g.sum()), "n_base": n, "psus_base": n_psu,
                         "relative_se": rse,
                         "unreliable": bool(n < r["min_enterprises"] or n_psu < r["min_psus"]
                                            or rse > r["max_relative_se"])})
    return pd.DataFrame(rows)


def calibration(y, p, w, bins: int) -> pd.DataFrame:
    y, p, w = np.asarray(y, float), np.asarray(p, float), np.asarray(w, float)
    decile = pd.qcut(pd.Series(p).rank(method="first"), bins, labels=False)
    rows = []
    for d in range(bins):
        m = (decile == d).to_numpy()
        rows.append({"decile": d + 1, "n": int(m.sum()), "min_predicted": float(p[m].min()),
                     "max_predicted": float(p[m].max()),
                     "weighted_mean_predicted": float((w[m] * p[m]).sum() / w[m].sum()),
                     "weighted_observed": float((w[m] * y[m]).sum() / w[m].sum())})
    return pd.DataFrame(rows)


def importance_groups(cols: list[str], cfg: dict) -> dict[str, list[str]]:
    groups, used = {}, set()
    for name, patterns in cfg["evaluation"]["importance_groups"].items():
        members = [c for c in cols if any(fnmatch.fnmatch(c, pat) for pat in patterns)]
        if members:
            groups[name] = members
            used |= set(members)
    for c in cols:
        if c not in used:
            groups[c] = [c]
    return groups


def permutation_importance(pipe, X: pd.DataFrame, y, w, groups: dict, repeats: int, seed: int) -> pd.DataFrame:
    """Drop in weighted PR-AUC when a group's columns are permuted together (same row permutation)."""
    from sklearn.metrics import average_precision_score
    base = average_precision_score(y, pipe.predict_proba(X)[:, 1], sample_weight=w)
    rng = np.random.default_rng(seed)
    rows = []
    for name, members in groups.items():
        drops = []
        for _ in range(repeats):
            perm = rng.permutation(len(X))
            Xp = X.copy()
            Xp[members] = X[members].iloc[perm].to_numpy()
            drops.append(base - average_precision_score(y, pipe.predict_proba(Xp)[:, 1], sample_weight=w))
        rows.append({"feature_group": name, "columns": len(members), "mean_drop_pr_auc": float(np.mean(drops)),
                     "sd_drop_pr_auc": float(np.std(drops, ddof=1))})
    t = pd.DataFrame(rows).sort_values("mean_drop_pr_auc", ascending=False, kind="mergesort").reset_index(drop=True)
    t.insert(0, "rank", np.arange(1, len(t) + 1))
    return t


# owner groups -------------------------------------------------------------------------------

def owner_groups(owners: pd.DataFrame, roster: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Gender and age band of each enterprise's first listed owner (s8q6_1), from sect1_harvestw5."""
    r = roster.assign(indiv=pd.to_numeric(roster["indiv"], errors="coerce")).drop_duplicates(["hhid", "indiv"])
    r = r.set_index(["hhid", "indiv"])
    key = pd.MultiIndex.from_arrays([owners["hhid"].to_numpy(), pd.to_numeric(owners["owner_1"], errors="coerce").to_numpy()])
    linked = key.isin(r.index)
    sex = pd.Series(np.nan, index=owners.index)
    age = pd.Series(np.nan, index=owners.index)
    sex[linked] = code_of(r.loc[key[linked], "s1q2"]).to_numpy()
    age[linked] = pd.to_numeric(r.loc[key[linked], "s1q6"], errors="coerce").to_numpy()
    gender = pd.Series(np.where(sex == 1, "male", np.where(sex == 2, "female", "missing or unlinked")), index=owners.index)
    band = pd.Series("under 15, missing or unlinked", index=owners.index)
    for lo, hi in cfg["features"]["breakdown_only"]["owner_age"]["bands"]:
        m = (age >= lo) & ((age <= hi) if hi is not None else True)
        band[m] = f"{lo}-{hi}" if hi is not None else f"{lo}+"
    return pd.DataFrame({"owner_gender": gender, "owner_age_band": band, "roster_linked": linked}, index=owners.index)


# run ----------------------------------------------------------------------------------------

def run(zip_path=None, out_dir=None, config_path=None):
    from taxcap.audit import COVER_FILE, ENTERPRISE_FILE, check_no_identifiers
    from taxcap.features import HOUSEHOLD_FILES, build_features
    from taxcap.frame import build_frame
    from taxcap.load import PROJECT_ROOT, load_config, read_table
    from taxcap.split import make_split

    check_selection_committed(PROJECT_ROOT)                       # before any data is loaded
    with open(PROJECT_ROOT / SELECTION_FILE, encoding="utf-8") as f:
        sel = yaml.safe_load(f)
    cfg = load_config(config_path)
    ev = cfg["evaluation"]
    level = float(ev["confidence_level"])

    ent = read_table(ENTERPRISE_FILE, zip_path=zip_path)
    cover = read_table(COVER_FILE, zip_path=zip_path)
    fr = build_frame(ent, cover, cfg)
    split = make_split(fr, cfg)
    if split.test_psu_hash() != sel["test_psu_sha256"]:
        raise EvaluationRefused("test PSU hash does not match config/model_selection.yaml")
    check_test_hash(split, PROJECT_ROOT / "outputs" / "tables" / "split_summary.csv")   # before any test row
    household = {f: read_table(f, zip_path=zip_path) for f in HOUSEHOLD_FILES}
    table = build_features(fr, ent, household, split.train_mask)

    test = split.test_rows(table.data, final_evaluation=True)     # the only test-row access in the project
    y, w = test[TARGET].astype(int).to_numpy(), test["weight"].to_numpy()
    mult = bootstrap_multiplicities(test["psu"], test["zone"], int(ev["bootstrap_replicates"]), int(ev["bootstrap_seed"]))
    pref = (sel["preferred"]["model"], sel["preferred"]["feature_set"])

    scores, metric_rows = {}, []
    for model, sets in sel["models"].items():
        for fs, s in sets.items():
            pipe = joblib.load(PROJECT_ROOT / s["artifact"])
            X = design_matrix(test, *split_kinds(table, table.features(fs)))
            p = pipe.predict_proba(X)[:, 1]
            th = {op: s["thresholds"][key] for op, key in OP_KEYS.items()}
            scores[(model, fs)] = (p, th, pipe, X)
            role = "headline" if (model, fs) == pref else "secondary"
            for metric, iv in metrics_with_intervals(y, p, w, th, mult, level).items():
                metric_rows.append({"model": model, "feature_set": fs, "role": role, "metric": metric, **iv})
    for rule, col in RULES.items():
        flag = (pd.to_numeric(test[col], errors="coerce").fillna(0) > 0).astype(float).to_numpy()
        scores[(rule, "-")] = (flag, None, None, None)
        for metric, iv in metrics_with_intervals(y, flag, w, None, mult, level).items():
            metric_rows.append({"model": rule, "feature_set": "-", "role": "baseline", "metric": metric, **iv})
    prevalence = float((w * y).sum() / w.sum())
    no_skill = [float((w * m * y).sum() / (w * m).sum()) for m in mult]
    metric_rows.append({"model": "no skill", "feature_set": "-", "role": "reference", "metric": "pr_auc",
                        **interval(no_skill, prevalence, level)})
    test_metrics = pd.DataFrame(metric_rows)

    # differences
    p_pref, th_pref = scores[pref][0], scores[pref][1]
    reg = scores[("rule_registered", "-")][0]
    p_b = scores[(pref[0], "B")][0]

    def diff_recall(wt):
        return (scorer_metrics(y, p_pref, wt, th_pref)["ffr10_recall"]
                - scorer_metrics(y, reg, wt, None)["rule_recall"])

    def diff_prauc(wt):
        return scorer_metrics(y, p_b, wt, th_pref)["pr_auc"] - scorer_metrics(y, p_pref, wt, th_pref)["pr_auc"]

    test_differences = pd.DataFrame([
        {"comparison": f"recall at false-flag-rate operating point: {pref[0]} set {pref[1]} minus rule_registered",
         **interval([diff_recall(w * m) for m in mult], diff_recall(w), level)},
        {"comparison": f"PR-AUC: {pref[0]} set B minus set A",
         **interval([diff_prauc(w * m) for m in mult], diff_prauc(w), level)},
    ])

    # groups for the preferred model at the false-flag-rate operating point
    flag = p_pref >= th_pref["ffr10"]
    owners = owner_groups(fr.data.loc[test.index, ["hhid", "owner_1"]], household["sect1_harvestw5"], cfg)
    group_frames = []
    for gtype, g in [("zone", test["zone"].astype(str)),
                     ("urban_rural", pd.Series(np.where(test["urban"] == 1, "urban", "rural"), index=test.index)),
                     ("owner_gender", owners["owner_gender"]), ("owner_age_band", owners["owner_age_band"])]:
        group_frames.append(group_rates(y, flag, w, g, test["psu"], mult, cfg, level).assign(group_type=gtype))
    test_groups = pd.concat(group_frames, ignore_index=True)
    test_groups.insert(0, "group_type", test_groups.pop("group_type"))
    test_groups["roster_linkage_rate"] = float(owners["roster_linked"].mean())

    test_calibration = calibration(y, p_pref, w, int(ev["calibration_bins"]))
    p, th, pipe, X = scores[pref]
    test_importance = permutation_importance(pipe, X, y, w, importance_groups(list(X.columns), cfg),
                                             int(ev["permutation_repeats"]), int(ev["permutation_seed"]))

    tables = {"test_metrics": test_metrics, "test_differences": test_differences, "test_groups": test_groups,
              "test_calibration": test_calibration, "test_importance": test_importance}
    check_no_identifiers(tables)
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "outputs" / "tables"
    for name, t in tables.items():
        t.to_csv(out_dir / f"{name}.csv", index=False)
    print(f"Test evaluation complete: {len(test)} enterprises, {test['psu'].nunique()} PSUs, "
          f"{mult.shape[0]} bootstrap replicates. Tables written to {out_dir}")
    return tables


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", dest="zip_path", default=None)
    ap.add_argument("--out", dest="out_dir", default=None)
    args = ap.parse_args(argv)
    run(zip_path=args.zip_path, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
