# Problem Statement: More Taxpayers, Not Higher Taxes? Measuring Taxable Capacity in Nigeria's Informal Sector

As of 10 October 2026

## 1. Context

Nigeria's four tax reform laws took effect on 1 January 2026. Under the Nigeria Tax Act, annual personal incomes of ₦800,000 or less are exempt from personal income tax, and rates above that level rise progressively from 7% to 25%. Small companies with turnover under ₦100 million and assets below ₦250 million are exempt from company income tax. Where a taxpayer keeps no records, a presumptive tax applies, at rates set by the Minister of Finance ([Guardian](https://guardian.ng/news/explainer-who-will-pay-under-nigerias-new-tax-laws/)).

The Minister of Finance, Taiwo Oyedele, has said that the government's priority is to widen the tax base rather than raise rates: "It is not about increasing taxes but making sure that those who are supposed to pay taxes" do so ([Pulse, 26 June 2026](https://www.pulse.ng/story/nigeria-needs-more-taxpayers-not-higher-taxes-says-finance-minister-taiwo-oyedele-2026062614344076206)). He has also said that Nigeria cannot continue to finance development primarily through borrowing ([Veegil Media, 13 May 2026](https://media.veegil.com/nigeria-cannot-depend-on-borrowing-for-development-oyedele/)).

Most Nigerian businesses operate informally. As chairman of the Presidential Committee on Fiscal Policy and Tax Reforms, Oyedele stated that over 90% of informal sector operators lack the capacity to pay tax ([Channels Television, 4 October 2025](https://www.channelstv.com/2025/10/04/over-90-informal-sector-operators-have-no-capacity-to-pay-tax-oyedele/)). He has also identified multiple taxation and fragmented state tax administration as burdens on businesses ([Veegil Media, 13 May 2026](https://media.veegil.com/nigeria-cannot-depend-on-borrowing-for-development-oyedele/)).

## 2. Problem

Widening the tax base depends on two things that are rarely measured: how many informal businesses earn enough to fall above the exemption threshold, and whether a tax authority could identify them from information it can observe. Without that evidence, base-widening efforts risk two errors. They may miss operators who can pay, or they may reach operators the law intends to exempt.

There is a related problem. Informal operators below the federal threshold may already pay levies to local governments. If so, the burden the reform intends to remove persists at the local level, and new federal collection would add to it.

## 3. Research question

What share of Nigeria's informal non-farm businesses earn above the personal income tax exemption threshold, where are they concentrated, and how accurately can they be identified from characteristics a tax authority can observe?

Hypothesis: a minority of informal operators earn above the threshold, consistent with the claim that most lack capacity to pay. However, formal registration is a poor guide to who can pay, and a substantial share of operators below the threshold already pay local levies.

## 4. Sub-questions

| # | Sub-question | Method | Output |
| --- | --- | --- | --- |
| 1 | What share of informal operators earn above ₦800,000 a year, and how does this vary by state, sector, urban or rural location, and gender of owner? | Weighted descriptive analysis of enterprise profit, annualised and adjusted to 2026 prices | National and state estimates with uncertainty |
| 2 | How many operators already pay local levies, and how does this compare with their income? | Cross-tabulation of local authority payments against income relative to the threshold | Estimate of levy payment below the threshold |
| 3 | How accurately can operators above the threshold be identified from observable characteristics? | Supervised classification (logistic regression baseline, gradient boosting), evaluated on held-out data | Recall, precision and false-flag rates; comparison with a registration-only rule |
| 4 | Which observable characteristics carry most of the predictive signal? | Model interpretation (feature importance, SHAP values) | Ranked list of indicators relevant to presumptive tax design |
| 5 | How sensitive are the results to the threshold, the price adjustment and the treatment of multi-owner businesses? | Sensitivity analysis | Range of estimates under alternative assumptions |

## 5. Data

The primary source is the Nigeria General Household Survey Panel, Wave 5 (2023–2024), conducted by the National Bureau of Statistics with World Bank support ([World Bank Microdata Library](https://microdata.worldbank.org/catalog/6410)). It is nationally representative, covering about 5,000 households. Fieldwork took place in July–September 2023 and January–March 2024.

The non-farm enterprise module records 3,436 enterprises, with monthly sales, profit and costs, months of operation, registration status, payments to local authorities, premises, industry and employees ([data dictionary](https://microdata.worldbank.org/index.php/catalog/6410/data-dictionary/F74)). Household files add phone and internet use, savings and banking, housing, durable assets and consumption.

Access requires registration and acceptance of the World Bank's terms of use. The raw data is not redistributed in this repository.

## 6. Preliminary check

A pilot check of the enterprise module found 3,338 enterprises currently operating. Annualising last month's profit by months operated over April 2023 to March 2024, and before any price adjustment:

- About 17% of operating enterprises earn above ₦800,000 a year (weighted by household survey weights).
- Of enterprises above that level, 57% report payments to local authorities and 26% are officially registered.
- Of enterprises below that level, 27% report payments to local authorities.

These figures are in 2023–2024 prices, treat each enterprise as one income, and have not been cleaned for outliers. They indicate feasibility only and are not findings.

## 7. Scope and limitations

Scope:

- Population: household-operated non-farm enterprises in Nigeria. Agriculture, formal companies and wage employees are excluded.
- Tax: personal income tax for individuals and sole traders. Company income tax and VAT are excluded.
- Period: survey data from 2023–2024, assessed against the tax rules in force from January 2026.

Limitations:

- Profit is recalled for a single month and may be under-reported or seasonal.
- The threshold applies to a person's total income, while the survey records income by enterprise. Results are tested under alternative allocation rules.
- Prices have risen since the survey. The Consumer Price Index was rebased in January 2025, so the price adjustment requires care and is reported as a sensitivity range.
- Payments to local authorities are recorded as a yes or no answer, without amounts or levy type.
- The model identifies statistical patterns. It does not establish what any individual owes.

## 8. Policy relevance and audience

Primary audience: the Federal Ministry of Finance and the Nigeria Revenue Service.

Secondary audiences: the Joint Revenue Board, state internal revenue services, local government councils, and associations representing informal traders and artisans.

Outputs: a working paper, a policy brief, state-level maps of taxable capacity and local levy incidence, and a public GitHub repository with code and derived tables.

## Sources

- [Guardian: Explainer: Who will pay under Nigeria's new tax laws](https://guardian.ng/news/explainer-who-will-pay-under-nigerias-new-tax-laws/)
- [Pulse: Nigeria needs more taxpayers, not higher taxes, says Finance Minister Taiwo Oyedele (26 Jun 2026)](https://www.pulse.ng/story/nigeria-needs-more-taxpayers-not-higher-taxes-says-finance-minister-taiwo-oyedele-2026062614344076206)
- [Veegil Media: Nigeria cannot depend on borrowing for development — Oyedele (13 May 2026)](https://media.veegil.com/nigeria-cannot-depend-on-borrowing-for-development-oyedele/)
- [Channels Television: Over 90% of informal sector operators lack capacity to pay tax — Oyedele (4 Oct 2025)](https://www.channelstv.com/2025/10/04/over-90-informal-sector-operators-have-no-capacity-to-pay-tax-oyedele/)
- [World Bank Microdata Library: Nigeria General Household Survey, Panel 2023–2024, Wave 5](https://microdata.worldbank.org/catalog/6410)
- [Data dictionary: Non-farm enterprises (sect8b_harvestw5)](https://microdata.worldbank.org/index.php/catalog/6410/data-dictionary/F74)
