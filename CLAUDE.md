# Project rules

## Data
- data_raw/ holds the World Bank GHS-Panel Wave 5 zip. Never extract it into the repo, modify it, or commit it.
- Never write record-level data (one row per household, person or enterprise) to any git-tracked path. Only aggregate tables go in outputs/.
- Read survey files through src/taxcap/load.py, not by hand-coded paths.
- Every assumption (threshold, price adjustment, income allocation, annualisation window) lives in config/assumptions.yaml with a source or an "assumption" label. Do not hard-code these values in code or notebooks.

## Analysis
- National and state estimates use survey weights (wt_wave5) and report uncertainty that accounts for clusters (ea) and strata.
- Model features are limited to characteristics a tax authority could observe. Sales, profit and costs are never model features.
- Model evaluation uses held-out enumeration areas (grouped splits), never random row splits.
- Changes to the analysis plan after seeing test results are recorded in docs/analysis_plan.md with a date and reason.

## Writing
- Neutral researcher voice: no "we", "our" or "you"; no placeholders; no bold lead-ins on bullets; no rhetorical or promotional phrasing.
- Every number in docs and reports traces to a source in docs/sources.md or to a notebook or output table.

## Code
- Tests use synthetic fixtures only (tests/conftest.py) and must pass without the real data.
- Commit messages describe what changed and why.
