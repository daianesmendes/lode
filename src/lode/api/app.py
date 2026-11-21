"""Read-only HTTP API over the scored companies.

    uv run uvicorn lode.api.app:app --reload     # then open http://localhost:8000/docs

The API only reads Postgres: scores and their reasons are computed at load time by
``python -m lode.model score``, so the model file is never needed here.
"""

import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated, Literal

import psycopg
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

SIZES = {"00": "not_informed", "01": "micro", "03": "small", "05": "other"}  # Receita codes
Size = Literal["not_informed", "micro", "small", "other"]

# Trade name and city were copied into company_score at scoring time (see lode.model.score).
COMPANIES = """
select s.rank, s.score, c.cnpj_basico, c.legal_name, s.trade_name as trade_name,
       s.municipality_code, coalesce(mi.name, mu.name) as municipality, c.size_code
from company_score s
join company c using (cnpj_basico)
left join municipality mu on mu.code = s.municipality_code
left join municipality_ibge mi on mi.code = s.municipality_code
"""


class Company(BaseModel):
    rank: int
    score: float  # probability of winning a public contract in the next 12 months
    cnpj_basico: str
    legal_name: str
    trade_name: str | None
    municipality_code: str
    municipality: str | None
    size: Size


class CompanyPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Company]


def company(row: dict) -> dict:
    return {**row, "size": SIZES.get(row.pop("size_code"), "not_informed")}


class Reason(BaseModel):
    feature: str
    contribution: float  # to the log-odds, compared with the average company


class Contracts(BaseModel):
    count: int
    total_value: float | None
    last_published: date | None


class Website(BaseModel):
    url: str | None  # the page that was read, after redirects
    domain: str  # from the e-mail the company registered
    verified: bool  # the LLM found it is the company's (or its group's) own site
    what_it_does: str | None  # only for verified sites
    # Only the quote, never a yes/no badge: on the test set a "sells to government" answer
    # was right 1 time in 4, so the person judges the evidence themselves.
    public_sector_evidence: str | None


class CompanyDetail(Company):
    opened_on: date | None
    capital: float
    legal_nature: str
    simples: bool
    partners: int
    establishments: int
    main_activity: str
    main_activity_name: str | None
    secondary_activities: int
    public_contracts: Contracts  # won in the loaded PNCP period
    reasons: list[Reason] | None  # largest effect first; none for non-linear models
    website: Website | None  # None when the site was not checked (outside the top companies)


DETAIL = """
select c.capital, c.legal_nature, c.is_simples as simples, c.partners,
       min(e.opened_on) as opened_on, count(e.*) as establishments,
       -- same establishment that stands for the company in the list
       (array_agg(e.cnae_main order by e.is_headquarters desc, e.opened_on nulls last))[1]
           as main_activity,
       max(cardinality(e.cnaes_secondary)) as secondary_activities,
       s.reasons
from company_score s
join company c using (cnpj_basico)
join establishment e using (cnpj_basico)
where s.cnpj_basico = %(cnpj)s
group by c.cnpj_basico, s.cnpj_basico
"""

WEBSITE = """
select url, domain, is_company_site = 'yes' as verified,
       case when is_company_site = 'yes' then nullif(what_it_does, '') end as what_it_does,
       case when is_company_site = 'yes' and public_sector = 'yes' then nullif(evidence, '') end
           as public_sector_evidence
from site_check where cnpj_basico = %(cnpj)s
"""

CONTRACTS = """
select count(*) as count, sum(value)::float as total_value,
       max(published_at)::date as last_published
from public_contract where cnpj_basico = %(cnpj)s
"""


class Municipality(BaseModel):
    municipality_code: str
    ibge_code: str | None  # joins the city to its outline on the map
    municipality: str | None
    companies: int
    mean_score: float
    # Sum of the probabilities: since scores are calibrated, an estimate of how many companies
    # of the city will win a public contract in the next 12 months.
    expected_winners: float
    best_cnpj_basico: str
    best_legal_name: str
    best_score: float


MUNICIPALITIES = """
select s.municipality_code, mi.ibge_code, coalesce(mi.name, mu.name) as municipality,
       count(*) as companies,
       avg(s.score) as mean_score, sum(s.score) as expected_winners,
       (array_agg(s.cnpj_basico order by s.rank))[1] as best_cnpj_basico,
       (array_agg(c.legal_name order by s.rank))[1] as best_legal_name,
       max(s.score) as best_score
from company_score s
join company c using (cnpj_basico)
left join municipality mu on mu.code = s.municipality_code
left join municipality_ibge mi on mi.code = s.municipality_code
{where}
group by s.municipality_code, mi.ibge_code, mi.name, mu.name
order by expected_winners desc
"""


class Health(BaseModel):
    status: str


class Evaluation(BaseModel):
    pr_auc: float
    pr_auc_interval: tuple[float, float]
    precision_at_100: float
    lift_at_10pct: float
    base_rate: float


class Meta(BaseModel):
    receita_month: str
    contracts_from: date
    contracts_to: date
    scored_at: datetime
    score_cutoff: date
    companies: int
    model: str
    model_version: str
    holdout: Evaluation  # how the model did on companies it never saw


