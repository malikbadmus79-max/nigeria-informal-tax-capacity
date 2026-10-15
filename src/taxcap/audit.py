"""Data audit of the non-farm enterprise module (sect8b, sect8c) against the cover file (secta).

Run as ``python -m taxcap.audit``. The report is printed to the console and written as
aggregate tables to outputs/tables/audit_*.csv. No household, enterprise or person
identifiers are written, and tables of single-enterprise values (CONSOLE_ONLY) are printed
only. All statistics are unweighted counts, except where a table
says otherwise; the audit describes the data as recorded, before any cleaning decision.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from taxcap.load import PROJECT_ROOT, load_config, read_table

ENTERPRISE_FILE = "sect8b_harvestw5"
WORKER_FILE = "sect8c_harvestw5"
COVER_FILE = "secta_harvestw5"

ENT_KEY = ["hhid", "ent_id"]
ID_COLUMNS = {"hhid", "ent_id", "indiv", "ea", "cluster", "lga", "psu"}
# Tables printed to the console but never written to disk: they hold single-enterprise values.
CONSOLE_ONLY = {"top_values", "percentiles_upper"}

STATUS, SALES, PROFIT = "s8q3", "s8q29", "s8q30"
OWNERS = ["s8q6_1", "s8q6_2"]
LABEL_VARS = ["s8q3", "s8q10", "s8q11", "s8q11b", "s8q2b"]
OPERATING_CODE = 1  # s8q3 questionnaire code: 1. CURRENTLY OPERATING
PERCENTILES = [1, 5, 25, 50, 75, 95, 99]
UPPER_PERCENTILES = [99.9]  # with the maximum, console only: above p99 a value describes very few enterprises
TOP_N_VALUES = 10
TOP_N_LABELS = 15


def code_of(s: pd.Series) -> pd.Series:
    """Leading numeric code of a labelled value such as '1. CURRENTLY OPERATING'."""
    return pd.to_numeric(s.astype("string").str.extract(r"^\s*(\d+)", expand=False), errors="coerce")


def is_operating(ent: pd.DataFrame) -> pd.Series:
    return code_of(ent[STATUS]) == OPERATING_CODE


def month_flag_index(ent: pd.DataFrame) -> dict[int, str]:
    """s8q9 flag columns keyed by their month index (s8q9__k -> k)."""
    flags = [c for c in ent.columns if c.startswith("s8q9__")]
    return {int(c.split("__")[1]): c for c in flags}


def interview_month_index(cover: pd.DataFrame, cfg: dict) -> pd.Series:
    """Index of each household's interview month on the s8q9 flag scale, keyed by hhid.

    month_flag_origin is the calendar month of flag 1 (questionnaire code 01).
    """
    a = cfg["annualisation"]
    origin = pd.Period(str(a["month_flag_origin"]), freq="M")
    date = pd.to_datetime(cover[a["interview_date_variable"]], format="%Y-%m-%dT%H:%M:%S", errors="coerce")
    months = date.dt.to_period("M")
    idx = (months.dt.year - origin.year) * 12 + (months.dt.month - origin.month) + 1
    # NaT year and month are not NaN in every pandas version, so mask missing dates explicitly
    idx = idx.astype("float").where(date.notna())
    return pd.Series(idx.to_numpy(), index=cover["hhid"].to_numpy())


def window_bounds(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict, rule: str | None = None) -> pd.DataFrame:
    """First and last s8q9 month index of each enterprise's annualisation window."""
    a = cfg["annualisation"]
    rule = rule or a["rule"]
    if rule == "12_months_ending_interview_month":
        # the window ends at the interview month or at the last month with a flag column, whichever is earlier
        last = ent["hhid"].map(interview_month_index(cover, cfg)).astype("float").clip(upper=a["last_month_flag"])
        first = last - a["window_months"] + 1
    elif rule == "fixed_calendar_window":
        fw = a["fixed_window_sensitivity"]
        first = pd.Series(float(fw["first_month_flag"]), index=ent.index)
        last = pd.Series(float(fw["last_month_flag"]), index=ent.index)
    else:
        raise ValueError(f"unknown annualisation rule: {rule}")
    return pd.DataFrame({"first": first, "last": last}, index=ent.index)


