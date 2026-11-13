# Lode

**Lode finds the companies most likely to buy, in a haystack of millions of public CNPJ records.**

> 🚧 Work in progress — see the [roadmap](#roadmap).

Sales teams that sell to other businesses usually pay for lead databases. Brazil publishes
much of that data for free: every registered company (Receita Federal), every public contract
(PNCP), every economic activity code (IBGE). Lode turns that raw data into a ranked list of
prospects: a map, filters, and the top 10 companies for each filter, scored by a model and
checked by an LLM.

The first version focuses on **software and IT services companies (CNAE 62) in São Paulo**.

## How it works (planned)

1. **ETL** — downloads the monthly Receita Federal open data, keeps the target sector and
   state, and loads it into Postgres. Public contracts come from the PNCP API.
2. **Scoring model** — learns what a "good prospect" looks like and scores every company.
   The public demo uses *won a public contract* as the target, measured on held-out data.
   Users can also upload their own customer list to find lookalikes.
3. **API** (FastAPI) — serves the map, filters and rankings. Scores are computed during the
   load, so the API stays light.
4. **LLM check** (Gemini, with Groq as fallback) — verifies a company's website and suggests
   an opening message, evaluated against a hand-labeled set.
5. **Web app** (Next.js) — the map and the prospect list.

## Roadmap

- [x] Project setup: sector definition, tests, CI
- [x] ETL: Receita Federal open data → Postgres
- [x] Public contracts (PNCP)
- [ ] Scoring model with held-out evaluation (logistic baseline done; gradient boosting next)
- [ ] API
- [ ] Web app: map, filters, top 10
- [ ] LLM website check + evaluation set
- [ ] Deploy (Supabase + Vercel)

## Data

Loaded from the Receita Federal open data of **October 2026** (7.8 GB of zipped CSVs, ~66 million
establishment rows), in about 3.5 minutes on a laptop, streaming straight from the zip files:

| | |
|---|---|
| Companies (CNAE 62 as main activity, active, São Paulo) | 133,729 |
| Establishments (headquarters + branches) | 134,551 |
| Database size | 75 MB |

Things the data taught us:

- **Almost no MEI.** Only 3 of 133k companies are MEI (individual micro-entrepreneurs). Not a bug:
  software development and IT consulting are not allowed activities for MEI under Brazilian
  law, so one-person IT businesses register as regular micro companies instead.
- **Privacy by design (LGPD).** Partner names and CPFs are never stored, only counts and age
  bands. Individual businesses carry the owner's CPF at the end of their legal name; the ETL
  strips it.
- **Main activity only.** About as many companies list IT only as a *secondary* activity. They
  are left out to keep the focus on companies whose core business is IT.

Run it:

```bash
cp .env.example .env                                  # point DATABASE_URL to your Postgres
uv run python -m lode.etl receita --download          # latest month: download, extract, load
uv run python -m lode.etl receita --month 2026-10     # files already in data/raw/2026-10
uv run python -m lode.etl pncp --start 2025-11-01 --end 2026-10-31 --download
```

The PNCP API only filters by publication date and is slow (~10 s per page of 500), so every
contract of each day is cached in `data/pncp/` as a gzipped JSON-lines file. Downloads resume
from the first missing day, and the cache can be filtered again if the target companies change.

Public contracts published from **November 2025 to October 2026** (365 days):

| | |
|---|---|
| Contracts published in the PNCP | 2,106,822 |
| Contracts won by our companies | 9,392 |
| Companies with at least one contract | 1,015 (0.8%) |
| Median contract value | R$ 25,680 |

Things the data taught us:

- **Few winners.** Less than 1% of the companies won a public contract in a year, so the model
  has to work with very imbalanced classes.
- **Very skewed values.** The median contract is about R$ 26 thousand, but the largest single one
  is above R$ 3.8 billion. Totals are meaningless here; medians and counts are not.
- **Mostly city halls.** Half of the contracts come from municipalities. The API also returns a
  buyer sphere `N` (620 contracts) that its documentation does not describe; it is kept as is.

## Model

The question: *looking at a company on 1 November 2025, will it win a public contract in the
next 12 months?* Features use only what was known on that date; the label is having a contract
published in the PNCP from November 2025 to October 2026. That leaves 109,041 companies opened
before the cutoff, of which 981 (0.9%) won.

20% of the companies are held out and scored once, at the end. The regularization of the
logistic regression is chosen by 5-fold cross-validation on the other 80%. Results on the
21,809 held-out companies:

| Ranking | PR-AUC | ROC-AUC | Precision in top 100 | Lift in top 10% |
|---|---|---|---|---|
| Random | 0.010 | 0.51 | 1% | 0.9× |
| Capital only | 0.117 | 0.89 | 20% | 7.1× |
| **Logistic regression** | **0.171** | **0.91** | **31%** | **7.7×** |

Accuracy is not reported on purpose: with 0.9% of winners, "nobody wins" is 99% accurate.
Classes are not reweighted either, so the score stays a real probability; reweighting would
barely change the ranking and would inflate every probability.

What the coefficients say: capital, company age and the number of secondary activities raise
the chance; micro companies and headquarters in the state capital lower it (half of the
contracts come from city halls, which seem to buy from companies outside the capital).

Things we learned the hard way:

- **A leak found through the coefficients.** A first version used a flag for "the whole partner
  list changed after the cutoff". It had a positive weight: winners change partners more often
  *after* winning. Nobody knew that on the cutoff date, so it was removed. The results barely
  moved (it affected 1,789 companies), but a model must not see the future.

Known limitations:

- Capital, size, legal nature, secondary activities and partner counts are today's values: the
  Receita publishes no history for them. A company that grew *because* it won contracts looks
  bigger than it was on the cutoff date.
- Only companies active in October 2026 are in the database, so companies that closed during
  the year are missing (survivorship bias).
- The holdout is a random split of the same year. A temporal check (train on one period, test
  on the next) needs more than one year of PNCP data.

Run it (prints the table above and saves the model to `models/`):

```bash
uv run python -m lode.model --cutoff 2025-11-01 --horizon-end 2026-11-01
```

## Development

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and a local Postgres.

```bash
uv sync                  # create the environment and install dependencies
uv run pytest            # run the tests
uv run ruff check .      # lint
```

## License

[MIT](LICENSE)
