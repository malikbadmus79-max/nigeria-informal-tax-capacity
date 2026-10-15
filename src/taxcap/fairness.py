"""Supplementary group error rates on out-of-fold training predictions (plan section 13.3).

Run as ``python -m taxcap.fairness``. Added after the test evaluation; it reads training rows only and
changes no model, threshold or test result. The preferred model (config/model_selection.yaml) is refitted
within the five training folds with its frozen hyperparameters, exactly as in taxcap.model, and the
resulting out-of-fold predictions are checked against the frozen out-of-fold PR-AUC before use. Units are
flagged at the frozen false-flag-rate threshold.

For each group (zone, urban/rural, owner gender, owner age band) the table reports the weighted share above
the threshold (prevalence) and weighted recall, precision and false-flag rate, with intervals from a
bootstrap over training PSUs within zone and the reliability flag of plan section 7.3. Writes the aggregate
table outputs/tables/oof_groups.csv.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score

from taxcap.evaluate import SELECTION_FILE, bootstrap_multiplicities, group_rates, interval, owner_groups
from taxcap.model import TARGET, oof_predict

FFR_THRESHOLD_KEY = "false_flag_rate_at_most_0.10"


def group_prevalence(y, w, groups: pd.Series, psu, mult: np.ndarray, cfg: dict, level: float) -> pd.DataFrame:
    """Weighted share above the threshold by group, with bootstrap interval and reliability flag."""
    r = cfg["estimation"]["reliability"]
    y, w, psu = np.asarray(y, float), np.asarray(w, float), np.asarray(psu)
    rows = []
    for g in sorted(groups.dropna().unique()):
        m_g = (groups == g).to_numpy()
        point = float((w[m_g] * y[m_g]).sum() / w[m_g].sum())
        reps = []
        for m in mult:
            wm = (w * m)[m_g]
            reps.append((wm * y[m_g]).sum() / wm.sum() if wm.sum() > 0 else np.nan)
        iv = interval(reps, point, level)
        n, n_psu = int(m_g.sum()), int(np.unique(psu[m_g]).size)
        rse = iv["se"] / abs(point) if point and np.isfinite(iv["se"]) else np.inf
        rows.append({"group": g, "metric": "prevalence", **iv, "n_group": n, "n_base": n, "psus_base": n_psu,
                     "relative_se": rse,
                     "unreliable": bool(n < r["min_enterprises"] or n_psu < r["min_psus"]
                                        or rse > r["max_relative_se"])})
    return pd.DataFrame(rows)


def check_oof_reproduces(y, oof, w, frozen_pr_auc: float, tol: float = 1e-9) -> None:
    pr = float(average_precision_score(y, oof, sample_weight=w))
    if abs(pr - frozen_pr_auc) > tol:
        raise RuntimeError(f"out-of-fold PR-AUC {pr} does not reproduce the frozen value {frozen_pr_auc}")


def run(zip_path=None, out_dir=None, config_path=None):
    from taxcap.audit import COVER_FILE, ENTERPRISE_FILE, check_no_identifiers
    from taxcap.features import HOUSEHOLD_FILES, build_features
    from taxcap.frame import build_frame
    from taxcap.load import PROJECT_ROOT, load_config, read_table
    from taxcap.split import make_split

    cfg = load_config(config_path)
    with open(PROJECT_ROOT / SELECTION_FILE, encoding="utf-8") as f:
        sel = yaml.safe_load(f)
    model, fs = sel["preferred"]["model"], sel["preferred"]["feature_set"]
    frozen = sel["models"][model][fs]
    ev = cfg["evaluation"]
    level = float(ev["confidence_level"])

    ent = read_table(ENTERPRISE_FILE, zip_path=zip_path)
    cover = read_table(COVER_FILE, zip_path=zip_path)
    fr = build_frame(ent, cover, cfg)
    split = make_split(fr, cfg)
    if split.test_psu_hash() != sel["test_psu_sha256"]:
        raise RuntimeError("split does not match the frozen selection")
    household = {f: read_table(f, zip_path=zip_path) for f in HOUSEHOLD_FILES}
    table = build_features(fr, ent, household, split.train_mask)

    tr = split.train_rows(table.data)
    y, w = tr[TARGET].astype(int).to_numpy(), tr["weight"].to_numpy()
    oof = oof_predict(table, split, table.features(fs), model, frozen["params"], cfg)
    check_oof_reproduces(y, oof.loc[tr.index], w, frozen["weighted_oof_pr_auc"])
    flag = oof.loc[tr.index].to_numpy() >= frozen["thresholds"][FFR_THRESHOLD_KEY]

    mult = bootstrap_multiplicities(tr["psu"], tr["zone"], int(ev["bootstrap_replicates"]), int(ev["bootstrap_seed"]))
    owners = owner_groups(fr.data.loc[tr.index, ["hhid", "owner_1"]], household["sect1_harvestw5"], cfg)
    frames = []
    for gtype, g in [("zone", tr["zone"].astype(str)),
                     ("urban_rural", pd.Series(np.where(tr["urban"] == 1, "urban", "rural"), index=tr.index)),
                     ("owner_gender", owners["owner_gender"]), ("owner_age_band", owners["owner_age_band"])]:
        part = pd.concat([group_prevalence(y, w, g, tr["psu"], mult, cfg, level),
                          group_rates(y, flag, w, g, tr["psu"], mult, cfg, level)], ignore_index=True)
        frames.append(part.assign(group_type=gtype))
    out = pd.concat(frames, ignore_index=True)
    out.insert(0, "group_type", out.pop("group_type"))
    out["roster_linkage_rate"] = float(owners["roster_linked"].mean())
    out["model"], out["feature_set"], out["threshold"] = model, fs, frozen["thresholds"][FFR_THRESHOLD_KEY]

    check_no_identifiers({"oof_groups": out})
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "outputs" / "tables"
    out.to_csv(out_dir / "oof_groups.csv", index=False)
    print(f"Out-of-fold group rates: {len(tr)} training enterprises, {tr['psu'].nunique()} PSUs, "
          f"{mult.shape[0]} bootstrap replicates. Written to {out_dir / 'oof_groups.csv'}")
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", dest="zip_path", default=None)
    ap.add_argument("--out", dest="out_dir", default=None)
    args = ap.parse_args(argv)
    run(zip_path=args.zip_path, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
