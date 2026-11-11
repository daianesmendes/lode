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
- [ ] ETL: Receita Federal open data → Postgres
- [ ] Public contracts (PNCP)
- [ ] Scoring model with held-out evaluation
- [ ] API
- [ ] Web app: map, filters, top 10
- [ ] LLM website check + evaluation set
- [ ] Deploy (Supabase + Vercel)

## Development

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and a local Postgres.

```bash
uv sync                  # create the environment and install dependencies
uv run pytest            # run the tests
uv run ruff check .      # lint
```

## License

[MIT](LICENSE)
