# Analysis Plan

As of 15 October 2026. Drafted after the data audit and before any income estimate, model fit or test-set evaluation.

This plan fixes the analytical decisions for the research question in [problem_statement.md](problem_statement.md). Parameter values named here are held in [config/assumptions.yaml](../config/assumptions.yaml), and code reads them from there. Audit counts are unweighted and come from the tables in `outputs/tables/audit_*.csv`, produced by `python -m taxcap.audit`. No result beyond those counts is reported here.

## 1. Data and survey design

Source: Nigeria General Household Survey Panel, Wave 5, post-harvest visit. Files: `sect8b_harvestw5` (enterprises), `sect8c_harvestw5` (enterprise workers) and `secta_harvestw5` (cover page), read through `src/taxcap/load.py`.

The enterprise file holds 3,436 enterprises in 2,673 households. Every enterprise links to a household in the cover file (`audit_survey_design.csv`).

### 1.1 Weight

Estimates use the cross-sectional household weight `wt_cross_wave5`, as the World Bank study description recommends for cross-sectional estimates. Each enterprise carries the weight of its household.

`wt_cross_wave5` is positive for all 3,436 enterprises, including all 3,338 operating enterprises. The alternatives cover fewer operating enterprises: `wt_wave5` is missing or non-positive for 22 and `wt_longpanel_wave5` for 2,429 (`audit_survey_design.csv`).

### 1.2 Primary sampling unit

The PSU is a composite of `state`, `lga` and `ea`. The `ea` code alone does not identify a PSU: 91 of its 398 distinct codes appear in more than one state. The composite gives 727 PSUs in the cover file, none of which appears in more than one state. Operating enterprises fall in 651 PSUs (`audit_survey_design.csv`).

### 1.3 Strata

Strata are given by `strata`, which takes 6 values. All 6 are represented among operating enterprises, with at least 98 PSUs in each.

Among operating enterprises, 11 PSUs contain households recorded in more than one stratum. For variance estimation, each PSU is assigned to the stratum held by most of its enterprises. Ties go to the lowest stratum code. Outputs that report standard errors state this assignment. For comparison, `strata` differs from the zone code for 54 households in the cover file.

## 2. Population

The primary population is enterprises currently operating at interview (`s8q3` = 1): 3,338 of 3,436. The 98 others are excluded from primary estimates. They comprise 63 temporarily closed, 27 seasonally closed and 8 permanently closed enterprises (`audit_counts.csv`, `audit_value_labels.csv`). Taxable capacity is assessed for businesses that are running, so closed enterprises are not included in the base.

As a sensitivity, the 90 temporarily or seasonally closed enterprises are added back, using the same income measure.

Operating enterprises are estimated as a domain of the full sample design, so all PSUs and strata stay in the variance calculation.

## 3. Income measure

### 3.1 Definition

Annual enterprise income is monthly profit (`s8q30`) multiplied by the number of months the enterprise operated in a 12-month window. The window ends at the interview month or at April 2024, whichever is earlier (section 3.2).

`s8q30` has no missing values among operating enterprises. Profit is zero for 11 operating enterprises and negative for 15 (`audit_counts.csv`, `audit_profit_checks.csv`). Negative profit is set to zero income, since a loss cannot fall above the threshold. No enterprise reports profit above sales.

### 3.2 Months operated

Months operated come from the `s8q9` flags. The questionnaire asks: "In which months did you operate this [NON-FARM ENTERPRISE] in the past 12 months?"

The month of each flag is set by `month_flag_origin` in the configuration, with `s8q9__1` as January 2023. Printed codes run from JANUARY 2023 = 01 to FEBRUARY 2024 = 14.

The data also hold flags `s8q9__0`, `s8q9__15` and `s8q9__16`, which are not printed in the questionnaire. Flags 15 and 16 are assumed to continue the sequence as March 2024 and April 2024. This is an assumption. The World Bank data dictionary for the file (catalog 6410, F74) gives the same labels, MARCH 2024 and APRIL 2024.

The data dictionary labels `s8q9__0` "ALL 12 MONTHS". No operating enterprise flags it, so it does not enter the count.

The interview month comes from `InterviewStart` in `secta_harvestw5`, a text field of the form `YYYY-MM-DDTHH:MM:SS`. The window ends at the interview month or at April 2024 (`s8q9__16`, the last month with a flag column), whichever is earlier. It covers that month and the 11 before it, so it differs by household. The cap is set by `annualisation.last_month_flag`.

Operating enterprises by interview month (`audit_month_flags_by_interview.csv`):