def create_app(database_url: str | None = None, web_origins: list[str] | None = None) -> FastAPI:
    """`web_origins`: sites allowed to call the API from a browser (CORS). Defaults to the
    LODE_WEB_ORIGINS variable (comma-separated), else the local web app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        url = database_url
        if url is None:
            load_dotenv()
            url = os.environ["DATABASE_URL"]
        # Small pool: on Vercel each instance is short-lived and Supabase's free plan caps
        # connections. No prepared statements, so the pooler's transaction mode works too.
        kwargs = {"row_factory": dict_row, "prepare_threshold": None}
        with ConnectionPool(url, min_size=1, max_size=4, kwargs=kwargs) as pool:
            app.state.pool = pool
            yield

    app = FastAPI(
        title="Lode",
        description="Brazilian software companies ranked by their chance of winning a public "
        "contract, from public data (Receita Federal + PNCP).",
        version="0.1.0",
        lifespan=lifespan,
    )
    if web_origins is None:
        load_dotenv()
        web_origins = os.environ.get("LODE_WEB_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=web_origins, allow_methods=["GET"])

    @app.middleware("http")
    async def cache(request: Request, call_next):
        """The data only changes when it is reloaded (monthly), so a CDN in front of the API
        (Vercel's) may keep answers for a day instead of asking Postgres again."""
        response = await call_next(request)
        cacheable = request.method == "GET" and request.url.path != "/health"
        if cacheable and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=300, s-maxage=86400"
        return response

    def connection(request: Request) -> Iterator[psycopg.Connection]:
        with request.app.state.pool.connection() as conn:
            yield conn

    Conn = Annotated[psycopg.Connection, Depends(connection)]

    @app.get("/health", response_model=Health, tags=["meta"])
    def health(conn: Conn):
        conn.execute("select 1")
        return {"status": "ok"}

    @app.get("/meta", response_model=Meta, tags=["meta"])
    def meta(conn: Conn):
        """Where the data comes from, when it was scored, and how good the model is."""
        row = conn.execute(
            """
            select l.month as receita_month, p.period_start as contracts_from,
                   p.period_end as contracts_to, s.scored_at, s.cutoff as score_cutoff,
                   s.companies, s.model, s.model_version, s.metrics
            from load_info l, pncp_info p, score_info s
            """
        ).fetchone()
        if row is None:
            raise HTTPException(503, "data not loaded yet: run the ETL and the score command")
        metrics = row.pop("metrics")
        chosen = metrics["chosen"]
        holdout = metrics["holdout"][chosen]
        row["holdout"] = {
            **{k: holdout[k] for k in Evaluation.model_fields if k in holdout},
            "pr_auc_interval": metrics["holdout_pr_auc_interval"][chosen],
        }
        return row

    @app.get("/companies", response_model=CompanyPage, tags=["companies"])
    def companies(
        conn: Conn,
        municipality: Annotated[str | None, Query(description="Receita city code")] = None,
        size: Size | None = None,
        min_score: Annotated[float, Query(ge=0, le=1)] = 0,
        q: Annotated[str | None, Query(min_length=2, description="part of the name")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        """Companies from the highest score down, with optional filters. No contact data."""
        where, params = ["s.score >= %(min_score)s"], {"min_score": min_score}
        if municipality:
            where.append("s.municipality_code = %(municipality)s")
            params["municipality"] = municipality
        if size:
            where.append("c.size_code = %(size)s")
            params["size"] = next(code for code, name in SIZES.items() if name == size)
        if q:
            where.append(  # one search per table, so each can use its trigram index
                "s.cnpj_basico in (select cnpj_basico from company where legal_name ilike %(q)s"
                " union select cnpj_basico from company_score where trade_name ilike %(q)s)"
            )
            params["q"] = f"%{q}%"
        # Two queries: the page walks the rank index and stops after `limit` rows, while a
        # window count would force every matching row to be built first.
        filters = " where " + " and ".join(where)
        page = COMPANIES + filters + " order by s.rank limit %(limit)s offset %(offset)s"
        rows = conn.execute(page, {**params, "limit": limit, "offset": offset}).fetchall()
        count = f"select count(*) as total from ({COMPANIES}{filters}) matching"
        total = conn.execute(count, params).fetchone()["total"]
        items = [company(row) for row in rows]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    @app.get("/companies/{cnpj_basico}", response_model=CompanyDetail, tags=["companies"])
    def company_detail(
        conn: Conn,
        cnpj_basico: Annotated[str, Path(pattern=r"^\d{8}$", description="first 8 CNPJ digits")],
    ):
        """One company, its public contracts and why it got its score."""
        params = {"cnpj": cnpj_basico}
        row = conn.execute(COMPANIES + " where s.cnpj_basico = %(cnpj)s", params).fetchone()
        if row is None:
            raise HTTPException(404, "company not found")
        detail = conn.execute(DETAIL, params).fetchone()
        name = conn.execute(
            "select description from cnae where code = %s", (detail["main_activity"],)
        ).fetchone()
        reasons = detail.pop("reasons")
        return {
            **company(row),
            **detail,
            "main_activity_name": name["description"] if name else None,
            "public_contracts": conn.execute(CONTRACTS, params).fetchone(),
            "website": conn.execute(WEBSITE, params).fetchone(),
            "reasons": None
            if reasons is None
            else [
                {"feature": f, "contribution": v}
                for f, v in sorted(reasons.items(), key=lambda kv: -abs(kv[1]))
            ],
        }

    @app.get("/municipalities", response_model=list[Municipality], tags=["map"])
    def municipalities(conn: Conn, size: Size | None = None):
        """Companies and expected winners per city, for the map. Most expected winners first."""
        if size is None:
            return conn.execute(MUNICIPALITIES.format(where="")).fetchall()
        code = next(code for code, name in SIZES.items() if name == size)
        query = MUNICIPALITIES.format(where="where c.size_code = %(size)s")
        return conn.execute(query, {"size": code}).fetchall()

    return app


app = create_app()
