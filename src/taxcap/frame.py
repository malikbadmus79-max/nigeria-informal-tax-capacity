"""Enterprise analysis frame (docs/analysis_plan.md sections 1-6), built in memory.

The frame holds one row per currently operating enterprise and is never written to disk. Rows in
the analysis sample (in_sample) have months operated, annual income and threshold flags; the other
rows are kept with the reason for exclusion so that exclusions can be counted.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from taxcap.audit import (COVER_FILE, ENTERPRISE_FILE, PROFIT, code_of, is_operating, months_in_window,
                          psu_key, sector_group)
from taxcap.load import load_config, read_table
from taxcap.survey import Design, make_design, weighted_quantile

PRICE_BASES = ("nominal", "cpi")
EXCLUDED_NO_FLAGS = "s8q9 flags or interview date missing"
EXCLUDED_ZERO_MONTHS = "no month operated in window"
EXCLUDED_NO_WEIGHT = "weight missing or non-positive"


@dataclass
class AnalysisFrame:
    data: pd.DataFrame        # one row per operating enterprise; no identifiers leave this module's callers
    psu_strata: pd.Series     # stratum of every design PSU after the modal-stratum rule
    exclusions: pd.DataFrame  # step, count
    design_summary: pd.DataFrame
    profit_cap: float         # single-enterprise value: print only, never write to disk
    cfg: dict

    def design(self) -> Design:
        return make_design(self.data["weight"], self.data["psu"], self.psu_strata)

    @property
    def sample(self) -> np.ndarray:
        return self.data["in_sample"].to_numpy()


def modal_stratum(psu: pd.Series, strata: pd.Series) -> pd.Series:
    """Most common stratum per PSU; ties go to the lowest stratum code."""
    counts = pd.DataFrame({"psu": psu.to_numpy(), "stratum": strata.to_numpy()}).value_counts().reset_index(name="n")
    counts = counts.sort_values(["psu", "n", "stratum"], ascending=[True, False, True])
    return counts.drop_duplicates("psu").set_index("psu")["stratum"]


def design_psu_strata(ent_psu: pd.Series, ent_strata: pd.Series, cover: pd.DataFrame, cfg: dict) -> pd.Series:
    """Stratum of every design PSU (PSUs of cover-file households with a positive weight).

    PSUs with weighted operating enterprises take the stratum held by most of those enterprises (plan section 1.3);
    other PSUs take the stratum held by most of their households. Ties go to the lowest code.
    """
    d = cfg["survey_design"]
    w = pd.to_numeric(cover[d["weight"]], errors="coerce")
    hh = cover[w.notna() & (w > 0)]
    by_household = modal_stratum(psu_key(hh, cfg), hh[d["strata"]])
    by_enterprise = modal_stratum(ent_psu, ent_strata)
    out = by_household.copy()
    out.loc[by_enterprise.index] = by_enterprise
    return out.sort_index()


def build_frame(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict) -> AnalysisFrame:
    d = cfg["survey_design"]
    threshold = float(cfg["tax_rules"]["pit_exemption_naira"])
    cpi_ratio = float(cfg["price_adjustment"]["cpi_ratio"])
    if cfg["price_adjustment"]["method"] != "cpi_ratio":
        raise ValueError("price_adjustment.method must be cpi_ratio for the CPI-adjusted estimates")

    n_total = len(ent)
    op_mask = is_operating(ent)
    months_all = months_in_window(ent, cover, cfg)
    ent = ent.loc[op_mask].copy()
    months = months_all.loc[op_mask]

    cov = cover[["hhid", d["weight"], d["strata"]]].rename(
        columns={d["weight"]: "weight", d["strata"]: "stratum_household"})
    ent = ent.merge(cov, on="hhid", how="left", validate="many_to_one").set_index(ent.index)

    f = pd.DataFrame(index=ent.index)
    f["psu"] = psu_key(ent, cfg)
    f["zone"] = ent["zone"]
    f["state"] = ent["state"]
    f["urban_rural"] = np.where(code_of(ent["sector"]) == 1, "urban", "rural")
    f["sector_group"] = sector_group(ent, cfg)
    f["weight"] = pd.to_numeric(ent["weight"], errors="coerce")
    f["months"] = months

    profit = pd.to_numeric(ent[PROFIT], errors="coerce").clip(lower=0)  # negative profit -> zero income
    f["profit"] = profit

    reason = pd.Series(pd.NA, index=f.index, dtype="string")
    reason = reason.mask(reason.isna() & f["months"].isna(), EXCLUDED_NO_FLAGS)
    reason = reason.mask(reason.isna() & (f["months"] == 0), EXCLUDED_ZERO_MONTHS)
    reason = reason.mask(reason.isna() & ~(f["weight"] > 0), EXCLUDED_NO_WEIGHT)
    f["exclusion"] = reason
    f["in_sample"] = reason.isna()

    # profit winsorised at the weighted percentile of the analysis sample (plan section 6)
    s = f["in_sample"]
    pct = float(cfg["outliers"]["winsorisation_percentile"]) / 100
    cap = weighted_quantile(f.loc[s, "profit"], f.loc[s, "weight"], pct) if s.any() else np.nan
    f["profit_winsorised"] = f["profit"].clip(upper=cap)

    m = f["months"].where(s)
    for basis, factor in [("nominal", 1.0), ("cpi", cpi_ratio)]:
        f[f"income_{basis}"] = f["profit"] * m * factor
        f[f"income_winsorised_{basis}"] = f["profit_winsorised"] * m * factor
        f[f"above_{basis}"] = (f[f"income_{basis}"] > threshold).astype(float).where(s)

    f["registered"] = (code_of(ent["s8q11"]) == 1).astype(float)
    f["pays_local_authorities"] = (code_of(ent["s8q11b"]) == 1).astype(float)

    f["weight"] = f["weight"].where(f["weight"] > 0, 0.0)  # excluded rows carry no weight into totals
    weighted = f["weight"] > 0
    psu_strata = design_psu_strata(f.loc[weighted, "psu"], ent.loc[weighted, "stratum_household"], cover, cfg)
    f["stratum"] = f["psu"].map(psu_strata)

    exclusions = pd.DataFrame([
        ("enterprises in sect8b", n_total),
        ("not currently operating (s8q3 != 1)", int((~op_mask).sum())),
        ("currently operating (s8q3 = 1)", len(f)),
        (f"excluded: {EXCLUDED_NO_FLAGS}", int((reason == EXCLUDED_NO_FLAGS).sum())),
        (f"excluded: {EXCLUDED_ZERO_MONTHS}", int((reason == EXCLUDED_ZERO_MONTHS).sum())),
        (f"excluded: {EXCLUDED_NO_WEIGHT}", int((reason == EXCLUDED_NO_WEIGHT).sum())),
        ("analysis sample", int(s.sum())),
    ], columns=["step", "count"])

    ent_psus = set(f["psu"])
    reassigned = int((ent["stratum_household"].groupby(f["psu"]).nunique() > 1).sum())
    design_summary = pd.DataFrame([
        ("design PSUs (cover-file households with positive weight)", int(psu_strata.size)),
        ("strata", int(psu_strata.nunique())),
        ("degrees of freedom (PSUs minus strata)", int(psu_strata.size - psu_strata.nunique())),
        ("PSUs with operating enterprises", len(ent_psus)),
        ("PSUs with analysis-sample enterprises", int(f.loc[s, "psu"].nunique())),
        ("PSUs with operating enterprises in more than one stratum (modal rule applied)", reassigned),
        ("winsorisation percentile", pct * 100),
        ("cpi_ratio", cpi_ratio),
        ("threshold (naira)", threshold),
    ], columns=["item", "value"])
    return AnalysisFrame(f, psu_strata, exclusions, design_summary, cap, cfg)


def load_frame(zip_path=None, config_path=None) -> AnalysisFrame:
    cfg = load_config(config_path)
    ent = read_table(ENTERPRISE_FILE, zip_path=zip_path)
    cover = read_table(COVER_FILE, zip_path=zip_path)
    return build_frame(ent, cover, cfg)
