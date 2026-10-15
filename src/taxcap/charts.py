"""Figures for the report, run as ``python -m taxcap.charts``.

Reads only the aggregate tables in outputs/tables/*.csv, never the survey data, and writes PNGs (200 dpi)
to outputs/figures/. One colour-blind-safe palette is used throughout (validated categorical slots 1-3);
the third slot sits below 3:1 contrast on white, so its marks always carry a direct label and their own
marker shape. Titles are built from the table values.
"""
from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "outputs" / "tables"
FIGURES = ROOT / "outputs" / "figures"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"   # categorical slots 1-3 (validated, all pairs)
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BASES = {"nominal": ("if incomes have not grown since 2023/24", BLUE, "o"),
         "cpi": ("if incomes kept pace with inflation", ORANGE, "s")}
SOURCE = "Source: GHS-Panel Wave 5 (2023/24), author's calculations."
THRESHOLD = "₦800,000"
DPI = 200
FIGURES_PRODUCED = [f"fig{i}_{n}.png" for i, n in enumerate(
    ["headline", "zones", "local_payments", "model_vs_rule", "fairness", "importance", "calibration"], start=1)]

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "font.size": 9,
    "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "legend.frameon": False, "figure.facecolor": "white",
})


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(TABLES / f"{name}.csv")


def pct(x: float, digits: int = 0) -> str:
    return f"{100 * x:.{digits}f}%"


def zone_label(z: str) -> str:
    return str(z).split(". ", 1)[-1]


TITLE_PT, SUB_PT, LINE = 11.5, 8.5, 1.3


def _wrap(text: str, width_in: float, size_pt: float, bold: bool = False) -> list[str]:
    """Wrap to the figure width; average glyph width about 0.55 em (0.6 em bold) for DejaVu Sans."""
    per_char = size_pt / 72 * (0.6 if bold else 0.55)
    lines = []
    for part in text.split("\n"):
        lines += textwrap.wrap(part, max(20, int((width_in - 0.25) / per_char))) or [""]
    return lines


def frame(fig, title: str, subtitle: str) -> None:
    """Title, subtitle and source line, wrapped to the figure width; the plot's top margin follows the
    wrapped header so nothing overlaps or runs off the canvas."""
    w, h = fig.get_size_inches()
    t_lines = _wrap(title, w, TITLE_PT, bold=True)
    s_lines = _wrap(subtitle, w, SUB_PT)
    pad = 0.1 / h
    y = 1 - pad
    fig.text(0.01, y, "\n".join(t_lines), ha="left", va="top", fontsize=TITLE_PT, fontweight="bold", color=INK,
             linespacing=LINE)
    y -= len(t_lines) * TITLE_PT * LINE / 72 / h + 0.06 / h
    fig.text(0.01, y, "\n".join(s_lines), ha="left", va="top", fontsize=SUB_PT, color=INK2, linespacing=LINE)
    y -= len(s_lines) * SUB_PT * LINE / 72 / h
    fig.text(0.01, 0.015, SOURCE, ha="left", fontsize=7.5, color=INK2)
    extra = 0.45 if any(ax.get_title(loc="left") for ax in fig.axes) else 0.3   # room for panel titles
    fig.subplots_adjust(top=y - extra / h)


def save(fig, name: str, out: Path) -> Path:
    path = out / name
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def dot_ci(ax, y, est, lo, hi, color, marker, label=None, hollow=None, size=6):
    est, lo, hi = np.asarray(est, float), np.asarray(lo, float), np.asarray(hi, float)
    ax.hlines(y, lo, hi, color=color, linewidth=2)
    hollow = np.zeros(len(est), bool) if hollow is None else np.asarray(hollow, bool)
    ax.plot(est[~hollow], np.asarray(y)[~hollow], marker, color=color, markersize=size, label=label,
            markeredgecolor="white", markeredgewidth=1, linestyle="none")
    if hollow.any():
        ax.plot(est[hollow], np.asarray(y)[hollow], marker, markerfacecolor="white", markeredgecolor=color,
                markersize=size, markeredgewidth=1.5, linestyle="none")


def percent_axis(ax, axis="x"):
    fmt = matplotlib.ticker.PercentFormatter(1.0, decimals=0)
    (ax.xaxis if axis == "x" else ax.yaxis).set_major_formatter(fmt)


# figures --------------------------------------------------------------------------------------

