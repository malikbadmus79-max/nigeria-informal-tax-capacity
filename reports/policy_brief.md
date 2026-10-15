# Who Can Pay? Informal Business Incomes and the ₦800,000 Threshold

Policy brief, October 2026. For the Federal Ministry of Finance, the Nigeria Revenue Service, the Joint Revenue Board, state internal revenue services and local government councils.

## Key messages

1. Between 19.9% and 43.8% of operating informal non-farm businesses earn more than ₦800,000 a year. The lower figure applies if incomes have not grown since 2023/24, the higher if incomes kept pace with inflation. Under both price assumptions, most informal businesses fall below the personal income tax exemption threshold.
2. Payments to government or non-government local authorities to allow operation are already common below the threshold: 28.3% of businesses at or below ₦800,000 make them if incomes have not grown since 2023/24, and 22.0% if incomes kept pace with inflation. These are businesses the Nigeria Tax Act 2025 exempts from personal income tax.
3. Characteristics a tax authority can observe identify businesses above the threshold better than registration status alone, but not precisely. At a false-flag rate held near 10%, a screening model finds 28.1% of businesses above the threshold, against 20.0% for a registration rule, and error rates differ by gender, location and zone.

## The problem

The Nigeria Tax Act 2025 exempts annual personal incomes of ₦800,000 or less from personal income tax, with rates rising from 7% to 25% above that level, and provides a presumptive tax for taxpayers who keep no records [T01]. The Minister of Finance has stated that the priority is more taxpayers rather than higher taxes [T02], and, as chairman of the Presidential Committee on Fiscal Policy and Tax Reforms, that over 90% of informal sector operators lack the capacity to pay tax [T04]. Multiple taxation and fragmented state tax administration have also been identified as burdens on businesses [T03].

Base-widening in the informal sector depends on three facts that are rarely measured: how many informal businesses earn above the threshold, whether they can be identified from information a tax authority holds, and what those below the threshold already pay at the local level.

## What the evidence shows

The analysis uses the Nigeria General Household Survey Panel, Wave 5 (2023/24), a nationally representative survey of about 5,000 households conducted by the National Bureau of Statistics with World Bank support [T05]. It covers 3,289 operating non-farm enterprises with complete information on months of operation. Annual income is monthly profit multiplied by months operated in the 12 months to the interview. Results are reported in nominal 2023/24 naira and in August 2026 prices, using a price ratio of 1.8777 built from published inflation rates [T08–T13].

![Figure 1](../outputs/figures/fig1_headline.png)

*Figure 1. Share of informal businesses with annual income above ₦800,000, with 95% confidence intervals and the range across eight sensitivity scenarios.*

The share above the threshold is 19.9% (95% CI 17.6% to 22.5%) if incomes have not grown since 2023/24, and 43.8% (95% CI 40.8% to 46.9%) if incomes kept pace with inflation. Across eight alternative assumptions about months operated, the population, the unit of analysis, the price index and the survey design, the share ranges from 17.8% to 21.9% on the first basis and from 41.7% to 47.7% on the second. The share is highest in the South South (31.8% to 53.1%) and lowest in the North East (13.0% to 28.3%).

![Figure 2](../outputs/figures/fig3_local_payments.png)

*Figure 2. Shares making payments to government or non-government local authorities to allow operation, and shares officially registered, above and below ₦800,000.*

Among businesses above the threshold, 56.7% make payments to government or non-government local authorities to allow operation if incomes have not grown since 2023/24, and 49.4% if incomes kept pace with inflation. Among those at or below the threshold, the shares are 28.3% and 22.0%. Official registration is less common: 25.5% and 20.9% above the threshold, and 10.6% and 7.9% at or below it, on the two price bases. Between 15.1% and 18.8% of businesses at or below the threshold make these payments without being officially registered. The survey records only whether a payment was made, not its amount, its legal basis or whether the authority was governmental.

![Figure 3](../outputs/figures/fig4_model_vs_rule.png)

*Figure 3. Recall, precision and false-flag rate on a held-out test set: registration rule compared with the screening model at two operating points.*

