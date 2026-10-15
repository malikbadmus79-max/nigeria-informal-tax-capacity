import numpy as np
import pandas as pd
import pytest

from taxcap import audit
from taxcap.load import load_config


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def report(audit_frames, cfg):
    ent, workers, cover = audit_frames
    return audit.build_report(ent, workers, cover, cfg)


def lookup(table, key_cols, keys, value_col):
    mask = np.logical_and.reduce([table[c] == k for c, k in zip(key_cols, keys)])
    assert mask.sum() == 1, f"{keys} not unique in table"
    return table.loc[mask, value_col].iloc[0]


def test_code_of_reads_leading_code():
    codes = audit.code_of(pd.Series(["1. CURRENTLY OPERATING", "96. OTHER (SPECIFY)", None]))
    assert codes.iloc[0] == 1 and codes.iloc[1] == 96
    assert pd.isna(codes.iloc[2])


def test_interview_month_index_uses_flag_origin(cfg):
    # s8q9__1 = January 2023, so February 2024 is flag 14 and May 2024 is flag 17
    cover = pd.DataFrame({"hhid": [1, 2, 3], "InterviewStart": ["2024-02-28T18:16:12", "2024-05-02T08:00:00", None]})
    idx = audit.interview_month_index(cover, cfg)
    assert idx.loc[1] == 14 and idx.loc[2] == 17
    assert pd.isna(idx.loc[3])


def test_window_bounds_end_at_interview_month(audit_frames, cfg):
    ent, _, cover = audit_frames
    b = audit.window_bounds(ent, cover, cfg)
    assert b.iloc[0].tolist() == [3, 14]   # February 2024 interview
    assert b.iloc[3].tolist() == [4, 15]   # March 2024 interview
    may = audit.window_bounds(ent, cover.assign(InterviewStart="2024-05-02T08:00:00"), cfg)
    assert may.iloc[0].tolist() == [5, 16]  # May 2024 interview: capped at s8q9__16 = April 2024
    fixed = audit.window_bounds(ent, cover, cfg, "fixed_calendar_window")
    fw = cfg["annualisation"]["fixed_window_sensitivity"]
    assert fixed.iloc[3].tolist() == [fw["first_month_flag"], fw["last_month_flag"]]


def test_window_bounds_rejects_unknown_rule(audit_frames, cfg):
    ent, _, cover = audit_frames
    with pytest.raises(ValueError):
        audit.window_bounds(ent, cover, cfg, "no_such_rule")


def test_enterprise_counts(report):
    t = report["counts"]

    def get(item, measure):
        return lookup(t, ["item", "measure"], [item, measure], "count")

    assert get("enterprises", "total") == 4
    assert get("enterprises", "currently operating (s8q3 = 1)") == 3
    assert get("s8q29 (sales)", "zero, all") == 1
    assert get("s8q30 (profit)", "zero, operating") == 1
    assert get("s8q29 (sales)", "missing, all") == 0
    assert get("s8q29 and s8q30", "both zero, all") == 1


def test_months_in_window_counts_only_window_flags(audit_frames, cfg):
    ent, _, cover = audit_frames
    n = audit.months_in_window(ent, cover, cfg)
    # enterprise 2 flags s8q9__0, __1 and __16 only, all outside a February 2024 window
    assert n.iloc[0] == 12 and n.iloc[1] == 0 and n.iloc[2] == 6
    assert pd.isna(n.iloc[3])
    fixed = audit.months_in_window(ent, cover, cfg, "fixed_calendar_window")
    assert fixed.iloc[0] == 11   # s8q9__3 falls outside April 2023 to March 2024


def test_months_in_window_capped_for_may_interview(audit_frames, cfg):
    ent, _, cover = audit_frames
    n = audit.months_in_window(ent, cover.assign(InterviewStart="2024-05-02T08:00:00"), cfg)
    # enterprise 1 flags March 2023 to February 2024: 10 of them fall in May 2023 to April 2024
    assert n.iloc[0] == 10 and n.iloc[1] == 1


def test_months_in_window_missing_interview_date(audit_frames, cfg):
    ent, _, cover = audit_frames
    cover = cover.assign(InterviewStart=[None, "2024-02-11T09:00:00", "2024-03-05T09:00:00", None])
    n = audit.months_in_window(ent, cover, cfg)
    assert pd.isna(n.iloc[0]) and pd.isna(n.iloc[1]) and n.iloc[2] == 6


def test_months_distribution(report):
    t = report["months_distribution"].set_index("months_in_window")
    assert t.loc["0", "operating"] == 1
    assert t.loc["12", "operating"] == 1
    assert t.loc["flags or interview date missing", "operating"] == 1
    assert t.loc["6", "not operating"] == 1
    assert t["total"].sum() == 4
    assert t.loc["11", "operating, fixed window (sensitivity)"] == 1


def test_month_flags_by_interview(report):
    t = report["month_flags_by_interview"].set_index("interview_month")
    assert t.loc["2024-02", "n_operating"] == 2
    assert t.loc["2024-02", "s8q9__16"] == 0.5
    assert t.loc["2024-02", "window_first_flag"] == 3 and t.loc["2024-02", "window_last_flag"] == 14
    assert t.loc["2024-02", "window_months_with_flag_column"] == 12
    assert t.loc["2024-03", "n_operating"] == 1