def fig_headline(out: Path) -> Path:
    h = read("est_headline").set_index("price_basis")
    s = read("est_sensitivity")
    s = s[s["measure"] == "share above threshold"]
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    fig.subplots_adjust(left=0.27, right=0.97, bottom=0.2)
    for i, (b, (label, color, marker)) in enumerate(BASES.items()):
        rng = s.loc[s["price_basis"] == b, "estimate"]
        ax.barh(i, rng.max() - rng.min(), left=rng.min(), height=0.42, color=color, alpha=0.18, linewidth=0)
        r = h.loc[b]
        dot_ci(ax, [i], [r.estimate], [r.ci_low], [r.ci_high], color, marker, size=8)
        ax.annotate(f"{pct(r.estimate)} (95% CI {pct(r.ci_low)}-{pct(r.ci_high)})", (r.ci_high, i),
                    xytext=(8, 0), textcoords="offset points", va="center", fontsize=8.5, color=INK)
    ax.set_yticks([0, 1], [textwrap.fill(BASES[b][0], 22) for b in BASES])
    ax.set_ylim(-0.6, 1.6)
    ax.set_xlim(0, 0.75)
    percent_axis(ax)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Share of operating non-farm enterprises with annual income above " + THRESHOLD)
    n = int(h.loc["nominal", "n"])
    frame(fig, f"About {pct(h.loc['nominal', 'estimate'])} to {pct(h.loc['cpi', 'estimate'])} of informal businesses "
               f"earn above {THRESHOLD} a year",
          f"Survey-weighted share, point and 95% CI; light band = range across {s['scenario'].nunique()} sensitivity "
          f"scenarios. n = {n:,} enterprises.")
    return save(fig, "fig1_headline.png", out)


def fig_zones(out: Path) -> Path:
    d = read("est_domains")
    d = d[d["domain_type"] == "zone"].copy()
    d["zone"] = d["domain"].map(zone_label)
    order = d[d["price_basis"] == "nominal"].sort_values("estimate")["zone"].tolist()
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    fig.subplots_adjust(left=0.17, right=0.97, bottom=0.2)
    for k, (b, (label, color, marker)) in enumerate(BASES.items()):
        r = d[d["price_basis"] == b].set_index("zone").loc[order]
        y = np.arange(len(order)) + (k - 0.5) * 0.28
        dot_ci(ax, y, r["estimate"], r["ci_low"], r["ci_high"], color, marker, label=label)
    ax.set_yticks(range(len(order)), order)
    ax.set_xlim(0, 0.8)
    percent_axis(ax)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Share with annual income above " + THRESHOLD)
    ax.legend(loc="lower right", fontsize=8)
    nom = d[d["price_basis"] == "nominal"].set_index("zone")["estimate"]
    n = int(d[d["price_basis"] == "nominal"]["n"].sum())
    frame(fig, f"The share above {THRESHOLD} ranges from {pct(nom.min())} ({nom.idxmin()}) to {pct(nom.max())} "
               f"({nom.idxmax()}) if incomes have not grown",
          f"Survey-weighted share by geopolitical zone, point and 95% CI; sorted by the first price basis. "
          f"n = {n:,} enterprises.")
    return save(fig, "fig2_zones.png", out)


def fig_local_payments(out: Path) -> Path:
    r = read("est_registration_payments")
    pays = r["measure"].str.contains("s8q11b") & ~r["measure"].str.contains("not registered")
    reg = r["measure"].str.contains(r"\(s8q11\)$") & ~r["measure"].str.contains("pays")
    rows = [("Paying local authorities to operate:\nabove " + THRESHOLD, pays, "above threshold"),
            ("Paying local authorities to operate:\nat or below " + THRESHOLD, pays, "at or below threshold"),
            ("Officially registered:\nabove " + THRESHOLD, reg, "above threshold"),
            ("Officially registered:\nat or below " + THRESHOLD, reg, "at or below threshold")]
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    fig.subplots_adjust(left=0.33, right=0.97, bottom=0.2)
    for k, (b, (label, color, marker)) in enumerate(BASES.items()):
        sel = [r[m & (r["group"] == g) & (r["price_basis"] == b)].iloc[0] for _, m, g in rows]
        y = np.arange(len(rows))[::-1] + (0.5 - k) * 0.28
        dot_ci(ax, y, [x.estimate for x in sel], [x.ci_low for x in sel], [x.ci_high for x in sel], color, marker,
               label=label)
    ax.set_yticks(np.arange(len(rows))[::-1], [x[0] for x in rows])
    ax.set_xlim(0, 0.8)
    percent_axis(ax)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Survey-weighted share of enterprises")
    ax.legend(loc="lower right", fontsize=8)
    a = r[pays & (r["group"] == "above threshold") & (r["price_basis"] == "nominal")].iloc[0]
    b = r[pays & (r["group"] == "at or below threshold") & (r["price_basis"] == "nominal")].iloc[0]
    n = int(r[(r["group"] == "all enterprises in the analysis sample")]["n"].iloc[0])
    frame(fig, f"{pct(a.estimate)} of businesses above {THRESHOLD} and {pct(b.estimate)} of those below pay local "
               "authorities to operate, if incomes have not grown",
          f"Share paying local authorities to operate (s8q11b) and share registered (s8q11), point and 95% CI. "
          f"n = {n:,} enterprises.")
    return save(fig, "fig3_local_payments.png", out)


