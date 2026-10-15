# Analysis Plan

As of 15 October 2026. Drafted after the data audit and before any income estimate, model fit or test-set evaluation.

This plan fixes the analytical decisions for the research question in [problem_statement.md](problem_statement.md). Parameter values named here are held in [config/assumptions.yaml](../config/assumptions.yaml), and code reads them from there. Audit counts are unweighted and come from the tables in `outputs/tables/audit_*.csv`, produced by `python -m taxcap.audit`. No result beyond those counts is reported here.

## 1. Data and survey design

Source: Nigeria General Household Survey Panel, Wave 5, post-harvest visit (T05, T06). Sources cited by ID (T01, T02, and so on) are listed in [sources.md](sources.md). Files: `sect8b_harvestw5` (enterprises), `sect8c_harvestw5` (enterprise workers) and `secta_harvestw5` (cover page), read through `src/taxcap/load.py`.

The enterprise file holds 3,436 enterprises in 2,673 households. Every enterprise links to a household in the cover file (`audit_survey_design.csv`).

### 1.1 Weight

Estimates use the cross-sectional household weight `wt_cross_wave5`, as the World Bank study description recommends for cross-sectional estimates (T05). Each enterprise carries the weight of its household.

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

Months operated come from the `s8q9` flags. The questionnaire asks: "In which months did you operate this [NON-FARM ENTERPRISE] in the past 12 months?" (T07)

The month of each flag is set by `month_flag_origin` in the configuration, with `s8q9__1` as January 2023. Printed codes run from JANUARY 2023 = 01 to FEBRUARY 2024 = 14.

The data also hold flags `s8q9__0`, `s8q9__15` and `s8q9__16`, which are not printed in the questionnaire. Flags 15 and 16 are assumed to continue the sequence as March 2024 and April 2024. This is an assumption. The World Bank data dictionary for the file (catalog 6410, F74; T06) gives the same labels, MARCH 2024 and APRIL 2024.

The data dictionary labels `s8q9__0` "ALL 12 MONTHS" (T06). No operating enterprise flags it, so it does not enter the count.

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

### 4.1 Method

Income is adjusted from August 2023 prices to August 2026 prices by chaining three National Bureau of Statistics (NBS) headline year-on-year inflation rates:

cpi_ratio = (1 + rate for August 2024) × (1 + rate for August 2025) × (1 + rate for August 2026)

Each rate is the change in the headline index over the 12 months to that August. The product is therefore the change in the price level from August 2023 to August 2026.

The Consumer Price Index was rebased in January 2025. Chaining published year-on-year rates avoids linking index levels from the old and new bases.

The reference month is August 2023. It is the midpoint of the 12-month income window for most enterprises: 2,880 of 3,338 operating enterprises were interviewed in February 2024, with a window from March 2023 to February 2024 (`audit_month_flags_by_interview.csv`). The target month is August 2026, the latest release as of 15 October 2026.

One national ratio is applied to all enterprises. It does not vary by state, urban or rural location, or interview month. For the 458 enterprises interviewed in March to May 2024, the midpoint of the window falls one to two months after August 2023.

Adjusted income is nominal income multiplied by the ratio. Equivalently, the ₦800,000 threshold corresponds to ₦426,053 in August 2023 prices.

### 4.2 Rates

| Rate | Value | Sources |
| --- | --- | --- |
| August 2024 | 32.15% | T08, T09 |
| August 2025 | 23.14% | T10, T11, T12; revision documented in T13 |
| August 2026 | 15.39% | T10, T11, T12 |
| cpi_ratio | 1.8777 | Computed: 1.3215 × 1.2314 × 1.1539 |

The rates and the ratio are held in `price_adjustment` in the configuration.

August 2025 has two published values. The NBS first published 20.12% in September 2025 (T15, T16). In December 2025, the NBS changed the CPI reference period to the 2024 average and revised its January to November 2025 year-on-year rates. This revision raised August 2025 to 23.14% (T13, T14). The August 2026 release compares with 23.14% (T10, T11, T12), and this revised value is used.

As a sensitivity, the originally published 20.12% is used instead, which gives a ratio of 1.8317 (`price_adjustment.sensitivities`).

A second sensitivity moves the reference month to September 2023, chaining the September 2024, 2025 and 2026 rates. It is pending: the September 2026 rate had not been released as of 15 October 2026.

### 4.3 Interpretation

Nominal results assume no growth in nominal income since the survey. They are a lower bound.

CPI-adjusted results assume that real incomes have held constant since the survey. They are an upper bound under that assumption.

Every headline share is reported as a range from the nominal to the CPI-adjusted value.

## 5. Threshold and unit of analysis

### 5.1 Threshold

The threshold is annual income above ₦800,000, the personal income tax exemption level under the Nigeria Tax Act 2025 (T01; `tax_rules.pit_exemption_naira`).

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

### 7.1 Variance

Shares, means and totals are survey-weighted. Standard errors are Taylor-linearised using the composite PSU and `strata`, with the stratum assignment in section 1.3. Variance uses the stratified with-replacement approximation at PSU level.

Domain estimates keep every PSU in the design in the variance calculation, including PSUs with no enterprise in the domain. The design PSUs are those of households in the cover file with a positive weight.

### 7.2 Confidence intervals

All headline numbers carry 95% confidence intervals from the t distribution, with degrees of freedom equal to the number of design PSUs minus the number of strata.