def all_month_flags(ent: pd.DataFrame) -> list[str]:
    flags = [c for c in ent.columns if c.startswith("s8q9__")]
    return sorted(flags, key=lambda c: int(c.split("__")[1]))


# (a) enterprise counts -------------------------------------------------------------------

def enterprise_counts(ent: pd.DataFrame) -> pd.DataFrame:
    op = is_operating(ent)
    rows = [
        ("enterprises", "total", len(ent)),
        ("enterprises", "currently operating (s8q3 = 1)", int(op.sum())),
        ("enterprises", "not operating", int((~op & ent[STATUS].notna()).sum())),
        ("enterprises", "s8q3 missing", int(ent[STATUS].isna().sum())),
    ]
    for var, name in [(SALES, "sales"), (PROFIT, "profit")]:
        v = pd.to_numeric(ent[var], errors="coerce")
        for pop, mask in [("all", pd.Series(True, index=ent.index)), ("operating", op)]:
            rows += [
                (f"{var} ({name})", f"missing, {pop}", int(v[mask].isna().sum())),
                (f"{var} ({name})", f"zero, {pop}", int((v[mask] == 0).sum())),
            ]
    s = pd.to_numeric(ent[SALES], errors="coerce")
    p = pd.to_numeric(ent[PROFIT], errors="coerce")
    rows.append(("s8q29 and s8q30", "both zero, all", int(((s == 0) & (p == 0)).sum())))
    rows.append(("s8q29 and s8q30", "both zero, operating", int(((s == 0) & (p == 0) & op).sum())))
    return pd.DataFrame(rows, columns=["item", "measure", "count"])


# (b) months operated ---------------------------------------------------------------------

def months_in_window(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict, rule: str | None = None) -> pd.Series:
    """Months flagged inside each enterprise's window.

    NaN when every s8q9 flag is missing or, under the interview-month rule, the interview date is missing.
    """
    cols = month_flag_index(ent)
    b = window_bounds(ent, cover, cfg, rule)
    k = np.array(sorted(cols))
    flags = ent[[cols[i] for i in k]]
    inside = (k[None, :] >= b["first"].to_numpy()[:, None]) & (k[None, :] <= b["last"].to_numpy()[:, None])
    n = pd.Series((flags.fillna(0).to_numpy() * inside).sum(axis=1), index=ent.index)
    return n.where(flags.notna().any(axis=1) & b["last"].notna())


def months_scaled_excluding(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict, excluded_flags,
                            rule: str | None = None) -> pd.Series:
    """Months operated with some flags treated as missing (plan section 3.4).

    Flags are counted over the window months whose flag is not excluded, then scaled to the window length
    (window_months x flagged / usable window months). NaN as in months_in_window, or when no window month
    is usable.
    """
    cols = month_flag_index(ent)
    excluded = {int(x) for x in excluded_flags}
    b = window_bounds(ent, cover, cfg, rule)
    k = np.array([i for i in sorted(cols) if i not in excluded])
    flags = ent[[cols[i] for i in k]]
    inside = (k[None, :] >= b["first"].to_numpy()[:, None]) & (k[None, :] <= b["last"].to_numpy()[:, None])
    flagged = (flags.fillna(0).to_numpy() * inside).sum(axis=1)
    usable = inside.sum(axis=1)
    scaled = np.where(usable > 0, flagged * cfg["annualisation"]["window_months"] / np.maximum(usable, 1), np.nan)
    all_flags = ent[[cols[i] for i in sorted(cols)]]
    return pd.Series(scaled, index=ent.index).where(all_flags.notna().any(axis=1) & b["last"].notna())


def _distribution(n: pd.Series, status: np.ndarray) -> pd.DataFrame:
    table = pd.crosstab(n.fillna(-1).astype(int), status)
    table.index = ["flags or interview date missing" if i == -1 else str(i) for i in table.index]
    return table