def fig_model_vs_rule(out: Path) -> Path:
    m = read("test_metrics")
    split = read("split_summary")
    n_test = int(split[(split["zone"] == "all") & (split["set"] == "test") & (split["measure"] == "enterprises")]["value"].iloc[0])
    pref = m[m["role"] == "headline"].iloc[0]
    model, fs = pref["model"], pref["feature_set"]

    def get(name, set_, metric):
        return m[(m["model"] == name) & (m["feature_set"] == set_) & (m["metric"] == metric)].iloc[0]

    series = [("Registration rule (s8q11)", AQUA, "D", lambda k: get("rule_registered", "-", f"rule_{k}")),
              ("Model, false-flag rate at most 10%", BLUE, "o", lambda k: get(model, fs, f"ffr10_{k}")),
              ("Model, recall at least 50%", ORANGE, "s", lambda k: get(model, fs, f"rec50_{k}"))]
    metrics = [("recall", "Recall"), ("precision", "Precision"), ("false_flag_rate", "False-flag rate")]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    fig.subplots_adjust(left=0.17, right=0.97, bottom=0.2)
    for k, (label, color, marker, f) in enumerate(series):
        rows = [f(key) for key, _ in metrics]
        y = np.arange(len(metrics))[::-1] + (1 - k) * 0.26
        dot_ci(ax, y, [r.estimate for r in rows], [r.ci_low for r in rows], [r.ci_high for r in rows], color,
               marker, label=label)
        if color == AQUA:   # below 3:1 contrast: label every aqua mark directly
            for yy, r in zip(y, rows):
                ax.annotate(pct(r.estimate), (r.ci_high, yy), xytext=(5, 0), textcoords="offset points",
                            va="center", fontsize=7.5, color=INK)
    ax.set_yticks(np.arange(len(metrics))[::-1], [x[1] for x in metrics])
    ax.set_xlim(0, 1)
    percent_axis(ax)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8)
    r_m, r_r = get(model, fs, "ffr10_recall").estimate, get("rule_registered", "-", "rule_recall").estimate
    frame(fig, f"With at most 10% false flags, the model identifies {pct(r_m)} of businesses above {THRESHOLD}; "
               f"registration identifies {pct(r_r)}",
          f"Test set, survey-weighted, 95% bootstrap intervals; incomes kept pace with inflation. Model: logistic "
          f"regression, feature set {fs}. n = {n_test:,} enterprises.")
    return save(fig, "fig4_model_vs_rule.png", out)


def fig_fairness(out: Path) -> Path:
    g = read("oof_groups")
    g = g[~g["group"].str.contains("missing|unlinked")]
    g = g[g["group_type"].isin(["owner_gender", "urban_rural", "zone"])]
    names = {"female": "Female owner", "male": "Male owner", "rural": "Rural", "urban": "Urban"}
    keys = (g[["group_type", "group"]].drop_duplicates()
            .assign(o=lambda x: x["group_type"].map({"owner_gender": 0, "urban_rural": 1, "zone": 2})).sort_values(["o", "group"]))
    labels = [names.get(r.group, zone_label(r.group)) for r in keys.itertuples()]
    y = np.arange(len(keys))[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(8, 5.4), sharey=True)
    fig.subplots_adjust(left=0.16, right=0.86, bottom=0.12, wspace=0.12)
    for ax, (metric, title) in zip(axes, [("false_flag_rate", "False-flag rate"), ("recall", "Recall")]):
        r = g[g["metric"] == metric].set_index(["group_type", "group"]).loc[list(zip(keys.group_type, keys.group))]
        dot_ci(ax, y, r["estimate"], r["ci_low"], r["ci_high"], BLUE, "o", hollow=r["unreliable"])
        ax.set_title(title, fontsize=9.5, color=INK, loc="left")
        ax.set_xlim(0, 0.7)
        percent_axis(ax)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y, labels)
    prev = g[g["metric"] == "prevalence"].set_index(["group_type", "group"]).loc[list(zip(keys.group_type, keys.group))]
    for yy, p in zip(y, prev["estimate"]):
        axes[1].annotate(f"{pct(p)} above", (1.02, yy), xycoords=("axes fraction", "data"), va="center", fontsize=7.5,
                         color=INK2, annotation_clip=False)
    axes[1].annotate("Share above\nthreshold", (1.02, y.max() + 0.9), xycoords=("axes fraction", "data"),
                     fontsize=7.5, color=INK2, annotation_clip=False, va="bottom")
    ffr = g[g["metric"] == "false_flag_rate"]
    lo, hi = ffr.loc[ffr["estimate"].idxmin()], ffr.loc[ffr["estimate"].idxmax()]
    n = int(g[(g["metric"] == "prevalence") & (g["group_type"] == "urban_rural")]["n_group"].sum())
    frame(fig, f"False-flag rates range from {pct(lo.estimate)} ({names.get(lo.group, zone_label(lo.group))}) to "
               f"{pct(hi.estimate)} ({names.get(hi.group, zone_label(hi.group))}) across groups",
          f"Out-of-fold predictions on training PSUs, flagged at the false-flag-rate operating point; 95% bootstrap "
          f"intervals; hollow = unreliable. n = {n:,} enterprises.")
    return save(fig, "fig5_fairness.png", out)