Proportions use logit-transformed intervals, as in the default of `svyciprop` in the R survey package: expit(logit(p) ± t × SE / (p(1 − p))). The interval is reported as not estimable when p is 0 or 1. Standard errors are unchanged by the transformation.

Means use symmetric t intervals. Medians use Woodruff intervals.

Every domain estimate also reports the unweighted number of enterprises and of PSUs behind it.

### 7.3 Reliability

A domain estimate is flagged "unreliable" if any of the following holds:

- It rests on fewer than 50 enterprises.
- It rests on fewer than 10 PSUs.
- Its relative standard error exceeds 30%.

Flagged estimates are still reported, never dropped (`estimation.reliability`).

### 7.4 Representativeness

The survey is designed to be representative nationally and by geopolitical zone (T05). The study description does not state representativeness by urban/rural location or by state. Its only state-level reference is the calibration of the cross-sectional weights to state populations of males and females.

State estimates are therefore labelled "indicative" in a separate column of every state-level table, whatever their reliability flag.

Urban/rural is not a stated design domain either: T05 states representativeness nationally and by zone only. Urban and rural estimates are reported without the "indicative" label and with their normal standard errors.

### 7.5 Sensitivity

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

`s8q11b` is described in all outputs as "payments to government or non-government local authorities to allow operation". It is not described as tax, since the question does not identify the payee type, the amount or the legal basis. The question wording (T07) is recorded in `config/assumptions.yaml`:

> "Did your household make any payments to local authorities (government or non-government) to allow operation of [NON-FARM ENTERPRISE] in past 12 months?"

`s8q11` is official registration with the government. Recorded answers among all 3,436 enterprises:

- `s8q11b`: 1,096 yes and 2,340 no.
- `s8q11`: 443 yes and 2,993 no.

(`audit_value_labels.csv`)

## 10. Model target and features

### 10.1 Target

The model target is a binary indicator: the enterprise's annual income (section 3) is above ₦800,000. Income is in August 2026 prices (section 4). The target uses the primary population and income measure. The 49 enterprises excluded in section 3.3 are not modelled.

### 10.2 Allowed features

Features are limited to characteristics a tax authority could observe. The full list is in `features` in `config/assumptions.yaml`. For each feature it gives the source file, the variable and how the variable is coded. Variable names and labels follow the World Bank data dictionary for catalog 6410 (T06). The list was fixed on 15 October 2026, before any holdout split.

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

Rare-category mapping for premises and housing materials is fitted on training rows only (`features.rare_category`). A code held by fewer than 1% of non-missing training rows, or not seen in training, maps to 96 (other), and the same mapping is applied to test rows.

A household with no row in a household-level source file gets missing values, not 0 or "no".

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

Tuning uses 5-fold (`model.cv_folds`) `StratifiedGroupKFold` on the remaining 80% of PSUs. The composite PSU is the group, and folds are stratified on the CPI-adjusted target of training rows. Folds are shuffled with `random_state` equal to `model.split_seed`.

All enterprises in a PSU fall in the same fold, so no enumeration area contributes to both training and evaluation. Test-row targets are never read in forming the folds.

No PSU code or row assignment is saved. `outputs/tables/split_summary.csv` records the counts, the weighted training-set and per-fold target shares, and a SHA-256 hash of the sorted test PSU list.

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
| 2026-10-15 | Price adjustment set: chained NBS headline year-on-year rates for August 2024, 2025 and 2026, cpi_ratio 1.8777 from August 2023 to August 2026 prices. The revised August 2025 rate is used, with the originally published rate as a sensitivity. Results reported as a range from nominal to CPI-adjusted. Replaces the open item in section 4. | Made before any income estimate. Chaining year-on-year rates avoids linking index levels across the January 2025 rebase (section 4). |
| 2026-10-15 | Reliability rule added: a domain estimate is flagged "unreliable" if it rests on fewer than 50 enterprises or fewer than 10 PSUs, or its relative standard error exceeds 30%. Flagged estimates are reported, not dropped. Confidence intervals use the t distribution with degrees of freedom equal to design PSUs minus strata. | Set before any estimate was computed (section 7). |
| 2026-10-15 | Proportion confidence intervals changed from symmetric t intervals to logit-transformed intervals; not estimable when p is 0 or 1 (section 7.2). | Changed after the first estimates, because symmetric intervals gave negative lower bounds for small domains. Point estimates and standard errors are unaffected. |
| 2026-10-15 | State estimates labelled "indicative" in a new column, whatever the reliability flag (section 7.4). | Changed after the first estimates. The survey is designed to be representative nationally and by zone, not by state (T05). Point estimates, standard errors and reliability flags are unaffected. |
| 2026-10-15 | Rare-category frequencies computed on training rows only; codes unseen in training map to 96 (other) (section 10.2). Previously computed on the whole analysis sample. | Pre-modelling change, before any model fit. Keeps test-row information out of feature construction. |
| 2026-10-15 | Cross-validation folds changed from unshuffled `GroupKFold` to `StratifiedGroupKFold` (shuffled, `random_state` = `model.split_seed`), grouped by PSU and stratified on the CPI-adjusted target of training rows (section 11). The test draw is unchanged. | Pre-modelling change, before any model fit. Balances the target share across folds, and makes fold assignment depend on the seed. |

No deviations after test results have been recorded.
