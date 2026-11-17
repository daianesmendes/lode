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
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

SIZES = {"00": "not_informed", "01": "micro", "03": "small", "05": "other"}  # Receita codes
Size = Literal["not_informed", "micro", "small", "other"]

# Trade name and city were copied into company_score at scoring time (see lode.model.score).
COMPANIES = """
select s.rank, s.score, c.cnpj_basico, c.legal_name, s.trade_name as trade_name,
       s.municipality_code, mu.name as municipality, c.size_code
from company_score s
join company c using (cnpj_basico)
left join municipality mu on mu.code = s.municipality_code
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


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        url = database_url
        if url is None:
            load_dotenv()
            url = os.environ["DATABASE_URL"]
        with ConnectionPool(url, kwargs={"row_factory": dict_row}) as pool:
            app.state.pool = pool
            yield

    app = FastAPI(
        title="Lode",
        description="Brazilian software companies ranked by their chance of winning a public "
        "contract, from public data (Receita Federal + PNCP).",
        version="0.1.0",
        lifespan=lifespan,
    )

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

    return app


app = create_app()
