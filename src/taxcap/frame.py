"""Enterprise analysis frame (docs/analysis_plan.md sections 1-6), built in memory.

The frame holds one row per enterprise in the population and is never written to disk. Rows in
the analysis sample (in_sample) have months operated, annual income and threshold flags; the other
rows are kept with the reason for exclusion so that exclusions can be counted.

FrameOptions selects the sensitivity variants of plan sections 2, 3.4 and 7.5; the defaults are the
primary settings. to_owner_level applies the owner-level unit of plan section 5.2.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from taxcap.audit import (COVER_FILE, ENTERPRISE_FILE, OWNERS, PROFIT, STATUS, code_of, months_in_window,
                          months_scaled_excluding, psu_key, sector_group)
from taxcap.load import load_config, read_table
from taxcap.survey import Design, make_design, weighted_quantile

PRICE_BASES = ("nominal", "cpi")
EXCLUDED_NO_FLAGS = "s8q9 flags or interview date missing"
EXCLUDED_ZERO_MONTHS = "no month operated in window"
EXCLUDED_NO_WEIGHT = "weight missing or non-positive"
MONTHS_RULES = ("primary", "profit_x12", "fixed_window", "unprinted_missing")
STRATA_RULES = ("modal", "zone_sector")


@dataclass(frozen=True)
class FrameOptions:
    months_rule: str = "primary"          # primary | profit_x12 | fixed_window | unprinted_missing
    status_codes: tuple[int, ...] | None = None   # None: population.primary_status_codes
    strata_rule: str = "modal"            # modal | zone_sector (plan section 7.5)

    def __post_init__(self):
        if self.months_rule not in MONTHS_RULES:
            raise ValueError(f"unknown months_rule: {self.months_rule}")
        if self.strata_rule not in STRATA_RULES:
            raise ValueError(f"unknown strata_rule: {self.strata_rule}")


@dataclass
class AnalysisFrame:
    data: pd.DataFrame        # one row per unit; identifiers stay in memory and never reach an output table
    psu_strata: pd.Series     # stratum of every design PSU
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


def _weighted_households(cover: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    w = pd.to_numeric(cover[cfg["survey_design"]["weight"]], errors="coerce")
    return cover[w.notna() & (w > 0)]


def design_psu_strata(ent_psu: pd.Series, ent_strata: pd.Series, cover: pd.DataFrame, cfg: dict) -> pd.Series:
    """Stratum of every design PSU (PSUs of cover-file households with a positive weight).

    PSUs with weighted operating enterprises take the stratum held by most of those enterprises (plan section 1.3);
    other PSUs take the stratum held by most of their households. Ties go to the lowest code.
    """
    hh = _weighted_households(cover, cfg)
    by_household = modal_stratum(psu_key(hh, cfg), hh[cfg["survey_design"]["strata"]])
    by_enterprise = modal_stratum(ent_psu, ent_strata)
    out = by_household.copy()
    out.loc[by_enterprise.index] = by_enterprise
    return out.sort_index()


def zone_sector_psu_strata(cover: pd.DataFrame, cfg: dict) -> pd.Series:
    """Zone x urban/rural stratum of every design PSU (plan section 7.5); modal over households."""
    hh = _weighted_households(cover, cfg)
    cells = [hh[c].astype("string") for c in cfg["survey_design"]["strata_sensitivity"]]
    key = cells[0].str.cat(cells[1:], sep=" x ")
    return modal_stratum(psu_key(hh, cfg), key).sort_index()


def _months(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict, rule: str) -> pd.Series:
    a = cfg["annualisation"]
    if rule == "fixed_window":
        return months_in_window(ent, cover, cfg, "fixed_calendar_window")
    if rule == "unprinted_missing":
        return months_scaled_excluding(ent, cover, cfg, a["unprinted_flags_sensitivity"])
    return months_in_window(ent, cover, cfg)


def build_frame(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict, options: FrameOptions = FrameOptions()) -> AnalysisFrame:
    d = cfg["survey_design"]
    threshold = float(cfg["tax_rules"]["pit_exemption_naira"])
    cpi_ratio = float(cfg["price_adjustment"]["cpi_ratio"])
    if cfg["price_adjustment"]["method"] != "cpi_ratio":
        raise ValueError("price_adjustment.method must be cpi_ratio for the CPI-adjusted estimates")
    primary_codes = tuple(cfg["population"]["primary_status_codes"])
    codes = tuple(options.status_codes) if options.status_codes is not None else primary_codes

    n_total = len(ent)
    status = code_of(ent[STATUS])
    pop_mask = status.isin(codes)
    operating = status.isin(primary_codes)
    months_all = _months(ent, cover, cfg, options.months_rule)

    cov = cover[["hhid", d["weight"], d["strata"]]].rename(
        columns={d["weight"]: "weight", d["strata"]: "stratum_household"})
    ent_all = ent.merge(cov, on="hhid", how="left", validate="many_to_one").set_index(ent.index)
    w_all = pd.to_numeric(ent_all["weight"], errors="coerce")

    # the design is the same in every scenario: strata come from weighted operating enterprises (plan section 1.3)
    op_w = operating & (w_all > 0)
    if options.strata_rule == "zone_sector":
        psu_strata = zone_sector_psu_strata(cover, cfg)
    else:
        psu_strata = design_psu_strata(psu_key(ent_all[op_w], cfg), ent_all.loc[op_w, "stratum_household"], cover, cfg)

    ent = ent_all.loc[pop_mask]
    f = pd.DataFrame(index=ent.index)
    f["hhid"] = ent["hhid"]
    for i, c in enumerate(OWNERS, start=1):
        f[f"owner_{i}"] = pd.to_numeric(ent[c], errors="coerce")
    f["psu"] = psu_key(ent, cfg)
    f["zone"] = ent["zone"]
    f["state"] = ent["state"]
    f["urban_rural"] = np.where(code_of(ent["sector"]) == 1, "urban", "rural")
    f["sector_group"] = sector_group(ent, cfg)
    f["weight"] = w_all.loc[pop_mask]
    f["months"] = months_all.loc[pop_mask]
    f["profit"] = pd.to_numeric(ent[PROFIT], errors="coerce").clip(lower=0)  # negative profit -> zero income

    # exclusions follow the window rule of the scenario; profit x 12 keeps the primary exclusions
    rule_months = months_in_window(ent, cover, cfg) if options.months_rule == "profit_x12" else f["months"]
    reason = pd.Series(pd.NA, index=f.index, dtype="string")
    reason = reason.mask(reason.isna() & rule_months.isna(), EXCLUDED_NO_FLAGS)
    reason = reason.mask(reason.isna() & (rule_months == 0), EXCLUDED_ZERO_MONTHS)
    reason = reason.mask(reason.isna() & ~(f["weight"] > 0), EXCLUDED_NO_WEIGHT)
    f["exclusion"] = reason
    f["in_sample"] = reason.isna()
    if options.months_rule == "profit_x12":
        f["months"] = float(cfg["annualisation"]["window_months"])

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
    f["stratum"] = f["psu"].map(psu_strata)

    in_label = ("currently operating (s8q3 = 1)" if codes == (1,)
                else f"in population (s8q3 in {', '.join(map(str, codes))})")
    out_label = ("not currently operating (s8q3 != 1)" if codes == (1,) else "outside population")
    exclusions = pd.DataFrame([
        ("enterprises in sect8b", n_total),
        (out_label, int((~pop_mask).sum())),
        (in_label, len(f)),
        (f"excluded: {EXCLUDED_NO_FLAGS}", int((reason == EXCLUDED_NO_FLAGS).sum())),
        (f"excluded: {EXCLUDED_ZERO_MONTHS}", int((reason == EXCLUDED_ZERO_MONTHS).sum())),
        (f"excluded: {EXCLUDED_NO_WEIGHT}", int((reason == EXCLUDED_NO_WEIGHT).sum())),
        ("analysis sample", int(s.sum())),
    ], columns=["step", "count"])

    reassigned = int((ent_all.loc[op_w, "stratum_household"].groupby(psu_key(ent_all[op_w], cfg)).nunique() > 1).sum())
    design_summary = pd.DataFrame([
        ("design PSUs (cover-file households with positive weight)", int(psu_strata.size)),
        ("strata", int(psu_strata.nunique())),
        ("degrees of freedom (PSUs minus strata)", int(psu_strata.size - psu_strata.nunique())),
        ("PSUs with operating enterprises", int(psu_key(ent_all[operating], cfg).nunique())),
        ("PSUs with analysis-sample enterprises", int(f.loc[s, "psu"].nunique())),
        ("PSUs with operating enterprises in more than one stratum (modal rule applied)", reassigned),
        ("winsorisation percentile", pct * 100),
        ("cpi_ratio", cpi_ratio),
        ("threshold (naira)", threshold),
    ], columns=["item", "value"])
    return AnalysisFrame(f, psu_strata, exclusions, design_summary, cap, cfg)


def to_owner_level(fr: AnalysisFrame) -> AnalysisFrame:
    """Owner-level units (plan section 5.2, income_allocation owner_sum).

    Each person's income is the sum over the analysis-sample enterprises they own; an enterprise with two
    listed owners contributes half its income to each. A person makes payments to local authorities if
    any of their enterprises does. Persons carry their household's weight, PSU and stratum.
    """
    threshold = float(fr.cfg["tax_rules"]["pit_exemption_naira"])
    ent = fr.data[fr.data["in_sample"]]
    owner_cols = [c for c in ent.columns if c.startswith("owner_")]
    long = ent.reset_index(names="ent_row").melt(
        id_vars=["ent_row"], value_vars=owner_cols, value_name="indiv").dropna(subset=["indiv"])
    long = long.drop_duplicates(["ent_row", "indiv"])
    long["share"] = 1.0 / long.groupby("ent_row")["indiv"].transform("size")
    long = long.join(ent, on="ent_row")
    for b in PRICE_BASES:
        long[f"income_{b}"] = long[f"income_{b}"] * long["share"]
        long[f"income_winsorised_{b}"] = long[f"income_winsorised_{b}"] * long["share"]

    keys = ["hhid", "indiv"]
    sums = long.groupby(keys)[[f"{p}_{b}" for p in ("income", "income_winsorised") for b in PRICE_BASES]].sum()
    anys = long.groupby(keys)[["pays_local_authorities", "registered"]].max()
    firsts = long.groupby(keys)[["psu", "stratum", "weight", "zone", "state", "urban_rural"]].first()
    p = pd.concat([firsts, sums, anys], axis=1).reset_index()
    for b in PRICE_BASES:
        p[f"above_{b}"] = (p[f"income_{b}"] > threshold).astype(float)
    p["in_sample"] = True

    no_owner = int((~ent.index.isin(long["ent_row"])).sum())
    exclusions = pd.DataFrame([
        ("analysis-sample enterprises", len(ent)),
        ("analysis-sample enterprises with no owner listed", no_owner),
        ("enterprises with two owners", int((long.groupby("ent_row").size() == 2).sum())),
        ("persons (owner-level units)", len(p)),
    ], columns=["step", "count"])
    return AnalysisFrame(p, fr.psu_strata, exclusions, fr.design_summary, float("nan"), fr.cfg)


def load_frame(zip_path=None, config_path=None, options: FrameOptions = FrameOptions()) -> AnalysisFrame:
    cfg = load_config(config_path)
    ent = read_table(ENTERPRISE_FILE, zip_path=zip_path)
    cover = read_table(COVER_FILE, zip_path=zip_path)
    return build_frame(ent, cover, cfg, options)
