"""First estimates (docs/analysis_plan.md sections 2-9), run as ``python -m taxcap.estimate``.

Builds the analysis frame in memory and writes aggregate tables only, to outputs/tables/est_*.csv.
Every domain estimate carries the reliability flag of plan section 7.3. Single-enterprise values
(the winsorisation cap) are printed to the console and never written.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from taxcap.audit import check_no_identifiers
from taxcap.frame import PRICE_BASES, AnalysisFrame, load_frame
from taxcap.load import PROJECT_ROOT
from taxcap.survey import Design, Estimate, mean, proportion, quantile

LOCAL_PAYMENTS = "payments to government or non-government local authorities to allow operation (s8q11b)"
REGISTERED = "officially registered with the government (s8q11)"
PAYS_NOT_REGISTERED = "pays (s8q11b) and not registered (s8q11)"
DOMAIN_VARIABLES = {"zone": "zone", "urban_rural": "urban_rural", "sector_group": "sector_group", "state": "state"}
# The sample is designed to be representative nationally and by zone (T05), not by state: state estimates
# are labelled indicative whatever their reliability flag (plan section 7.3).
INDICATIVE_DOMAINS = {"state"}
ESTIMATE_COLUMNS = ["estimate", "se", "ci_low", "ci_high", "n", "psus", "df", "relative_se", "unreliable"]


def unreliable(e: Estimate, cfg: dict) -> bool:
    r = cfg["estimation"]["reliability"]
    return bool(e.n < r["min_enterprises"] or e.psus < r["min_psus"] or e.relative_se > r["max_relative_se"])


def row(e: Estimate, cfg: dict, **labels) -> dict:
    return {**labels, **e.as_dict(), "unreliable": unreliable(e, cfg)}


def headline(fr: AnalysisFrame, design: Design, level: float) -> pd.DataFrame:
    rows = [row(proportion(design, fr.data[f"above_{b}"].fillna(0), fr.sample, level), fr.cfg,
                measure="share of operating enterprises above threshold", price_basis=b) for b in PRICE_BASES]
    return pd.DataFrame(rows)


def domains(fr: AnalysisFrame, design: Design, level: float) -> pd.DataFrame:
    rows = []
    for kind, col in DOMAIN_VARIABLES.items():
        for value in sorted(fr.data.loc[fr.sample, col].dropna().unique()):
            dom = fr.sample & (fr.data[col] == value).to_numpy()
            for b in PRICE_BASES:
                e = proportion(design, fr.data[f"above_{b}"].fillna(0), dom, level)
                rows.append(row(e, fr.cfg, domain_type=kind, domain=value, price_basis=b,
                                indicative=kind in INDICATIVE_DOMAINS))
    return pd.DataFrame(rows)


CONSISTENCY_DOMAINS = ["zone", "urban_rural", "sector_group"]
CONSISTENCY_TOLERANCE = 1e-9


def domain_consistency(fr: AnalysisFrame, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Weighted average of domain shares, with weights = estimated domain population (sum of weights in
    the analysis sample), against the headline share. Domains of one type partition the sample, so the
    two must agree to rounding error."""
    d, h = tables["domains"], tables["headline"].set_index("price_basis")["estimate"]
    s = fr.data[fr.sample]
    rows = []
    for kind in CONSISTENCY_DOMAINS:
        pop = s.groupby(DOMAIN_VARIABLES[kind])["weight"].sum()
        for b in PRICE_BASES:
            share = d[(d["domain_type"] == kind) & (d["price_basis"] == b)].set_index("domain")["estimate"]
            avg = float((share * pop.reindex(share.index)).sum() / pop.reindex(share.index).sum())
            diff = abs(avg - float(h[b]))
            rows.append({"domain_type": kind, "price_basis": b, "headline": float(h[b]), "weighted_average": avg,
                         "abs_difference": diff, "consistent": diff <= CONSISTENCY_TOLERANCE})
    return pd.DataFrame(rows)


def same_basis_checks(fr: AnalysisFrame, domains_table: pd.DataFrame) -> list[str]:
    """For domains whose nominal and CPI-adjusted shares are identical, count enterprises whose nominal
    income lies above threshold / cpi_ratio and at or below the threshold (the only incomes that switch
    class between price bases). Counts only; printed to the console."""
    t = float(fr.cfg["tax_rules"]["pit_exemption_naira"])
    lower = t / float(fr.cfg["price_adjustment"]["cpi_ratio"])
    wide = domains_table.pivot_table(index=["domain_type", "domain"], columns="price_basis", values="estimate")
    same = wide[wide["nominal"] == wide["cpi"]]
    y = fr.data["income_nominal"]
    switch = fr.data["in_sample"] & (y > lower) & (y <= t)
    lines = []
    for kind, value in same.index:
        k = int((switch & (fr.data[DOMAIN_VARIABLES[kind]] == value)).sum())
        note = ("none, so identical estimates are expected" if k == 0
                else "estimates should differ: check the CPI adjustment")
        lines.append(f"{kind} {value}: nominal and CPI-adjusted shares identical; enterprises with nominal annual "
                     f"income above {lower:,.0f} and at or below {t:,.0f} naira: {k} ({note})")
    return lines


