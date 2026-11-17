"""Read-only HTTP API over the scored companies.

    uv run uvicorn lode.api.app:app --reload     # then open http://localhost:8000/docs

The API only reads Postgres: scores and their reasons are computed at load time by
``python -m lode.model score``, so the model file is never needed here.
"""

import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated

import psycopg
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel


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

    return app


app = create_app()
