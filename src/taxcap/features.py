"""Feature table for the primary analysis sample (docs/analysis_plan.md section 10), built in memory.

One row per enterprise, indexed like the analysis frame. Features follow config ``features``: enterprise
variables from sect8b, location from the frame, and household variables merged by hhid, with per-member
answers turned into "any member" indicators (missing when no member answered). Categorical features keep
their leading codes. Category frequencies are computed on training rows only: codes held by fewer than
``rare_category.min_share`` of training rows, and codes not seen in training, map to
``rare_category.merge_code``. A household with no row in a source file gets missing values, never 0 or
"no". Missing values are left in place; they are handled inside the model pipeline, fitted on training
data only.

The table is never written to disk.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from taxcap.audit import code_of
from taxcap.frame import AnalysisFrame

HOUSEHOLD_FILES = ["sect5b_plantingw5", "sect5a1_plantingw5", "sect9_harvestw5", "sect10_plantingw5", "sect1_harvestw5"]
YES = 1
EXCLUDED_ITEM = 3341   # durable item "Other (Specify)"
TARGETS = {"target_cpi": "above_cpi", "target_nominal": "above_nominal"}   # primary, secondary (plan section 10.1)
DESIGN_COLUMNS = ["weight", "psu", "stratum"]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    file: str
    variables: tuple[str, ...]
    kind: str   # categorical | binary | count | numeric


@dataclass
class FeatureTable:
    data: pd.DataFrame                 # features, targets and design columns for the analysis sample
    specs: list[FeatureSpec]
    set_a: list[str]                   # base feature columns
    set_b: list[str]                   # set A plus local authority payments

    def features(self, feature_set: str) -> list[str]:
        return {"A": self.set_a, "B": self.set_b}[feature_set]


def _any_member_yes(table: pd.DataFrame, variable: str) -> pd.Series:
    """1 if any member answers YES, 0 if at least one member answers and none YES, missing otherwise."""
    code = code_of(table[variable])
    answered = code.notna().groupby(table["hhid"]).any()
    yes = (code == YES).groupby(table["hhid"]).any()
    return yes.astype(float).where(answered)


def _yes_no(s: pd.Series) -> pd.Series:
    code = code_of(s)
    return (code == YES).astype(float).where(code.notna())


def _merge_rare(codes: pd.Series, train, cfg: dict) -> pd.Series:
    """Keep codes held by at least min_share of non-missing training rows; map every other code, including
    codes unseen in training, to merge_code. Missing stays missing."""
    rule = cfg["features"]["rare_category"]
    train = np.asarray(train, dtype=bool)
    share = codes[train].value_counts(normalize=True)
    keep = share.index[share >= rule["min_share"]]
    out = codes.where(codes.isin(keep) | codes.isna(), rule["merge_code"])
    return out.astype("Int64").astype("string")


def _spec_variables(spec: dict) -> tuple[str, ...]:
    return tuple(spec["variables"]) if "variables" in spec else (spec["variable"],)


def household_coverage(fr: AnalysisFrame, household: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Analysis-sample enterprises whose household has no row in each household-level source file."""
    hhid = fr.data.loc[fr.data["in_sample"], "hhid"]
    return pd.DataFrame([{"source_file": f, "analysis_sample_enterprises": len(hhid),
                          "enterprises_without_household_row": int((~hhid.isin(household[f]["hhid"])).sum())}
                         for f in HOUSEHOLD_FILES])