| Interview month | Operating enterprises | Window (flags) | Window months with a flag column |
| --- | --- | --- | --- |
| February 2024 | 2,880 | 3 to 14 | 12 |
| March 2024 | 361 | 4 to 15 | 12 |
| April 2024 | 12 | 5 to 16 | 12 |
| May 2024 | 85 | 5 to 16 | 12 |

For the 85 May 2024 interviews, the window ends at April 2024, the last month with a flag column. It is the same window as for April 2024 interviews.

Within each interview-month group, the share of enterprises flagging a month falls to zero after the interview month. For example, no February 2024 interview flags `s8q9__15`. A fixed calendar window would therefore cut short the months of households interviewed before the window ends. This is the reason for the household-specific window.

### 3.3 Distribution of months operated

The table shows operating enterprises by months operated (`audit_months_distribution.csv`).

| Months in window | Operating, interview-month window (primary) | Operating, fixed April 2023 to March 2024 window (sensitivity) |
| --- | --- | --- |
| 0 | 48 | 72 |
| 1 | 105 | 85 |
| 2 | 25 | 28 |
| 3 | 35 | 39 |
| 4 | 43 | 41 |
| 5 | 44 | 65 |
| 6 | 63 | 58 |
| 7 | 57 | 69 |
| 8 | 72 | 80 |
| 9 | 68 | 227 |
| 10 | 268 | 499 |
| 11 | 562 | 1,834 |
| 12 | 1,947 | 240 |
| Flags or interview date missing | 1 | 1 |

Under the primary window, 1,947 operating enterprises record all 12 months. Under the fixed window, 240 do, and 1,834 record 11 months.

Some enterprises report operating at interview but flag no month in the window: 48 under the primary rule. One more enterprise has no flags at all. These 49 are excluded from income estimates and threshold classification. They are counted and reported alongside every headline estimate.

### 3.4 Sensitivities

Three alternative income measures are run:

- Profit multiplied by 12, ignoring months operated.
- The fixed calendar window from April 2023 to March 2024 (flags 4 to 15), as set in `annualisation.fixed_window_sensitivity`.
- Flags 15 and 16 treated as missing, not as March and April 2024 (`annualisation.unprinted_flags_sensitivity`). This affects the 458 operating enterprises interviewed in March, April or May 2024. For them, months operated are counted over the window months that have a printed code and scaled to a 12-month equivalent.

## 4. Price adjustment

Results are reported in nominal 2023–2024 naira and also adjusted to 2026 prices.

The CPI source for the 2026 adjustment is still open. The Consumer Price Index was rebased in January 2025, and the method for linking the old and new series across the rebase is also open. Both are to be documented in `docs/sources.md` and entered in `price_adjustment` in the configuration before any adjusted figure is produced. Until then, `price_adjustment.method` is `none` and only nominal results are produced.

## 5. Threshold and unit of analysis

### 5.1 Threshold

The threshold is annual income above ₦800,000, the personal income tax exemption level under the Nigeria Tax Act 2025 (`tax_rules.pit_exemption_naira`).

### 5.2 Unit

The primary unit is the enterprise: each enterprise's annual income is compared with the threshold on its own.

As a sensitivity, the comparison is made at owner level (`income_allocation.rule: owner_sum`). Each person's income is the sum of income from all the enterprises they own. Income from enterprises with two owners is split equally between them.

The audit shows how much this matters. Among operating enterprises, 121 list two owners. Of 3,406 persons listed as owners, 51 own more than one enterprise (`audit_ownership.csv`).

### 5.3 Scope of income

Personal income tax applies to a person's total income, including wages, rent and other sources. Only non-farm enterprise income is measured here, so other income is out of scope. Enterprise-level results therefore understate how many individuals have total income above the threshold.

## 6. Outliers

No observation is deleted.

The headline shares are classifications above or below the threshold, so extreme values above the threshold do not change them.

Means and totals of income use profit winsorised at the weighted 99.5th percentile of operating enterprises (`outliers.winsorisation_percentile`). Untreated values are reported as a sensitivity. For reference, unweighted monthly profit among operating enterprises has a 99th percentile of ₦348,630 (`audit_percentiles.csv`). Values above the 99th percentile describe very few enterprises, so the audit prints them to the console only and does not save them.

The number of enterprises whose annual income lies within ±25% of the threshold (₦600,000 to ₦1,000,000; `outliers.threshold_band`) is reported, both weighted and unweighted. This shows how far the classification depends on recall error near the threshold.

