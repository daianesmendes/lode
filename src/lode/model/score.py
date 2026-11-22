"""Score every company as it is today and store the scores, with their reasons, in Postgres.

Training looked at companies on a past cutoff and checked what happened next. Scoring uses the
same features, built for today's cutoff (the month after the Receita snapshot), to estimate the
next 12 months. Companies opened in the last year, absent from training, are scored too.
"""

import hashlib
import json
from datetime import date

import numpy as np
import pandas as pd
import psycopg
from sklearn.pipeline import Pipeline

from lode.etl.load import SCHEMA
from lode.model.features import build
from lode.model.pipeline import CATEGORIES, FEATURES, to_frame

MAIN_ESTABLISHMENT = """
update company_score s
set trade_name = m.trade_name, municipality_code = m.municipality_code
from (
    select distinct on (cnpj_basico) cnpj_basico, trade_name, municipality_code
    from establishment
    order by cnpj_basico, is_headquarters desc, opened_on nulls last
) m
where m.cnpj_basico = s.cnpj_basico
"""

# Per city and size, so the map's size filter needs no per-company work either.
CITY_SCORES = """
truncate city_score;
insert into city_score
select s.municipality_code, c.size_code, count(*), sum(s.score),
       min(s.rank),
       (array_agg(s.cnpj_basico order by s.rank))[1],
       (array_agg(c.legal_name order by s.rank))[1],
       max(s.score)
from company_score s
join company c using (cnpj_basico)
group by s.municipality_code, c.size_code
"""


def cutoff_for(conn: psycopg.Connection) -> date:
    """First day after the month of the loaded Receita snapshot ("2026-10" -> 2026-11-01)."""
    row = conn.execute("select month from load_info").fetchone()
    if row is None:
        raise ValueError("no Receita load found: run the receita ETL first")
    year, month = map(int, row[0].split("-"))
    return date(year + month // 12, month % 12 + 1, 1)


def original_feature(column: str) -> str:
    """Model column -> the feature it comes from ("size_code_01" -> "size_code")."""
    column = column.removeprefix("missingindicator_")
    for name in CATEGORIES:
        if column.startswith(f"{name}_"):
            return name
    if column not in FEATURES:
        raise ValueError(f"unknown model column {column!r}")
    return column


def reasons(model: Pipeline, frame: pd.DataFrame) -> list[dict[str, float]] | None:
    """Contribution of each feature to each company's log-odds, compared with the average
    company: coefficient x (company value - average value), summed over a feature's columns.
    Only linear models have such an exact split; for others there are no reasons."""
    estimator = model[-1]
    if not hasattr(estimator, "coef_"):
        return None
    prep = model[:-1]
    x = prep.transform(frame[FEATURES])
    contributions = (x - x.mean(axis=0)) * estimator.coef_[0]
    columns = [original_feature(c.split("__", 1)[1]) for c in prep.get_feature_names_out()]
    grouped = pd.DataFrame(contributions, columns=columns).T.groupby(level=0).sum().T
    return [{k: round(float(v), 3) for k, v in row.items()} for _, row in grouped.iterrows()]


def model_version(model_bytes: bytes) -> str:
    return hashlib.sha256(model_bytes).hexdigest()[:12]


def score(
    conn: psycopg.Connection, model: Pipeline, version: str, metrics: dict
) -> dict[str, object]:
    cutoff = cutoff_for(conn)
    frame = to_frame(build(conn, cutoff, None))
    probabilities = model.predict_proba(frame[FEATURES])[:, 1]
    ranks = (-probabilities).argsort(kind="stable").argsort() + 1
    explained = reasons(model, frame) or [None] * len(frame)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(SCHEMA.read_text())
        cur.execute("truncate company_score, score_info")
        with cur.copy("copy company_score (cnpj_basico, score, rank, reasons) from stdin") as copy:
            for cnpj, p, rank, why in zip(
                frame.index, probabilities, ranks, explained, strict=True
            ):
                copy.write_row((cnpj, float(p), int(rank), json.dumps(why) if why else None))
        cur.execute(MAIN_ESTABLISHMENT)
        cur.execute(CITY_SCORES)
        cur.execute(
            "insert into score_info (cutoff, model_version, model, companies, metrics) "
            "values (%s, %s, %s, %s, %s)",
            (cutoff, version, type(model[-1]).__name__, len(frame), json.dumps(metrics)),
        )
    return {
        "cutoff": cutoff,
        "companies": len(frame),
        "mean_score": float(np.mean(probabilities)),
        "model_version": version,
    }