def build_features(fr: AnalysisFrame, ent: pd.DataFrame, household: dict[str, pd.DataFrame], train) -> FeatureTable:
    """train: boolean mask over the analysis-sample rows (frame order); rare-category frequencies use it only."""
    cfg = fr.cfg
    fcfg = cfg["features"]
    s = fr.data[fr.data["in_sample"]]
    train = np.asarray(train, dtype=bool)
    if train.shape != (len(s),):
        raise ValueError("train mask must have one value per analysis-sample row")
    e = ent.loc[s.index]
    hhid = s["hhid"]
    out = pd.DataFrame(index=s.index)
    specs: list[FeatureSpec] = []

    def add(name: str, values: pd.Series, section: str, kind: str):
        spec = fcfg[section][name]
        out[name] = values
        specs.append(FeatureSpec(name, spec["file"], _spec_variables(spec), kind))

    # enterprise (sect8b)
    add("sector_group", s["sector_group"].astype("string"), "enterprise", "categorical")
    add("premises", _merge_rare(code_of(e["s8q10"]), train, cfg), "enterprise", "categorical")
    add("registered", _yes_no(e["s8q11"]), "enterprise", "binary")
    add("non_household_employees", code_of(e["s8q13a"]) + code_of(e["s8q13b"]), "enterprise", "count")
    add("years_in_operation", code_of(e["s8q4b"]).astype(float), "enterprise", "numeric")

    # location (cover file, carried on the frame)
    add("zone", s["zone"].astype("string"), "location", "categorical")
    add("state", s["state"].astype("string"), "location", "categorical")
    add("urban", (s["urban_rural"] == "urban").astype(float), "location", "binary")

    # household variables, merged by hhid
    def by_hh(series: pd.Series) -> pd.Series:
        return pd.Series(hhid.map(series).to_numpy(), index=s.index)

    b5 = household["sect5b_plantingw5"]
    add("any_member_mobile_phone", by_hh(_any_member_yes(b5, "s5bq8")), "household", "binary")
    add("any_member_internet", by_hh(_any_member_yes(b5, "s5bq14")), "household", "binary")

    h9 = household["sect9_harvestw5"].drop_duplicates("hhid").set_index("hhid")
    add("household_internet_connection", by_hh(_yes_no(h9["s9q48"])), "household", "binary")

    a5 = household["sect5a1_plantingw5"]
    add("any_member_account", by_hh(_any_member_yes(a5, "s5aq2")), "household", "binary")
    add("any_member_formal_savings", by_hh(_any_member_yes(a5, "s5aq6")), "household", "binary")

    for name, var in [("wall_material", "s9q9"), ("roof_material", "s9q10"), ("floor_material", "s9q11")]:
        add(name, _merge_rare(by_hh(code_of(h9[var])), train, cfg), "household", "categorical")

    d10 = household["sect10_plantingw5"]
    item = code_of(d10["item_cd"])
    owned = _yes_no(d10["s10q1a"])
    wide = pd.DataFrame({"hhid": d10["hhid"], "item": item, "owned": owned})
    wide = wide[wide["item"] != EXCLUDED_ITEM].pivot_table(index="hhid", columns="item", values="owned", aggfunc="max")
    spec = fcfg["household"]["durable_assets"]
    for code in sorted(wide.columns):
        col = f"asset_{int(code)}"
        out[col] = by_hh(wide[code])
        specs.append(FeatureSpec(col, spec["file"], _spec_variables(spec), "binary"))
    out["asset_types_owned"] = by_hh(wide.sum(axis=1, min_count=1))
    specs.append(FeatureSpec("asset_types_owned", spec["file"], _spec_variables(spec), "count"))

    r1 = household["sect1_harvestw5"]
    member = (code_of(r1["s1q4"]) == YES) | (pd.to_numeric(r1["NEWMEMBER"], errors="coerce") == 1)
    add("household_size", by_hh(member.groupby(r1["hhid"]).sum().astype(float)), "household", "count")

    set_a = list(out.columns)
    add("local_authority_payments", _yes_no(e["s8q11b"]), "with_local_payments", "binary")
    set_b = set_a + ["local_authority_payments"]

    for target, col in TARGETS.items():
        out[target] = s[col]
    for col in DESIGN_COLUMNS:
        out[col] = s[col]

    table = FeatureTable(out, specs, set_a, set_b)
    check_excluded(table, cfg)
    return table


def check_excluded(table: FeatureTable, cfg: dict) -> None:
    """Raise if any never-feature variable, file or derived name is used in feature set A or B."""
    never = cfg["features"]["never"]
    bad_vars, bad_files = set(never["variables"]), set(never["files"])
    patterns = set(never["name_patterns"])
    used = set(table.set_a) | set(table.set_b)
    for spec in table.specs:
        if spec.name not in used:
            continue
        if bad_vars & set(spec.variables) or spec.file in bad_files:
            raise ValueError(f"feature {spec.name} uses an excluded source: {spec.file} {spec.variables}")
    for name in used:
        tokens = set(name.lower().split("_"))
        if tokens & patterns or name in TARGETS or name in DESIGN_COLUMNS:
            raise ValueError(f"feature {name} is excluded or derived from an excluded variable")
    names = {s.name for s in table.specs}
    if used - names:
        raise ValueError(f"features without a source spec: {sorted(used - names)}")


def summary(table: FeatureTable, train: np.ndarray) -> pd.DataFrame:
    """Aggregate description of each feature; missing shares and categories on training rows only."""
    tr = table.data[train]
    rows = []
    for spec in table.specs:
        col = tr[spec.name]
        rows.append({
            "feature": spec.name,
            "feature_set": "B only" if spec.name not in table.set_a else "A and B",
            "source_file": spec.file,
            "source_variables": " + ".join(spec.variables),
            "type": spec.kind,
            "categories_in_training_set": int(col.dropna().nunique()) if spec.kind == "categorical" else np.nan,
            "share_missing_training_set": float(col.isna().mean()),
        })
    return pd.DataFrame(rows)
