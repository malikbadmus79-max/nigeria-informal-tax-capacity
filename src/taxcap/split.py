"""Test-set lock and cross-validation folds (docs/analysis_plan.md section 11).

A share of PSUs (model.holdout_share) is held out as the final test set, drawn within each zone with a
fixed seed (model.split_seed). Training rows are assigned to model.cv_folds folds with StratifiedGroupKFold
(shuffled, random_state = model.split_seed), grouped by PSU and stratified on the CPI-adjusted target. Test rows are returned only by ``Split.test_rows(..., final_evaluation=True)``; every other accessor
returns training rows. No PSU code or row assignment is written to disk: ``python -m taxcap.split`` writes
aggregate summaries only, with a SHA-256 hash of the sorted test PSU list. On a rerun the rebuilt split is
checked against the hash already recorded in outputs/tables/split_summary.csv, and the run stops if it differs.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from taxcap.audit import COVER_FILE, ENTERPRISE_FILE, check_no_identifiers
from taxcap.features import HOUSEHOLD_FILES, FeatureTable, build_features, household_coverage, summary
from taxcap.frame import build_frame
from taxcap.load import PROJECT_ROOT, load_config, read_table


class LockedTestSetError(PermissionError):
    pass


class Split:
    def __init__(self, psu: pd.Series, zone: pd.Series, stratify: pd.Series, cfg: dict):
        """psu, zone and stratify (the CPI-adjusted target): one value per row, aligned on the same index.
        stratify is read for training rows only, to balance the folds."""
        m = cfg["model"]
        self._index = psu.index
        self._psu = psu.astype(str)
        psu_zone = pd.DataFrame({"psu": self._psu, "zone": zone.astype(str)}).drop_duplicates("psu")
        if psu_zone["psu"].duplicated().any():
            raise ValueError("a PSU spans more than one zone")
        rng = np.random.default_rng(int(m["split_seed"]))
        test = []
        for _, g in psu_zone.sort_values(["zone", "psu"]).groupby("zone", sort=True):
            k = max(1, int(round(float(m["holdout_share"]) * len(g))))
            test += list(rng.choice(g["psu"].to_numpy(), size=k, replace=False))
        self._test_psus = frozenset(test)
        self._is_test = self._psu.isin(self._test_psus).to_numpy()
        train_psu = self._psu[~self._is_test]
        y = stratify[~self._is_test].astype(int).to_numpy()
        sgkf = StratifiedGroupKFold(n_splits=int(m["cv_folds"]), shuffle=True, random_state=int(m["split_seed"]))
        folds = sgkf.split(np.zeros(len(train_psu)), y, groups=train_psu.to_numpy())
        fold = pd.Series(-1, index=train_psu.index)
        for k, (_, val) in enumerate(folds):
            fold.iloc[val] = k
        self._fold = fold
        self._zone = zone

    # training-side accessors -----------------------------------------------------------------
    @property
    def train_mask(self) -> np.ndarray:
        return ~self._is_test

    def train_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.loc[self._index[self.train_mask]]

    def folds(self):
        """(train_index, validation_index) pairs within the training set, by fold."""
        for k in sorted(self._fold.unique()):
            yield self._fold.index[self._fold != k], self._fold.index[self._fold == k]

    @property
    def fold_of_training_rows(self) -> pd.Series:
        return self._fold.copy()

    # test accessor ---------------------------------------------------------------------------
    def test_rows(self, df: pd.DataFrame, final_evaluation: bool = False) -> pd.DataFrame:
        if final_evaluation is not True:
            raise LockedTestSetError("test rows are available only for the final evaluation (final_evaluation=True)")
        return df.loc[self._index[self._is_test]]

    # verification ----------------------------------------------------------------------------
    def test_psu_hash(self) -> str:
        return hashlib.sha256("\n".join(sorted(self._test_psus)).encode("utf-8")).hexdigest()

    def summary(self) -> pd.DataFrame:
        is_test = pd.Series(self._is_test, index=self._index)
        rows = []
        for name, mask in [("train", ~is_test), ("test", is_test)]:
            rows.append(("all", name, "enterprises", int(mask.sum())))
            rows.append(("all", name, "PSUs", int(self._psu[mask].nunique())))
        for zone in sorted(self._zone.astype(str).unique()):
            z = self._zone.astype(str) == zone
            for name, mask in [("train", ~is_test), ("test", is_test)]:
                rows.append((zone, name, "enterprises", int((mask & z).sum())))
                rows.append((zone, name, "PSUs", int(self._psu[mask & z].nunique())))
        for k in sorted(self._fold.unique()):
            f = self._fold == k
            rows.append(("all", f"train fold {k}", "enterprises", int(f.sum())))
            rows.append(("all", f"train fold {k}", "PSUs", int(self._psu[f[f].index].nunique())))
        rows.append(("all", "test", "SHA-256 of sorted test PSU list", self.test_psu_hash()))
        return pd.DataFrame(rows, columns=["zone", "set", "measure", "value"])


TARGET_LABELS = [("target_cpi", "CPI-adjusted (primary target)"), ("target_nominal", "nominal (secondary)")]


def training_target_shares(table: FeatureTable, split: Split) -> pd.DataFrame:
    """Weighted share above threshold for each target, on the training set and each training fold only."""
    tr = split.train_rows(table.data)
    fold = split.fold_of_training_rows
    rows = []
    groups = [("train", tr.index)] + [(f"train fold {k}", fold.index[fold == k]) for k in sorted(fold.unique())]
    for name, idx in groups:
        g = tr.loc[idx]
        for target, label in TARGET_LABELS:
            rows.append((name, "all", f"weighted share above threshold, {label}",
                         float((g["weight"] * g[target]).sum() / g["weight"].sum())))
    return pd.DataFrame(rows, columns=["set", "zone", "measure", "value"])


def make_split(fr, cfg: dict) -> Split:
    """Split over the analysis sample, built from the frame before any feature is computed."""
    s = fr.data[fr.data["in_sample"]]
    return Split(s["psu"], s["zone"], s["above_cpi"], cfg)


HASH_MEASURE = "SHA-256 of sorted test PSU list"


class SplitChanged(RuntimeError):
    pass


def recorded_hash(summary_path: Path) -> str | None:
    """Test-PSU hash recorded in an existing split_summary.csv, or None if there is none."""
    if not Path(summary_path).exists():
        return None
    s = pd.read_csv(summary_path)
    rec = s.loc[s["measure"] == HASH_MEASURE, "value"]
    return str(rec.iloc[0]) if len(rec) == 1 else None


def verify_split(split: Split, summary_path: Path) -> str:
    """Refuse to continue if a rebuilt split differs from the one recorded in split_summary.csv."""
    recorded = recorded_hash(summary_path)
    if recorded is not None and recorded != split.test_psu_hash():
        raise SplitChanged(f"test PSU hash {split.test_psu_hash()} does not match the recorded {recorded}")
    return "matches the recorded hash" if recorded else "no recorded hash; recording it"


def run(zip_path=None, out_dir=None, config_path=None):
    cfg = load_config(config_path)
    ent = read_table(ENTERPRISE_FILE, zip_path=zip_path)
    cover = read_table(COVER_FILE, zip_path=zip_path)
    fr = build_frame(ent, cover, cfg)
    household = {f: read_table(f, zip_path=zip_path) for f in HOUSEHOLD_FILES}
    split = make_split(fr, cfg)
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "outputs" / "tables"
    status = verify_split(split, out_dir / "split_summary.csv")   # before anything is overwritten
    print(f"Test PSU hash {split.test_psu_hash()}: {status}")
    table = build_features(fr, ent, household, split.train_mask)

    split_summary = split.summary()
    targets = training_target_shares(table, split)
    feat = summary(table, split.train_mask)
    tables = {"split_summary": pd.concat([split_summary, targets], ignore_index=True),
              "features_summary": feat,
              "features_coverage": household_coverage(fr, household)}
    check_no_identifiers(tables)
    out_dir.mkdir(parents=True, exist_ok=True)
    with pd.option_context("display.width", 200, "display.max_rows", 200, "display.max_colwidth", 70):
        for name, t in tables.items():
            t.to_csv(out_dir / f"{name}.csv", index=False)
            print(f"\n{name}\n{t.to_string(index=False)}")
    return table, split


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", dest="zip_path", default=None)
    ap.add_argument("--out", dest="out_dir", default=None)
    args = ap.parse_args(argv)
    run(zip_path=args.zip_path, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
