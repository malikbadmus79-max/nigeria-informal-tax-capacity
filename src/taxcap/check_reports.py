"""Checks on the written reports, run as ``python -m taxcap.check_reports``.

1. Every number in reports/working_paper.md and reports/policy_brief.md is matched to a value in an
   outputs/tables/*.csv file, a figure quoted in docs/sources.md, or a design parameter in
   config/assumptions.yaml. Unmatched numbers are listed for review.
2. Forbidden wording: "we", "our", "us", "you", "levy", "levies", and sentences that place "tax" next to the
   payments recorded by s8q11b.
3. Word counts.

Writes reports/number_sources.md.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORTS = {"working_paper": ROOT / "reports" / "working_paper.md",
           "policy_brief": ROOT / "reports" / "policy_brief.md",
           "README": ROOT / "README.md"}
MUST_MATCH_BRIEF = {"README"}   # figures quoted in these documents must appear verbatim in the policy brief
TABLE_ORDER = ["est_exclusions", "est_design", "est_headline", "est_domains", "est_registration_payments",
               "est_income", "est_threshold_band", "est_sensitivity", "test_metrics", "test_differences",
               "test_calibration", "test_importance", "test_groups", "oof_groups", "cv_selected", "split_summary"]
NUMBER = re.compile(r"(?<![A-Za-z0-9_.\-/])₦?\d[\d,]*(?:\.\d+)?(?:%|th)?")
YEARS = {str(y) for y in range(2009, 2027)}
FORBIDDEN = re.compile(r"\b(we|our|us|you|levy|levies)\b", re.IGNORECASE)


def config_parameters(cfg: dict) -> dict[str, str]:
    m, e, r = cfg["model"], cfg["evaluation"], cfg["estimation"]["reliability"]
    return {
        "95%": "config estimation.confidence_level",
        f"{m['holdout_share'] * 100:g}%": "config model.holdout_share",
        f"{m['operating_points']['max_false_flag_rate'] * 100:g}%": "config model.operating_points.max_false_flag_rate",
        f"{m['operating_points']['min_recall'] * 100:g}%": "config model.operating_points.min_recall",
        f"{r['max_relative_se'] * 100:g}%": "config estimation.reliability.max_relative_se",
        f"{r['min_enterprises']}": "config estimation.reliability.min_enterprises",
        f"{r['min_psus']}": "config estimation.reliability.min_psus",
        f"{cfg['outliers']['winsorisation_percentile']:g}th": "config outliers.winsorisation_percentile",
        f"{e['bootstrap_replicates']:,}": "config evaluation.bootstrap_replicates",
        f"{e['permutation_repeats']}": "config evaluation.permutation_repeats",
        f"{m['near_tie_pr_auc']:g}": "config model.near_tie_pr_auc",
        f"{cfg['annualisation']['window_months']}": "config annualisation.window_months",
        "five": "config model.cv_folds",
    }


def _round(v: float, places: int) -> str:
    """Standard (half-up) rounding of the raw value, never of an already rounded display."""
    q = Decimal(1).scaleb(-places) if places else Decimal(1)
    return str(Decimal(repr(float(v))).quantize(q, ROUND_HALF_UP))


def table_index() -> dict[str, list[str]]:
    """Formatted value -> every table cell that produces it, as 'file [row label] column'.

    Percentages and decimals are formed by rounding the raw cell value once, so a number that was rounded
    twice in the text does not match. Several cells can produce the same text; all are listed.
    """
    idx: dict[str, list[str]] = {}

    def add(key: str, where: str) -> None:
        idx.setdefault(key, [])
        if where not in idx[key]:
            idx[key].append(where)

    for name in TABLE_ORDER:
        t = pd.read_csv(ROOT / "outputs" / "tables" / f"{name}.csv")
        label_cols = [c for c in t.columns
                      if not pd.api.types.is_numeric_dtype(t[c]) and not pd.api.types.is_bool_dtype(t[c])
                      and pd.to_numeric(t[c], errors="coerce").isna().all()][:3]
        for _, row in t.iterrows():
            label = " | ".join(str(row[c])[:60] for c in label_cols)
            for col in t.columns:
                where = f"{name}.csv [{label}] {col}"
                if isinstance(row[col], str) and pd.isna(pd.to_numeric(row[col], errors="coerce")):
                    for tok in NUMBER.findall(row[col]):   # numbers inside labels, such as a measure name
                        add(tok, where + " (label)")
                        add("\u20a6" + tok, where + " (label)")
                    continue
                v = pd.to_numeric(pd.Series([row[col]]), errors="coerce").iloc[0]
                if pd.isna(v) or isinstance(v, (bool, np.bool_)) or not np.isfinite(float(v)):
                    continue
                v = float(v)
                keys = {_round(v, 3), _round(v, 4)}
                if abs(v) <= 1:
                    keys |= {_round(100 * v, 1) + "%", _round(100 * v, 1)}
                if abs(v) >= 1:
                    whole = int(Decimal(repr(v)).quantize(Decimal(1), ROUND_HALF_UP))
                    keys |= {f"{whole:,}", f"\u20a6{whole:,}"}
                for k in keys:
                    add(k, where)
    return idx


def sources_index() -> dict[str, str]:
    idx = {}
    for line in (ROOT / "docs" / "sources.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| (T\d\d) \|", line)
        if m:
            for tok in NUMBER.findall(line.split("|", 3)[3]):
                idx.setdefault(tok, m.group(1))
    return idx


def classify(tok: str, tables, sources, params) -> str:
    bare = tok.rstrip(",")
    if bare in params:
        return params[bare]
    if bare in sources:
        return sources[bare]
    if bare in tables:   # every table cell that produces the value; the report text names the intended one
        hits = tables[bare]
        return "; ".join(hits[:3]) + (f"; and {len(hits) - 3} more" if len(hits) > 3 else "")
    if bare.replace("%", "") in YEARS:
        return "year or date"
    return ""


def check(name: str, tables, sources, params) -> tuple[pd.DataFrame, list[str], int]:
    text = REPORTS[name].read_text(encoding="utf-8")
    body = text.split("## References")[0]
    body = re.sub(r"(?s)```.*?```", "", body)                                # code blocks (commands)
    if name in MUST_MATCH_BRIEF:   # keep link and image alt text, which is checked; drop the URL or path
        body = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", body)
    body = re.sub(r"(CC BY|Attribution) 4\.0", "", body)                      # licence version
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)                       # figure paths
    body = re.sub(r"\[T\d\d(?:[,–\- ]+T?\d\d)*\]", "", body)                # source citations
    body = re.sub(r"(?m)^#+ \d+(\.\d+)?\.?", "", body)                     # section numbers in headings
    body = re.sub(r"(?m)^\d+\. ", "", body)                                 # numbered-list markers
    body = re.sub(r"\b\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|"
                  r"December) \d{4}\b", "", body)                               # dates
    body = re.sub(r"(?i)\bsections?\s+\d+(\.\d+)?|\bFigure \d|\bWave 5|\b[0-9a-f]{64}\b", "", body)
    rows = [{"number": tok.rstrip(","), "source": classify(tok, tables, sources, params)}
            for tok in NUMBER.findall(body)]
    numbers = pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame(columns=["number", "source"])
    issues = [f"forbidden word '{m.group(0)}'" for m in FORBIDDEN.finditer(text)]
    for sent in re.split(r"(?<=[.!?])\s+", text):
        low = sent.lower()
        if ("s8q11b" in low or "local authorit" in low) and re.search(r"\btax(es)?\b", low):
            if re.search(r"(local|authorit\w*)\s+tax|tax\w*\s+(paid\s+)?to\s+local|s8q11b\W+tax", low):
                issues.append(f"tax applied to local payments: {sent[:120]}")
    if name in MUST_MATCH_BRIEF:
        brief = REPORTS["policy_brief"].read_text(encoding="utf-8")
        for tok in numbers["number"]:
            if re.search(r"%|₦|\.", tok) and tok not in brief:
                issues.append(f"{tok} does not appear in the policy brief")
    words = len(re.findall(r"\b\w[\w'’-]*\b", text.split("## References")[0]))
    return numbers, issues, words


def run() -> dict:
    cfg = yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text(encoding="utf-8"))
    tables, sources, params = table_index(), sources_index(), config_parameters(cfg)
    out = ["# Number sources", "", "Generated by `python -m taxcap.check_reports`. For each number in the reports, the",
           "table cells (file, row label, column) or source IDs that produce it, with table values rounded once from",
           "the raw value. Where several cells produce the same text, up to three are listed; the report text names",
           "the table each number comes from.", ""]
    result = {}
    for name in REPORTS:
        numbers, issues, words = check(name, tables, sources, params)
        result[name] = {"numbers": numbers, "issues": issues, "words": words}
        out += [f"## {REPORTS[name].name}", "", f"Words (excluding references): {words}", "",
                "| Number | Source |", "| --- | --- |"]
        out += [f"| {r.number} | {r.source or 'UNMATCHED'} |" for r in numbers.itertuples()]
        out += ["", "Wording issues: " + ("; ".join(issues) if issues else "none"), ""]
    (ROOT / "reports" / "number_sources.md").write_text("\n".join(out), encoding="utf-8")
    return result


def main() -> None:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for name, r in run().items():
        n = r["numbers"]
        print(f"{name}: {r['words']} words, {len(n)} distinct numbers, "
              f"{int((n['source'] == '').sum())} unmatched, {len(r['issues'])} wording issues")
        for x in n.loc[n["source"] == "", "number"]:
            print("  UNMATCHED", x)
        for x in r["issues"]:
            print("  ISSUE", x)


if __name__ == "__main__":
    main()