def income(fr: AnalysisFrame, design: Design, level: float) -> pd.DataFrame:
    rows = []
    for b in PRICE_BASES:
        y = fr.data[f"income_{b}"].fillna(0)
        yw = fr.data[f"income_winsorised_{b}"].fillna(0)
        rows.append(row(quantile(design, y, 0.5, fr.sample, level), fr.cfg,
                        statistic="median annual income", price_basis=b))
        rows.append(row(mean(design, yw, fr.sample, level), fr.cfg,
                        statistic="mean annual income, winsorised profit", price_basis=b))
        rows.append(row(mean(design, y, fr.sample, level), fr.cfg,
                        statistic="mean annual income, untreated profit (sensitivity)", price_basis=b))
    return pd.DataFrame(rows)


def threshold_band(fr: AnalysisFrame, design: Design, level: float) -> pd.DataFrame:
    t = float(fr.cfg["tax_rules"]["pit_exemption_naira"])
    band = float(fr.cfg["outliers"]["threshold_band"])
    lo, hi = t * (1 - band), t * (1 + band)
    rows = []
    for b in PRICE_BASES:
        y = fr.data[f"income_{b}"]
        inside = (y >= lo) & (y <= hi)
        e = proportion(design, inside.astype(float), fr.sample, level)
        rows.append(row(e, fr.cfg, measure=f"share with annual income from {lo:,.0f} to {hi:,.0f} naira",
                        price_basis=b, unweighted_count=int((inside & fr.data["in_sample"]).sum())))
    return pd.DataFrame(rows)


def registration_payments(fr: AnalysisFrame, design: Design, level: float) -> pd.DataFrame:
    d = fr.data
    pays_not_reg = ((d["pays_local_authorities"] == 1) & (d["registered"] == 0)).astype(float)
    rows = []
    for var, y in [(REGISTERED, d["registered"]), (LOCAL_PAYMENTS, d["pays_local_authorities"])]:
        rows.append(row(proportion(design, y, fr.sample, level), fr.cfg,
                        measure=f"share {var}", group="all enterprises in the analysis sample", price_basis="either"))
    for b in PRICE_BASES:
        above = (d[f"above_{b}"] == 1).to_numpy()
        below = (d[f"above_{b}"] == 0).to_numpy()
        for var, y in [(REGISTERED, d["registered"]), (LOCAL_PAYMENTS, d["pays_local_authorities"])]:
            for group, g in [("above threshold", above), ("at or below threshold", below)]:
                rows.append(row(proportion(design, y, fr.sample & g, level), fr.cfg,
                                measure=f"share {var}", group=group, price_basis=b))
        rows.append(row(proportion(design, pays_not_reg, fr.sample & below, level), fr.cfg,
                        measure=f"share {PAYS_NOT_REGISTERED}", group="at or below threshold", price_basis=b))
    return pd.DataFrame(rows)


def build_tables(fr: AnalysisFrame) -> dict[str, pd.DataFrame]:
    design = fr.design()
    level = float(fr.cfg["estimation"]["confidence_level"])
    return {
        "headline": headline(fr, design, level),
        "domains": domains(fr, design, level),
        "income": income(fr, design, level),
        "threshold_band": threshold_band(fr, design, level),
        "registration_payments": registration_payments(fr, design, level),
        "exclusions": fr.exclusions,
        "design": fr.design_summary,
    }


def format_tables(tables: dict[str, pd.DataFrame], fr: AnalysisFrame) -> str:
    lines = same_basis_checks(fr, tables["domains"]) + [f"Monthly profit cap at the weighted {fr.cfg['outliers']['winsorisation_percentile']}th percentile "
             f"(console only, not saved): {fr.profit_cap:,.0f} naira"]
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_rows", 500,
                           "display.max_colwidth", 80, "display.float_format", lambda x: f"{x:,.4f}"):
        for name, t in tables.items():
            lines += ["", f"est_{name}", "-" * (len(name) + 4), t.to_string(index=False)]
    return "\n".join(lines)


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
    check_no_identifiers(tables)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, t in tables.items():
        p = out_dir / f"est_{name}.csv"
        t.to_csv(p, index=False)
        paths.append(p)
    return paths


def run(zip_path=None, out_dir=None, config_path=None) -> dict[str, pd.DataFrame]:
    fr = load_frame(zip_path, config_path)
    tables = build_tables(fr)
    print(format_tables(tables, fr))
    with pd.option_context("display.width", 200, "display.float_format", lambda x: f"{x:.12g}"):
        print("\nConsistency check: population-weighted average of domain shares against the headline share "
              f"(tolerance {CONSISTENCY_TOLERANCE:g}; console only)")
        print(domain_consistency(fr, tables).to_string(index=False))
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "outputs" / "tables"
    paths = write_tables(tables, out_dir)
    print(f"\nWrote {len(paths)} tables to {out_dir}")
    return tables


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", dest="zip_path", default=None, help="survey zip (default: config data.zip_path)")
    ap.add_argument("--out", dest="out_dir", default=None, help="output directory (default: outputs/tables)")
    args = ap.parse_args(argv)
    run(zip_path=args.zip_path, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