A logistic regression model using only characteristics a tax authority could observe (premises, registration, employees, years in operation, location, household assets, housing and household size) was selected on training data and then evaluated once on 665 enterprises from survey areas held out from the start. On that test set, at the operating point that keeps false flags near 10%, the model identifies 28.1% (95% interval 21.9% to 34.1%) of businesses above the threshold, with 73.3% of flagged businesses actually above it and a false-flag rate of 7.3%. The registration rule identifies 20.0% with a false-flag rate of 5.6%. The model's advantage in recall is 8.1 percentage points (95% interval 0.3 to 14.5). At an operating point set to find at least half of businesses above the threshold, the model identifies 52.8% but wrongly flags 13.9% of businesses below it.

![Figure 4](../outputs/figures/fig7_fairness.png)

*Figure 4. False-flag rate and recall by owner gender, urban or rural location and zone, with each group's share above the threshold.*

Errors are not evenly spread. On training data, false-flag rates are 7.0% for female-owned and 15.9% for male-owned businesses, 6.6% in rural and 14.5% in urban areas, and range across zones from 1.7% in the North East to 21.0% in the South South. These differences partly reflect differences in how many businesses in each group are above the threshold: 32.5% of female-owned and 58.7% of male-owned businesses. Several zone estimates rest on few businesses and are flagged as unreliable.

## Recommendations

(a) Target base-widening at the identifiable minority above the threshold, not at the informal sector as a whole. Lead: Nigeria Revenue Service, with the Federal Ministry of Finance. First step: set registration and outreach targets in terms of businesses above ₦800,000, and report progress against the 19.9% to 43.8% range rather than against the informal sector as a whole.

(b) Address payments to government or non-government local authorities to allow operation by operators the law exempts. Lead: Joint Revenue Board, with state internal revenue services and local government councils. First step: compile, state by state, the payments that local authorities require for business operation, with their legal basis, and identify those that fall on businesses below the federal threshold.

(c) Use screening on observable characteristics only as a first step, followed by verification and a right of appeal, and monitor error rates by gender, location and zone. Lead: Nigeria Revenue Service. First step: run a pilot in which flagged businesses are verified before any assessment, and publish recall, precision and false-flag rates by owner gender, urban or rural location and zone.

(d) Improve business income data. Lead: National Bureau of Statistics, with the Federal Ministry of Finance. First step: in the next survey round, record the amount and recipient of payments to local authorities and collect profit for more than one month of the year.

## What to avoid

The evidence supports treating the informal sector neither as uniformly unable to pay nor as uniformly able to pay. A model flag is not an assessment: the model identifies statistical patterns and does not establish what any individual owes. Federal collection should not be extended to businesses below the threshold that already make payments to local authorities to operate. Registration status alone finds fewer businesses above the threshold than the model does at a similar false-flag rate, so it is a weak basis for targeting.

## About this analysis

The estimates are survey-weighted, with uncertainty that accounts for the survey's clusters and strata. The analysis plan, including the modelling design, the operating points and the test set, was fixed before results were produced, and every change to it is logged with its date and reason. The test set was evaluated once. Profit is recalled for a single month; the threshold applies to a person's total income, while the survey records income by enterprise; and incomes in 2026 are not observed, which is why results are shown as a range between two price assumptions.

## Further reading

The full methods and results are in the accompanying working paper, *Who Can Pay? Taxable Capacity and Identification in Nigeria's Informal Sector* (reports/working_paper.md). Code, aggregate tables and the analysis plan are in the project repository.

Sources: [T01] The Guardian (Nigeria), Explainer: Who will pay under Nigeria's new tax laws, 2025. [T02] Pulse Nigeria, 26 June 2026. [T03] Veegil Media, 13 May 2026. [T04] Channels Television, 4 October 2025. [T05] World Bank Microdata Library, GHS-Panel Wave 5 study description. [T08]–[T13] National Bureau of Statistics inflation releases as reported by Channels Television, Arise News, Premium Times, Nairametrics, P.M. News and Tekedia. Full references in docs/sources.md.