def fig_importance(out: Path) -> Path:
    t = read("test_importance").sort_values("mean_drop_pr_auc")
    pretty = {"durable_assets": "Durable assets (42 items)", "housing": "Housing materials (3)",
              "non_household_employees": "Non-household employees", "any_member_mobile_phone": "Mobile phone access",
              "any_member_internet": "Internet access", "any_member_account": "Financial account",
              "any_member_formal_savings": "Formal savings", "household_internet_connection": "Household internet",
              "years_in_operation": "Years in operation", "household_size": "Household size",
              "sector_group": "Sector group", "registered": "Registered", "premises": "Premises type",
              "state": "State", "zone": "Zone", "urban": "Urban/rural"}
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    fig.subplots_adjust(left=0.3, right=0.97, bottom=0.16)
    y = np.arange(len(t))
    ax.barh(y, t["mean_drop_pr_auc"], height=0.6, color=BLUE, linewidth=0)
    ax.errorbar(t["mean_drop_pr_auc"], y, xerr=t["sd_drop_pr_auc"], fmt="none", ecolor=INK2, elinewidth=1, capsize=2)
    ax.axvline(0, color=INK2, linewidth=0.8)
    ax.set_yticks(y, [pretty.get(f, f) for f in t["feature_group"]])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Mean drop in weighted PR-AUC when the feature group is permuted (bar) and SD (line)")
    top = t.sort_values("mean_drop_pr_auc", ascending=False)["feature_group"].tolist()
    n = int(read("test_calibration")["n"].sum())
    frame(fig, f"{pretty.get(top[0], top[0])} and {pretty.get(top[1], top[1]).lower()} carry the most predictive "
               "signal in the preferred model",
          f"Test-set permutation importance, logistic regression feature set A, 20 repeats. n = {n:,} enterprises.")
    return save(fig, "fig6_importance.png", out)


def fig_calibration(out: Path) -> Path:
    c = read("test_calibration")
    fig, ax = plt.subplots(figsize=(6.0, 6.2))
    fig.subplots_adjust(left=0.14, right=0.95, bottom=0.12)
    ax.plot([0, 1], [0, 1], color=INK2, linewidth=1, linestyle="--", label="Perfect calibration")
    ax.plot(c["weighted_mean_predicted"], c["weighted_observed"], "o-", color=BLUE, markersize=7, linewidth=2,
            markeredgecolor="white", label="Decile of predicted probability")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    percent_axis(ax, "x")
    percent_axis(ax, "y")
    ax.set_xlabel("Mean predicted probability (weighted)")
    ax.set_ylabel("Observed share above threshold (weighted)")
    ax.legend(loc="upper left", fontsize=8)
    gap = float((c["weighted_observed"] - c["weighted_mean_predicted"]).abs().mean())
    frame(fig, f"Observed and predicted shares differ by {100 * gap:.1f} points on average across deciles",
          f"Test-set calibration, logistic regression feature set A, {len(c)} deciles. n = {int(c['n'].sum()):,} "
          "enterprises.")
    return save(fig, "fig7_calibration.png", out)


FIGURES_FUNCS = [fig_headline, fig_zones, fig_local_payments, fig_model_vs_rule, fig_fairness, fig_importance,
                 fig_calibration]


def run(out_dir: Path | None = None, tables_dir: Path | None = None) -> list[Path]:
    global TABLES
    saved = TABLES
    if tables_dir is not None:
        TABLES = Path(tables_dir)
    out = Path(out_dir) if out_dir else FIGURES
    out.mkdir(parents=True, exist_ok=True)
    try:
        return [f(out) for f in FIGURES_FUNCS]
    finally:
        TABLES = saved


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", dest="out_dir", default=None)
    args = ap.parse_args(argv)
    for p in run(args.out_dir):
        print(p)


if __name__ == "__main__":
    main()
