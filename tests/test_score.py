import math
from datetime import date

import numpy as np
import pytest

from lode.model.pipeline import FEATURES, boosting, logistic, to_frame
from lode.model.score import cutoff_for, original_feature, score
from tests.test_features import (
    URL,
    company,
    conn,  # noqa: F401  (fixture)
    establishment,
    insert,
)
from tests.test_pipeline import row

pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


def toy_frame():
    rng = np.random.default_rng(2)
    capitals = rng.lognormal(9, 2, size=300)
    return to_frame([row(i, capital=f"{c:.2f}", won=c > 50000) for i, c in enumerate(capitals)])


def rich(cnpj_basico, capital):
    values = list(company(cnpj_basico))
    values[3] = capital
    return tuple(values)


def setup_companies(conn):  # noqa: F811
    conn.execute(
        "insert into load_info (month, companies, establishments, rows_read) "
        "values ('2026-10', 3, 3, '{}')"
    )
    insert(
        conn,
        [rich("11111111", 5_000_000), rich("22222222", 1_000), rich("33333333", 50_000)],
        [
            establishment("11111111", 1, date(2010, 1, 1)),
            establishment("22222222", 1, date(2010, 1, 1)),
            establishment("33333333", 1, date(2026, 6, 1)),  # opened this year: scored too
        ],
    )


def test_original_feature_maps_model_columns_back():
    assert original_feature("size_code_01") == "size_code"
    assert original_feature("legal_nature_infrequent_sklearn") == "legal_nature"
    assert original_feature("missingindicator_youngest_age_band") == "youngest_age_band"
    assert original_feature("capital") == "capital"
    with pytest.raises(ValueError):
        original_feature("won")


def test_cutoff_is_the_month_after_the_snapshot(conn):  # noqa: F811
    conn.execute("truncate load_info")
    conn.execute(
        "insert into load_info (month, companies, establishments, rows_read) "
        "values ('2026-12', 0, 0, '{}')"
    )
    assert cutoff_for(conn) == date(2027, 1, 1)


def test_score_ranks_companies_and_explains_the_logistic(conn):  # noqa: F811
    conn.execute("truncate load_info")
    setup_companies(conn)
    frame = toy_frame()
    model = logistic().fit(frame[FEATURES], frame["won"])
    result = score(conn, model, "abc123", {"pr_auc": 0.2})
    assert result["cutoff"] == date(2026, 11, 1) and result["companies"] == 3

    rows = conn.execute(
        "select cnpj_basico, score, rank, reasons from company_score order by rank"
    ).fetchall()
    assert [r[0] for r in rows] == ["11111111", "33333333", "22222222"]  # by capital
    assert rows[0][1] > rows[1][1] > rows[2][1]
    reasons = rows[0][3]
    assert set(reasons) == set(FEATURES)
    assert reasons["capital"] > 0  # more capital than the average company
    # reasons + the log-odds of the average company give back the company's log-odds
    logit = math.log(rows[0][1] / (1 - rows[0][1]))
    average = conn.execute("select avg(ln(score / (1 - score))) from company_score").fetchone()[0]
    assert sum(reasons.values()) == pytest.approx(logit - average, abs=0.01)

    places = conn.execute("select municipality_code from company_score").fetchall()
    assert places == [("7107",)] * 3

    info = conn.execute("select model_version, model, companies, metrics from score_info")
    assert info.fetchone() == ("abc123", "LogisticRegression", 3, {"pr_auc": 0.2})


def test_models_without_coefficients_have_no_reasons(conn):  # noqa: F811
    conn.execute("truncate load_info")
    setup_companies(conn)
    frame = toy_frame()
    score(conn, boosting().fit(frame[FEATURES], frame["won"]), "def456", {})
    assert conn.execute("select count(*) from company_score where reasons is null").fetchone() == (
        3,
    )