## 7. Estimation and uncertainty

Shares, means and totals are survey-weighted. Standard errors are Taylor-linearised using the composite PSU and `strata`, with the stratum assignment in section 1.3.

All headline numbers carry 95% confidence intervals. State estimates also report the unweighted number of enterprises and of PSUs behind them.

As a sensitivity, variance is re-estimated with zone × urban/rural (`zone` × `sector`, 12 cells) as strata.

## 8. Sector

ISIC codes (`s8q2b`) take 182 distinct values among enterprises (`audit_value_labels.csv`). They are grouped into eight sector groups based on ISIC Rev. 4 divisions, plus a category for enterprises with no code. Enterprises by group (`audit_sector_groups.csv`):

| Group | ISIC divisions or classes | All | Operating |
| --- | --- | --- | --- |
| Food retail | 4711, 4721–4723, 4781 | 847 | 820 |
| Food and beverage processing | 10–12 | 186 | 181 |
| Primary activities, mining, other manufacturing and utilities | 01–09, 13–39 | 451 | 440 |
| Construction | 41–43 | 121 | 121 |
| Other trade | 45–47, except the food retail classes | 964 | 930 |
| Transport and storage | 49–53 | 326 | 318 |
| Accommodation and food service | 55–56 | 233 | 228 |
| Personal and other services | 58–99 | 269 | 263 |
| No industry code | `s8q2b` blank | 39 | 37 |

Divisions 01–03 are included because some enterprises carry agricultural support or forestry codes in the 01 and 02 divisions. Every recorded code falls in a group.

The mapping is held in `sector_groups` in the configuration and applied by `taxcap.audit.sector_group`. Any change to the grouping after test results are seen is logged in section 15.

## 9. Local authority payments and registration

`s8q11b` is described in all outputs as "payments to government or non-government local authorities to allow operation". It is not described as tax, since the question does not identify the payee type, the amount or the legal basis. The question wording is recorded in `config/assumptions.yaml`:

> "Did your household make any payments to local authorities (government or non-government) to allow operation of [NON-FARM ENTERPRISE] in past 12 months?"

`s8q11` is official registration with the government. Recorded answers among all 3,436 enterprises:

- `s8q11b`: 1,096 yes and 2,340 no.
- `s8q11`: 443 yes and 2,993 no.

(`audit_value_labels.csv`)

## 10. Model target and features

### 10.1 Target

The model target is a binary indicator: the enterprise's annual income (section 3) is above ₦800,000. Income is in 2026 prices once the CPI adjustment in section 4 is sourced, and nominal until then. The target uses the primary population and income measure. The 49 enterprises excluded in section 3.3 are not modelled.

### 10.2 Allowed features

Features are limited to characteristics a tax authority could observe. The full list is in `features` in `config/assumptions.yaml`. For each feature it gives the source file, the variable and how the variable is coded. Variable names and labels follow the World Bank data dictionary for catalog 6410. The list was fixed on 15 October 2026, before any holdout split.

| Feature | File | Variable |
| --- | --- | --- |
| Sector group (section 8) | `sect8b_harvestw5` | `s8q2b` |
| Premises type | `sect8b_harvestw5` | `s8q10` |
| Registration | `sect8b_harvestw5` | `s8q11` |
| Non-household employees | `sect8b_harvestw5` | `s8q13a` + `s8q13b` |
| Years in operation | `sect8b_harvestw5` | `s8q4b` |
| Zone, state, urban/rural | `secta_harvestw5` | `zone`, `state`, `sector` |
| Any member with mobile phone access | `sect5b_plantingw5` | `s5bq8` |
| Any member with internet access | `sect5b_plantingw5` | `s5bq14` |
| Household internet connection | `sect9_harvestw5` | `s9q48` |
| Any member with a financial account | `sect5a1_plantingw5` | `s5aq2` |
| Any member with formal or semi-formal savings | `sect5a1_plantingw5` | `s5aq6` |
| Wall, roof and floor material | `sect9_harvestw5` | `s9q9`, `s9q10`, `s9q11` |
| Durable assets owned | `sect10_plantingw5` | `item_cd`, `s10q1a` |
| Household size | `sect1_harvestw5` | `s1q4`, `NEWMEMBER` |

Phone, internet, account, savings and durable asset features come from the post-planting visit (July to September 2023). This visit falls inside the income window. The other features come from the post-harvest visit.

A second feature set adds `s8q11b`, payments to government or non-government local authorities to allow operation. Both feature sets are reported, so the added predictive value of these payment records can be read directly.

