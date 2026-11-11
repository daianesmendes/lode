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
- [ ] Public contracts (PNCP)
- [ ] Scoring model with held-out evaluation
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
cp .env.example .env                              # point DATABASE_URL to your Postgres
uv run python -m lode.etl --download              # latest month: download, extract, load
uv run python -m lode.etl --month 2026-10         # files already in data/raw/2026-10
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