def test_percentiles_and_checks(report):
    p = report["percentiles"]
    assert lookup(p, ["variable", "population"], ["s8q29", "all"], "p50") == 75
    assert "max" not in p.columns and "p99.9" not in p.columns
    upper = report["percentiles_upper"]
    assert lookup(upper, ["variable", "population"], ["s8q30", "all"], "max") == 80
    assert lookup(p, ["variable", "population"], ["s8q29", "operating"], "n") == 3

    c = report["profit_checks"]

    def get(check, pop):
        return lookup(c, ["check", "population"], [check, pop], "count")

    assert get("profit < 0", "all") == 1
    assert get("profit < 0", "operating") == 0
    assert get("profit > sales", "all") == 1


def test_top_values_sorted_and_padded(report):
    t = report["top_values"]
    assert list(t.columns) == ["rank", "s8q29", "s8q30"]
    assert len(t) == audit.TOP_N_VALUES
    assert t["s8q29"].head(4).tolist() == [200, 100, 50, 0]
    assert t["s8q30"].head(4).tolist() == [80, 50, 0, -10]
    assert t["s8q29"].iloc[4:].isna().all()


def test_ownership(report):
    t = report["ownership"]

    def get(item, category):
        return lookup(t, ["item", "category"], [item, category], "all")

    assert get("owners listed (s8q6_1, s8q6_2)", "1 owner(s)") == 3
    assert get("owners listed (s8q6_1, s8q6_2)", "2 owner(s)") == 1
    assert get("households by enterprises operated", "more than one") == 1
    assert get("persons listed as owner", "total") == 4
    assert get("persons listed as owner", "owning more than one enterprise") == 1
    assert get("enterprises", "in a household operating more than one enterprise") == 2


def test_value_labels(report):
    t = report["value_labels"]
    s8q3 = t[t["variable"] == "s8q3"]
    assert s8q3.iloc[0]["label"] == "1. CURRENTLY OPERATING"
    assert s8q3.iloc[0]["count"] == 3
    assert set(t["variable"]) == set(audit.LABEL_VARS)
    assert (t.groupby("variable").size() <= audit.TOP_N_LABELS).all()


def test_sector_groups(report):
    t = report["sector_groups"].set_index("sector_group")
    assert t.loc["food_retail", "all"] == 2
    assert t.loc["transport", "all"] == 1
    assert t.loc["primary_manufacturing_utilities", "operating"] == 1
    assert t.loc["unmapped", "all"] == 0 and t["all"].sum() == 4


def test_sector_group_missing_code(audit_frames, cfg):
    ent = audit_frames[0].assign(s8q2b=[None, "161. Support activities for crop production", "4721. Retail", "9999. X"])
    g = audit.sector_group(ent, cfg)
    assert g.tolist() == ["not_coded", "primary_manufacturing_utilities", "food_retail", "personal_other_services"]


def test_survey_design(report):
    t = report["survey_design"]

    def get(item, measure):
        return lookup(t, ["item", "measure"], [item, measure], "count")

    psu = "PSU (state x lga x ea)"
    assert get("enterprises", "household found in cover file") == 4
    assert get("enterprises", "wt_cross_wave5 missing or non-positive") == 1
    assert get("enterprises", f"{psu} differs between enterprise and cover file") == 0
    assert get("cover file", psu) == 4
    assert get("enterprises with positive weight", "strata (strata) represented") == 2
    assert get("enterprises with positive weight", f"{psu} represented") == 2
    assert get("enterprises with positive weight", f"{psu} spanning more than one stratum") == 0
    assert get(f"PSU candidate {psu}", "codes found in more than one state") == 0
    assert get("PSU candidate ea alone", "distinct codes") == 3
    assert get("PSU candidate ea alone", "codes found in more than one state") == 1


def test_psu_key_separates_reused_ea_codes(audit_frames, cfg):
    cover = audit_frames[2]
    keys = audit.psu_key(cover, cfg)
    assert keys.nunique() == 4 and cover["ea"].nunique() == 3


def test_worker_file(report):
    t = report["worker_file"].set_index("measure")["count"]
    assert t["enterprises in sect8b with no row"] == 0
    assert t["owner slots (s8q6_1, s8q6_2) filled"] == 5
    assert t["owner slots with no matching sect8c row"] == 1


def test_no_identifier_columns_in_any_table(report):
    for name, t in report.items():
        assert not audit.ID_COLUMNS & set(t.columns), name


def test_check_no_identifiers_rejects_ids():
    with pytest.raises(ValueError):
        audit.check_no_identifiers({"bad": pd.DataFrame({"hhid": [1]})})


def test_run_writes_aggregate_csvs(audit_zip, tmp_path, capsys):
    out = tmp_path / "tables"
    tables = audit.run(zip_path=audit_zip, out_dir=out)
    files = sorted(out.glob("audit_*.csv"))
    assert {f.stem.removeprefix("audit_") for f in files} == set(tables) - audit.CONSOLE_ONLY
    assert not (out / "audit_top_values.csv").exists()
    assert not (out / "audit_percentiles_upper.csv").exists()
    for f in files:
        assert not audit.ID_COLUMNS & set(pd.read_csv(f).columns), f.name
    printed = capsys.readouterr().out
    assert "(a) Enterprise counts" in printed and "(f) Survey design linkage" in printed
    assert "Ten largest values" in printed