### 10.3 Excluded features

The following are never used as features:

- Sales, profit and costs.
- Household consumption.
- Loan amounts.
- Durable asset values (`s10q6`).
- Any variable derived from the above.

Owner gender (`s1q2`) and owner age (`s1q6`) are never model features either. They are used only for the error-rate breakdowns in section 13.3.

## 11. Validation design

Before any model is fitted, 20% of PSUs are held out as the final test set (`model.holdout_share`). The draw is stratified by zone and uses the fixed seed 20261015 (`model.split_seed`). The test set is used once, for the final evaluation, and never for tuning or model selection.

Tuning uses 5-fold (`model.cv_folds`) `GroupKFold` with the composite PSU as the group, on the remaining 80% of PSUs. All enterprises in a PSU fall in the same fold, so no enumeration area contributes to both training and evaluation.

## 12. Models

Models are trained unweighted. All evaluation, in cross-validation and on the test set, is survey-weighted with `wt_cross_wave5`. As a sensitivity, models are also trained with `wt_cross_wave5` as `sample_weight` (`model.training_weight`).

The following are compared on the same test set:

- Rule baseline 1: registered enterprises (`s8q11` = yes) are flagged.
- Rule baseline 2: enterprises with any non-household employee are flagged.
- L2-penalised logistic regression.
- Histogram-based gradient boosting.

## 13. Metrics and interpretation

### 13.1 Test-set metrics

All metrics are survey-weighted and computed on the test set:

- Recall: the share of above-threshold enterprises that are flagged.
- Precision: the share of flagged enterprises that are above the threshold.
- False-flag rate: the share of below-threshold enterprises that are flagged.
- Area under the precision-recall curve.
- Calibration: predicted against observed share above the threshold, by decile of predicted probability.

### 13.2 Operating points

Two operating points are reported for each model (`model.operating_points`), with thresholds chosen on the cross-validation folds:

- False-flag rate at or below 10%.
- Precision at or above 50%.

### 13.3 Error rates by group

Error rates are also reported by zone, urban/rural location, owner gender and owner age group. The age bands are 15–24, 25–34, 35–44, 45–54 and 55 and over (`features.breakdown_only.owner_age.bands`). Owners who are under 15, have no recorded age or do not link to the roster are reported as a separate category. Owner gender and age come from the post-harvest household roster (`sect1_harvestw5`), linked through the first listed owner (`s8q6_1`). In the worker file, 129 of 3,558 filled owner slots have no matching row (`audit_worker_file.csv`), so the roster linkage rate is reported with the gender breakdown.

### 13.4 Interpretation

Feature importance is measured by permutation importance on the test set. SHAP values may be added later as a secondary method.

## 14. Limitations

Phone, internet, account, savings and durable asset features come from the post-planting visit (July to September 2023). This is about six months before the post-harvest visit that records income (February to May 2024; `audit_month_flags_by_interview.csv`). These characteristics change slowly, but the gap between the two visits is noted.

## 15. Changes and deviations

Any change to this plan made after test results are seen is logged here, with the date, the change and the reason.

The changes below were made before any income estimate or model result existed. They are recorded because they differ from the initial project setup (commit 164426d):

| Date | Change | Reason |
| --- | --- | --- |
| 2026-10-15 | Weight changed from `wt_wave5` to `wt_cross_wave5`. | The World Bank study description identifies `wt_cross_wave5` as the cross-sectional weight. It covers all operating enterprises, while `wt_wave5` is missing or non-positive for 22 (section 1.1). |
| 2026-10-15 | PSU changed from `ea` to `state` × `lga` × `ea`. | 91 `ea` codes repeat across states (section 1.2). |
| 2026-10-15 | Annualisation window changed from a fixed April 2023 to March 2024 window to the 12 months ending at the interview month. The fixed window is kept as a sensitivity. | No household flags months after its interview month, so the fixed window undercounts months for households interviewed before March 2024 (section 3.2). |
| 2026-10-15 | Window end capped at April 2024 (`s8q9__16`). Previously, May 2024 was counted as not operated for May interviews. | May 2024 has no flag column. Counting it as not operated limited the 85 May 2024 interviews to at most 11 months. |
| 2026-10-15 | Feature variables named from the World Bank data dictionary. Owner gender and age restricted to error-rate breakdowns. Training weights, holdout share, folds, seed, winsorisation percentile, threshold band, operating points and sector mapping entered in the configuration. | All fixed before any split or model fit. |

No deviations after test results have been recorded.
