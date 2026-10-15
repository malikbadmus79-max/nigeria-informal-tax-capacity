# Who Can Pay? Informal Business Incomes and the ₦800,000 Threshold

This project measures how many of Nigeria's informal non-farm businesses earn above the personal income tax exemption threshold, how many already make payments to government or non-government local authorities to allow operation, and how accurately businesses above the threshold can be identified from characteristics a tax authority could observe.

Malik Badmus | October 2026

- Policy brief: [Markdown](reports/policy_brief.md) | [PDF](reports/policy_brief.pdf)
- Working paper: [Markdown](reports/working_paper.md) | [PDF](reports/working_paper.pdf)

## Key findings

- Between 19.9% and 43.8% of operating informal non-farm businesses earn more than ₦800,000 a year. The lower figure applies if incomes have not grown since 2023/24, the higher if incomes kept pace with inflation. Under both price assumptions, most informal businesses fall below the threshold.
- Payments to government or non-government local authorities to allow operation are already common below the threshold: 28.3% of businesses at or below ₦800,000 make them if incomes have not grown since 2023/24, and 22.0% if incomes kept pace with inflation. The Nigeria Tax Act 2025 exempts these businesses from personal income tax.
- On a held-out test set of 665 enterprises, a screening model using only observable characteristics identifies 28.1% of businesses above the threshold at a false-flag rate of 7.3%, against 20.0% at a false-flag rate of 5.6% for a rule that flags registered businesses.
- Error rates differ by owner gender, location and zone. On out-of-fold predictions on training data, false-flag rates are 7.0% for female-owned and 15.9% for male-owned businesses. These differences partly reflect how many businesses in each group are above the threshold: 32.5% of female-owned and 58.7% of male-owned businesses.

## Figures

![Share above ₦800,000: 19.9% if incomes have not grown since 2023/24 and 43.8% if incomes kept pace with inflation](outputs/figures/fig1_headline.png)

![Payments to government or non-government local authorities to allow operation: 56.7% of businesses above ₦800,000 and 28.3% of those at or below it, if incomes have not grown since 2023/24](outputs/figures/fig3_local_payments.png)

![Test set: the screening model identifies 28.1% of businesses above ₦800,000, the registration rule 20.0%](outputs/figures/fig4_model_vs_rule.png)

## Recommendations

- Target base-widening at the identifiable minority above the threshold, not at the informal sector as a whole (Nigeria Revenue Service, with the Federal Ministry of Finance).
- Address payments to government or non-government local authorities to allow operation by operators the law exempts, starting by compiling, state by state, the payments that local authorities require for business operation, with their legal basis (Joint Revenue Board, with state internal revenue services and local government councils).
- Use screening on observable characteristics only as a first step, followed by verification and a right of appeal, and monitor and publish error rates by gender, location and zone (Nigeria Revenue Service).
- Improve business income data, including the amount and recipient of payments to local authorities and profit for more than one month (National Bureau of Statistics, with the Federal Ministry of Finance).

## Methods

- Data and sample: Nigeria General Household Survey Panel, Wave 5 (2023/24), conducted by the National Bureau of Statistics with World Bank support; 3,289 operating non-farm enterprises with complete information on months of operation.
- Income measure and price adjustment: monthly profit multiplied by months operated in the 12 months to the interview, with negative profit set to zero; results in nominal 2023/24 naira and in August 2026 prices, using a price ratio of 1.8777 chained from published year-on-year inflation rates.
- Survey design and uncertainty: survey-weighted estimates with Taylor-linearised standard errors that account for primary sampling units and strata, 95% confidence intervals, and a reliability flag for small domains.
- Held-out test design: primary sampling units were held out as a test set before any model was fitted; models were tuned on grouped cross-validation folds of the training units, the selection and thresholds were frozen in config/model_selection.yaml, and the test set was evaluated once.
- Sensitivity analyses: seven alternative scenarios each change one assumption relative to the primary estimate: months operated, the population, the unit of analysis, the price index or the survey design.
- The analysis plan, fixed before results and with every change logged, is in [docs/analysis_plan.md](docs/analysis_plan.md); all sources are listed in [docs/sources.md](docs/sources.md).

## Data access

The General Household Survey Panel, Wave 5 microdata are not redistributed in this repository. To obtain them:

1. Register at the [World Bank Microdata Library](https://microdata.worldbank.org/catalog/6410) (catalog 6410).
2. Accept the terms of use for the study.
3. Download the CSV version of the data as a zip file.
4. Place the zip file, unextracted, in the data_raw folder as data_raw/NGA_2023_GHSP-W5_v02_M_CSV.zip. The loader in src/taxcap/load.py reads this path from data.zip_path in config/assumptions.yaml and reads each survey file directly from the zip.

## How to reproduce

Windows (PowerShell):

```
git clone https://github.com/malikbadmus79-max/nigeria-informal-tax-capacity.git
cd nigeria-informal-tax-capacity
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,reports]"
pytest -q
```

macOS and Linux:

```
git clone https://github.com/malikbadmus79-max/nigeria-informal-tax-capacity.git
cd nigeria-informal-tax-capacity
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,reports]"
pytest -q
```

The tests use synthetic data and pass without the survey files. With the zip file in place, the pipeline runs in this order:

```
python -m taxcap.audit
python -m taxcap.estimate
python -m taxcap.sensitivity
python -m taxcap.split
python -m taxcap.model
python -m taxcap.evaluate
python -m taxcap.fairness
python -m taxcap.charts
python -m taxcap.build_pdfs
python -m taxcap.check_reports
```

taxcap.split rebuilds the test split and checks the SHA-256 hash of the sorted test primary sampling units against the hash recorded in outputs/tables/split_summary.csv; it stops if they differ. taxcap.model refits the models with the frozen hyperparameters and stops if the hyperparameters or the preferred model would differ from config/model_selection.yaml. taxcap.evaluate refuses to run if config/model_selection.yaml differs from the last commit or if the test hash does not match. The test set was evaluated once; every step uses fixed seeds, so re-running the pipeline on the same data reproduces the committed tables.

## Repository structure

```
config/          assumptions (assumptions.yaml) and the frozen model selection (model_selection.yaml)
data_raw/        location for the survey zip file; not tracked by git
docs/            problem statement, analysis plan and sources
outputs/tables/  aggregate tables written by the pipeline
outputs/figures/ figures written by taxcap.charts
reports/         policy brief and working paper, in Markdown and PDF
src/taxcap/      pipeline code
tests/           tests on synthetic data
```

Fitted models are written to artifacts/, which is not tracked by git.

## Limitations

- Profit is recalled for a single month, the last month of operation, and may be under-reported or seasonal.
- The threshold applies to a person's total income, while the survey records income by enterprise; wages and other income are out of scope.
- Payments to government or non-government local authorities to allow operation are recorded as a yes or no answer, without amounts, payee type or legal basis.
- The survey dates from 2023/24 and is assessed against tax rules in force from 2026; incomes in 2026 are not observed, so results are given as a range between two price assumptions.
- The model identifies statistical patterns and does not establish what any person owes.

## Licence

Code is released under the MIT licence (see [LICENSE](LICENSE)). Reports, documentation, figures and derived aggregate tables are released under the Creative Commons Attribution 4.0 International licence (CC BY 4.0). The survey microdata remain subject to the World Bank Microdata Library terms of use.

## Contact

Malik Badmus, GitHub: [malikbadmus79-max](https://github.com/malikbadmus79-max)
