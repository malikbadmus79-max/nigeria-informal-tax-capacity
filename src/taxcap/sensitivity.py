"""Sensitivity runs listed in docs/analysis_plan.md, run as ``python -m taxcap.sensitivity``.

Each scenario rebuilds the analysis frame with one change from the primary settings and reports, for each
price basis, the share above the threshold and the share of units at or below the threshold making
payments to government or non-government local authorities to allow operation. Writes the aggregate table
outputs/tables/est_sensitivity.csv.

Plan sensitivities not run here: untreated profit (section 6) changes means only and is reported in
est_income.csv; the September 2023 reference month (section 4) is pending the September 2026 rate.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from taxcap.audit import check_no_identifiers
from taxcap.estimate import LOCAL_PAYMENTS, row
from taxcap.frame import COVER_FILE, ENTERPRISE_FILE, PRICE_BASES, AnalysisFrame, FrameOptions, build_frame, \
    to_owner_level
from taxcap.load import PROJECT_ROOT, load_config, read_table
from taxcap.survey import proportion

SHARE_ABOVE = "share above threshold"
BELOW_PAYING = f"share at or below threshold making {LOCAL_PAYMENTS}"


@dataclass(frozen=True)
class Scenario:
    name: str
    plan_section: str
    description: str
    build: Callable[[pd.DataFrame, pd.DataFrame, dict], AnalysisFrame]
    bases: tuple[str, ...] = PRICE_BASES
    unit: str = "enterprises"


def _unrevised_cpi(cfg: dict) -> dict:
    out = copy.deepcopy(cfg)
    out["price_adjustment"]["cpi_ratio"] = cfg["price_adjustment"]["sensitivities"]["unrevised_aug_2025"]["cpi_ratio"]
    return out


def scenarios(cfg: dict) -> list[Scenario]:
    closed = tuple(cfg["population"]["sensitivity_status_codes"])
    return [
        Scenario("primary", "-", "primary settings", lambda e, c, g: build_frame(e, c, g)),
        Scenario("profit_x12", "3.4", "annual income = monthly profit x 12",
                 lambda e, c, g: build_frame(e, c, g, FrameOptions(months_rule="profit_x12"))),
        Scenario("fixed_window", "3.4", "fixed window April 2023 to March 2024",
                 lambda e, c, g: build_frame(e, c, g, FrameOptions(months_rule="fixed_window"))),
        Scenario("unprinted_flags_missing", "3.4", "s8q9 flags 15 and 16 missing, months scaled to 12",
                 lambda e, c, g: build_frame(e, c, g, FrameOptions(months_rule="unprinted_missing"))),
        Scenario("include_closed", "2", "adds temporarily and seasonally closed enterprises",
                 lambda e, c, g: build_frame(e, c, g, FrameOptions(status_codes=closed))),
        Scenario("owner_level", "5.2", "owner-level unit, two-owner enterprises split equally",
                 lambda e, c, g: to_owner_level(build_frame(e, c, g)), unit="persons"),
        Scenario("cpi_unrevised_aug_2025", "4", "August 2025 rate as first published (cpi_ratio 1.8317)",
                 lambda e, c, g: build_frame(e, c, _unrevised_cpi(g)), bases=("cpi",)),
        Scenario("strata_zone_urban_rural", "7.5", "strata = zone x urban/rural (variance only)",
                 lambda e, c, g: build_frame(e, c, g, FrameOptions(strata_rule="zone_sector"))),
    ]


def scenario_rows(sc: Scenario, fr: AnalysisFrame) -> list[dict]:
    design = fr.design()
    level = float(fr.cfg["estimation"]["confidence_level"])
    d = fr.data
    rows = []
    for b in sc.bases:
        labels = dict(scenario=sc.name, plan_section=sc.plan_section, description=sc.description,
                      unit=sc.unit, price_basis=b)
        above = proportion(design, d[f"above_{b}"].fillna(0), fr.sample, level)
        rows.append(row(above, fr.cfg, **labels, measure=SHARE_ABOVE))
        below = fr.sample & (d[f"above_{b}"] == 0).to_numpy()
        paying = proportion(design, d["pays_local_authorities"], below, level)
        rows.append(row(paying, fr.cfg, **labels, measure=BELOW_PAYING))
    return rows


def run_scenarios(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = []
    for sc in scenarios(cfg):
        rows += scenario_rows(sc, sc.build(ent, cover, cfg))
    return pd.DataFrame(rows)


def run(zip_path=None, out_dir=None, config_path=None) -> pd.DataFrame:
    cfg = load_config(config_path)
    ent = read_table(ENTERPRISE_FILE, zip_path=zip_path)
    cover = read_table(COVER_FILE, zip_path=zip_path)
    table = run_scenarios(ent, cover, cfg)
    check_no_identifiers({"sensitivity": table})
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_rows", 200,
                           "display.max_colwidth", 60, "display.float_format", lambda x: f"{x:,.4f}"):
        print(table.drop(columns=["description"]).to_string(index=False))
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "outputs" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "est_sensitivity.csv"
    table.to_csv(path, index=False)
    print(f"\nWrote {path}")
    return table


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", dest="zip_path", default=None, help="survey zip (default: config data.zip_path)")
    ap.add_argument("--out", dest="out_dir", default=None, help="output directory (default: outputs/tables)")
    args = ap.parse_args(argv)
    run(zip_path=args.zip_path, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