def months_distribution(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    status = np.where(is_operating(ent), "operating", "not operating")
    table = _distribution(months_in_window(ent, cover, cfg), status)
    table["total"] = table.sum(axis=1)
    fixed = _distribution(months_in_window(ent, cover, cfg, "fixed_calendar_window"), status)
    table = table.join(fixed[["operating"]].rename(columns={"operating": "operating, fixed window (sensitivity)"}),
                       how="outer").fillna(0).astype(int)
    order = sorted(table.index, key=lambda i: (not i.isdigit(), int(i) if i.isdigit() else 0))
    table = table.loc[order]
    table.index.name = "months_in_window"
    table.columns.name = None
    return table.reset_index()


def month_flag_share_by_interview(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Share of operating enterprises flagging each s8q9 month, by calendar month of interview.

    Also gives the window each interview month implies under the configured rule and how many of
    its months have a flag column in the data.
    """
    cols = month_flag_index(ent)
    flags = [cols[k] for k in sorted(cols)]
    op = is_operating(ent)
    b = window_bounds(ent, cover, cfg)[op]
    m = ent.loc[op, ENT_KEY + flags].merge(
        cover[["hhid", cfg["annualisation"]["interview_date_variable"]]], on="hhid", how="left"
    )
    m.index = b.index
    date = pd.to_datetime(m[cfg["annualisation"]["interview_date_variable"]], format="%Y-%m-%dT%H:%M:%S",
                          errors="coerce")
    m["interview_month"] = date.dt.strftime("%Y-%m").fillna("missing")
    g = m.groupby("interview_month")
    share = g[flags].mean().round(3)
    first, last = b.groupby(m["interview_month"])["first"].first(), b.groupby(m["interview_month"])["last"].first()
    share.insert(0, "n_operating", g.size())
    share.insert(1, "window_first_flag", first)
    share.insert(2, "window_last_flag", last)
    share.insert(3, "window_months_with_flag_column",
                 [sum(int(f) <= k <= int(l) for k in cols) if pd.notna(f) else 0 for f, l in zip(first, last)])
    return share.reset_index()


# (c) sales and profit --------------------------------------------------------------------

def value_percentiles(ent: pd.DataFrame, percentiles: list[float] = PERCENTILES,
                      with_max: bool = False) -> pd.DataFrame:
    op = is_operating(ent)
    rows = []
    for var in [SALES, PROFIT]:
        v = pd.to_numeric(ent[var], errors="coerce")
        for pop, mask in [("all", pd.Series(True, index=ent.index)), ("operating", op)]:
            x = v[mask].dropna().to_numpy(dtype=float)
            row = {"variable": var, "population": pop, "n": len(x)}
            pct = np.percentile(x, percentiles) if len(x) else [np.nan] * len(percentiles)
            row.update({f"p{q:g}": val for q, val in zip(percentiles, pct)})
            if with_max:
                row["max"] = x.max() if len(x) else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def profit_checks(ent: pd.DataFrame) -> pd.DataFrame:
    s = pd.to_numeric(ent[SALES], errors="coerce")
    p = pd.to_numeric(ent[PROFIT], errors="coerce")
    op = is_operating(ent)
    rows = []
    for pop, mask in [("all", pd.Series(True, index=ent.index)), ("operating", op)]:
        rows += [
            ("profit < 0", pop, int((p[mask] < 0).sum())),
            ("profit > sales", pop, int((p[mask] > s[mask]).sum())),
            ("profit > 0 and sales = 0", pop, int(((p > 0) & (s == 0))[mask].sum())),
        ]
    return pd.DataFrame(rows, columns=["check", "population", "count"])


def top_values(ent: pd.DataFrame, n: int = TOP_N_VALUES) -> pd.DataFrame:
    """The n largest values of sales and profit, each sorted independently. Values only."""
    out = {"rank": range(1, n + 1)}
    for var in [SALES, PROFIT]:
        v = pd.to_numeric(ent[var], errors="coerce").dropna().sort_values(ascending=False)
        out[var] = list(v.head(n)) + [np.nan] * max(0, n - len(v))
    return pd.DataFrame(out)


# (d) ownership ---------------------------------------------------------------------------

def ownership(ent: pd.DataFrame) -> pd.DataFrame:
    owners = ent[OWNERS].notna().sum(axis=1)
    op = is_operating(ent)
    rows = [("owners listed (s8q6_1, s8q6_2)", f"{k} owner(s)", int((owners == k).sum()), int((op & (owners == k)).sum()))
            for k in [0, 1, 2]]
    rows.append(("owners listed (s8q6_1, s8q6_2)", "same person in both slots",
                 int((ent[OWNERS[0]] == ent[OWNERS[1]]).sum()),
                 int((op & (ent[OWNERS[0]] == ent[OWNERS[1]])).sum())))

    per_hh_all = ent.groupby("hhid").size()
    per_hh_op = ent[op].groupby("hhid").size()
    for k in sorted(set(per_hh_all) | set(per_hh_op)):
        rows.append(("households by enterprises operated", f"{k} enterprise(s)",
                     int((per_hh_all == k).sum()), int((per_hh_op == k).sum())))
    rows.append(("households by enterprises operated", "more than one",
                 int((per_hh_all > 1).sum()), int((per_hh_op > 1).sum())))

    long = ent.assign(_op=op).melt(id_vars=ENT_KEY + ["_op"], value_vars=OWNERS, value_name="owner").dropna(subset=["owner"])
    long = long.drop_duplicates(ENT_KEY + ["owner"])
    per_owner_all = long.groupby(["hhid", "owner"]).size()
    per_owner_op = long[long["_op"]].groupby(["hhid", "owner"]).size()
    rows.append(("persons listed as owner", "total", len(per_owner_all), len(per_owner_op)))
    rows.append(("persons listed as owner", "owning more than one enterprise",
                 int((per_owner_all > 1).sum()), int((per_owner_op > 1).sum())))
    multi = ent.assign(_n=owners).groupby("hhid")["_n"].transform("size") > 1
    rows.append(("enterprises", "in a household operating more than one enterprise",
                 int(multi.sum()), int((multi & op).sum())))
    return pd.DataFrame(rows, columns=["item", "category", "all", "operating"])


# (e) value labels ------------------------------------------------------------------------

def value_labels(ent: pd.DataFrame, n: int = TOP_N_LABELS) -> pd.DataFrame:
    frames = []
    for var in LABEL_VARS:
        counts = ent[var].astype("string").fillna("(missing)").value_counts()
        top = counts.head(n).rename_axis("label").reset_index(name="count")
        top.insert(0, "rank", range(1, len(top) + 1))
        top.insert(0, "variable", var)
        top["distinct_values"] = counts.size
        top["other_count"] = int(counts.iloc[n:].sum())
        frames.append(top)
    return pd.concat(frames, ignore_index=True)


def sector_group(ent: pd.DataFrame, cfg: dict) -> pd.Series:
    """Sector group of each enterprise from its ISIC class code; first matching rule wins."""
    sg = cfg["sector_groups"]
    code = code_of(ent[sg["variable"]])
    out = pd.Series(pd.NA, index=ent.index, dtype="string")
    for g in sg["groups"]:
        hit = np.logical_or.reduce([code.between(lo, hi).fillna(False).to_numpy() for lo, hi in g["ranges"]])
        out = out.mask(out.isna() & hit, g["name"])
    out = out.mask(code.isna(), sg["missing_code_group"])
    return out.fillna("unmapped")


def sector_groups(ent: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    g = sector_group(ent, cfg)
    op = is_operating(ent)
    order = [x["name"] for x in cfg["sector_groups"]["groups"]] + [cfg["sector_groups"]["missing_code_group"], "unmapped"]
    t = pd.DataFrame({"sector_group": order,
                      "all": [int((g == k).sum()) for k in order],
                      "operating": [int(((g == k) & op).sum()) for k in order]})
    return t


# (f) survey design -----------------------------------------------------------------------

def psu_key(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """Composite PSU code built from the configured variables (state, lga, ea)."""
    parts = cfg["survey_design"]["psu"]
    return df[parts].astype("string").fillna("(missing)").agg("|".join, axis=1)


def survey_design(ent: pd.DataFrame, cover: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    d = cfg["survey_design"]
    w, st, parts = d["weight"], d["strata"], d["psu"]
    cover = cover.assign(psu=psu_key(cover, cfg))
    cover_cols = ["hhid", w, st, "psu"] + [c for c in ["interview_result"] if c in cover.columns]
    m = ent.assign(psu_ent=psu_key(ent, cfg))[ENT_KEY + ["psu_ent"]].merge(
        cover[cover_cols], on="hhid", how="left", indicator=True)
    matched = (m["_merge"] == "both").to_numpy()
    has_w = matched & (m[w].notna() & (m[w] > 0)).to_numpy()
    op = is_operating(ent).to_numpy()
    psu_name = "PSU (" + " x ".join(parts) + ")"
    rows = [
        ("enterprises", "total", len(m)),
        ("enterprises", "household found in cover file", int(matched.sum())),
        ("enterprises", "household not in cover file", int((~matched).sum())),
        ("enterprises", f"with positive {w}", int(has_w.sum())),
        ("enterprises", f"{w} missing or non-positive", int((matched & ~has_w).sum())),
        ("enterprises", f"operating, with positive {w}", int((has_w & op).sum())),
        ("enterprises", f"operating, {w} missing or non-positive", int((matched & ~has_w & op).sum())),
        ("enterprises", f"{psu_name} differs between enterprise and cover file",
         int((matched & (m["psu_ent"] != m["psu"]).to_numpy()).sum())),
        ("households with enterprises", "total", int(ent["hhid"].nunique())),
        ("households with enterprises", f"{w} missing or non-positive",
         int(m.loc[matched & ~has_w, "hhid"].nunique())),
    ]
    # coverage under each weight in the cover file, for comparison with the configured one
    for alt in [c for c in cover.columns if c.startswith("wt_")]:
        aw = m[["hhid"]].merge(cover[["hhid", alt]], on="hhid", how="left")[alt]
        ok = (aw.notna() & (aw > 0)).to_numpy()
        rows.append(("operating enterprises by weight variable", f"{alt} missing or non-positive",
                     int((op & ~ok).sum())))
    if "interview_result" in m.columns:
        for res, k in m.loc[matched & ~has_w, "interview_result"].fillna("(missing)").value_counts().items():
            rows.append(("enterprises without weight, by interview_result", str(res), int(k)))

    rows += [
        ("cover file", "households", len(cover)),
        ("cover file", f"households with {w} missing", int(cover[w].isna().sum())),
        ("cover file", f"strata ({st})", int(cover[st].nunique())),
        ("cover file", psu_name, int(cover["psu"].nunique())),
    ]
    for label, mask in [("enterprises with positive weight", has_w),
                        ("operating enterprises with positive weight", has_w & op)]:
        sub = m.loc[mask]
        per_stratum = sub.groupby(st)["psu"].nunique()
        rows += [
            (label, f"strata ({st}) represented", int(sub[st].nunique())),
            (label, f"{psu_name} represented", int(sub["psu"].nunique())),
            (label, f"min {psu_name} per stratum", int(per_stratum.min()) if len(per_stratum) else 0),
            (label, f"{psu_name} spanning more than one stratum",
             int((sub.groupby("psu")[st].nunique() > 1).sum())),
        ]

    # uniqueness of candidate PSU codes across states and strata
    candidates = {psu_name: "psu", "ea alone": "ea"}
    if "cluster" in cover.columns:
        candidates["cluster (cover file)"] = "cluster"
    for name, c in candidates.items():
        item = f"PSU candidate {name}"
        rows.append((item, "distinct codes", int(cover[c].nunique())))
        if "state" in cover.columns:
            rows.append((item, "codes found in more than one state",
                         int((cover.groupby(c)["state"].nunique() > 1).sum())))
        rows.append((item, f"codes spanning more than one stratum ({st})",
                     int((cover.groupby(c)[st].nunique() > 1).sum())))
    if "zone" in cover.columns:
        rows.append(("cover file", f"households whose {st} differs from zone code",
                     int((code_of(cover["zone"]) != cover[st]).sum())))
    return pd.DataFrame(rows, columns=["item", "measure", "count"])


def worker_file_summary(ent: pd.DataFrame, workers: pd.DataFrame) -> pd.DataFrame:
    ent_idx = pd.MultiIndex.from_frame(ent[ENT_KEY])
    wk_idx = pd.MultiIndex.from_frame(workers[ENT_KEY])
    rows = [
        ("rows (household member x enterprise)", len(workers)),
        ("enterprises with at least one row", int(wk_idx.unique().size)),
        ("enterprises in sect8b with no row", int((~ent_idx.isin(wk_idx)).sum())),
        ("rows whose enterprise is not in sect8b", int((~wk_idx.isin(ent_idx)).sum())),
    ]
    long = ent.melt(id_vars=ENT_KEY, value_vars=OWNERS, value_name="indiv").dropna(subset=["indiv"])
    owner_idx = pd.MultiIndex.from_frame(long[ENT_KEY + ["indiv"]].astype("int64"))
    wk_person = pd.MultiIndex.from_frame(workers[ENT_KEY + ["indiv"]].astype("int64"))
    rows.append(("owner slots (s8q6_1, s8q6_2) filled", len(owner_idx)))
    rows.append(("owner slots with no matching sect8c row", int((~owner_idx.isin(wk_person)).sum())))
    return pd.DataFrame(rows, columns=["measure", "count"])


# report ----------------------------------------------------------------------------------

def build_report(ent: pd.DataFrame, workers: pd.DataFrame, cover: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    return {
        "counts": enterprise_counts(ent),
        "months_distribution": months_distribution(ent, cover, cfg),
        "month_flags_by_interview": month_flag_share_by_interview(ent, cover, cfg),
        "percentiles": value_percentiles(ent),
        "percentiles_upper": value_percentiles(ent, UPPER_PERCENTILES, with_max=True),
        "profit_checks": profit_checks(ent),
        "top_values": top_values(ent),
        "ownership": ownership(ent),
        "value_labels": value_labels(ent),
        "sector_groups": sector_groups(ent, cfg),
        "survey_design": survey_design(ent, cover, cfg),
        "worker_file": worker_file_summary(ent, workers),
    }


TITLES = {
    "counts": "(a) Enterprise counts and missing or zero sales (s8q29) and profit (s8q30)",
    "months_distribution": "(b) Months flagged in the annualisation window, by operating status",
    "month_flags_by_interview": "(b) Share of operating enterprises flagging each s8q9 month, by interview month",
    "percentiles": "(c) Monthly sales and profit percentiles (naira, unweighted)",
    "percentiles_upper": "(c) Upper tail of monthly sales and profit (naira, unweighted; console only, not saved)",
    "profit_checks": "(c) Profit consistency checks",
    "top_values": "(c) Ten largest values, sales and profit sorted independently (naira; console only, not saved)",
    "ownership": "(d) Ownership and enterprises per household",
    "value_labels": "(e) Value labels as recorded (top 15 per variable)",
    "sector_groups": "(e) Enterprises by sector group (config sector_groups)",
    "survey_design": "(f) Survey design linkage",
    "worker_file": "sect8c (enterprise workers) linkage",
}


def check_no_identifiers(tables: dict[str, pd.DataFrame]) -> None:
    for name, t in tables.items():
        bad = ID_COLUMNS & set(map(str, t.columns))
        if bad:
            raise ValueError(f"audit table {name} contains identifier columns: {sorted(bad)}")


def format_report(tables: dict[str, pd.DataFrame], cfg: dict) -> str:
    a, d = cfg["annualisation"], cfg["survey_design"]
    lines = [f"Non-farm enterprise audit. Window rule: {a['rule']} ({a['window_months']} months). "
             f"Weight: {d['weight']}. PSU: {' x '.join(d['psu'])}. Strata: {d['strata']}."]
    with pd.option_context("display.width", 250, "display.max_columns", 50, "display.max_colwidth", 70,
                           "display.float_format", lambda x: f"{x:,.3f}".rstrip("0").rstrip(".")):
        for name, t in tables.items():
            lines += ["", TITLES[name], "-" * len(TITLES[name]), t.to_string(index=False)]
    return "\n".join(lines)


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
    """Write aggregate tables as CSV. Tables in CONSOLE_ONLY are never written."""
    tables = {k: v for k, v in tables.items() if k not in CONSOLE_ONLY}
    check_no_identifiers(tables)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, t in tables.items():
        p = out_dir / f"audit_{name}.csv"
        t.to_csv(p, index=False)
        paths.append(p)
    return paths


def run(zip_path: str | Path | None = None, out_dir: str | Path | None = None,
        config_path: str | Path | None = None) -> dict[str, pd.DataFrame]:
    cfg = load_config(config_path)
    ent = read_table(ENTERPRISE_FILE, zip_path=zip_path)
    workers = read_table(WORKER_FILE, zip_path=zip_path)
    cover = read_table(COVER_FILE, zip_path=zip_path)
    tables = build_report(ent, workers, cover, cfg)
    print(format_report(tables, cfg))
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
