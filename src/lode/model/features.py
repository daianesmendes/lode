"""One row per company, as the company looked on a cutoff date, plus the label.

The question the model answers: "looking at a company on the cutoff date, will it win a public
contract in the following months?". So every feature must be something we could have known on
that date, and the label comes only from contracts published after it. Mixing the two would let
the future leak into the features and make the model look better than it is.

The Receita snapshot is newer than the cutoff, so some fields can be rebuilt for the cutoff and
some cannot:

- rebuilt: company age, establishments open on the date and Simples membership (from its start
  date);
- ``partners_changed`` marks companies whose whole partner list joined after the date, so their
  partner counts describe a later company. It is a data-quality warning, not a model feature:
  it is itself a fact from after the cutoff;
- current values only (a known limitation): capital, size, legal nature, secondary activities,
  partner counts and age bands. The Receita publishes no history for them.

Companies that closed before the snapshot are not in the database at all (the ETL keeps only
active ones), which is another known limitation: survivorship bias.
"""

from datetime import date

import psycopg
from psycopg.rows import dict_row

SAO_PAULO_CITY = "7107"  # Receita municipality code of the state capital

QUERY = """
with firm as (
    select
        cnpj_basico,
        min(opened_on) as opened_on,
        count(*) filter (where opened_on < %(cutoff)s) as establishments,
        bool_or(is_headquarters and municipality_code = %(capital)s) as hq_in_capital,
        max(cardinality(cnaes_secondary)) as secondary_cnaes
    from establishment
    group by cnpj_basico
)
select
    c.cnpj_basico,
    (%(cutoff)s - f.opened_on) / 365.25 as age_years,
    f.establishments,
    f.hq_in_capital,
    f.secondary_cnaes,
    c.capital,
    c.size_code,
    c.legal_nature,
    coalesce(c.is_simples and c.simples_since < %(cutoff)s, false) as simples,
    coalesce(c.first_partner_since >= %(cutoff)s, false) as partners_changed,
    c.partners,
    c.partners_person,
    c.partners_company,
    c.partners_foreign,
    c.youngest_age_band,
    c.oldest_age_band{label}
from company c
join firm f using (cnpj_basico)
where f.opened_on < %(cutoff)s
order by c.cnpj_basico
"""

LABEL = """,
    exists (
        select 1 from public_contract p
        where p.cnpj_basico = c.cnpj_basico
          and p.published_at >= %(cutoff)s and p.published_at < %(horizon_end)s
    ) as won"""


def check_horizon(conn: psycopg.Connection, cutoff: date, horizon_end: date) -> None:
    """Fail if the loaded contracts do not cover the label window.

    Without this, a window longer than the PNCP load would silently label as "no contract" the
    companies whose contracts were simply never downloaded.
    """
    if cutoff >= horizon_end:
        raise ValueError(f"cutoff {cutoff} must be before the horizon end {horizon_end}")
    period = conn.execute("select period_start, period_end from pncp_info").fetchone()
    if period is None:
        raise ValueError("no public contracts loaded: run the pncp ETL first")
    start, end = period  # end is the last day loaded, inclusive
    if cutoff < start or horizon_end > date.fromordinal(end.toordinal() + 1):
        raise ValueError(
            f"contracts loaded for {start}..{end} do not cover the window {cutoff}..{horizon_end}"
        )


def build(conn: psycopg.Connection, cutoff: date, horizon_end: date | None) -> list[dict]:
    """Companies opened before `cutoff`, with `won` = a contract published in [cutoff, end).

    With `horizon_end=None` there is no label: that is how companies are scored today, when
    the future has not happened yet.
    """
    if horizon_end is not None:
        check_horizon(conn, cutoff, horizon_end)
    params = {"cutoff": cutoff, "horizon_end": horizon_end, "capital": SAO_PAULO_CITY}
    query = QUERY.format(label=LABEL if horizon_end is not None else "")
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(query, params).fetchall()
