"""Which website might be a company's: the domain of the e-mail it registered.

The Receita has no website field, only an e-mail. Its domain is a candidate, but often a wrong
one: accounting firms register their own e-mail for their clients (contabilizei.com.br alone
appears in 36 thousand of our companies). Deciding whether a candidate really is the company's
site is the LLM's job; ``shared_by`` (how many companies use the domain) feeds the simple rule
it is compared with.
"""

import re
from dataclasses import dataclass

import psycopg

# Free e-mail providers: never a company's own site.
FREE_MAIL = {
    "gmail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br", "live.com",
    "msn.com", "yahoo.com", "yahoo.com.br", "icloud.com", "me.com", "uol.com.br", "bol.com.br",
    "terra.com.br", "ig.com.br", "globo.com", "globomail.com", "r7.com", "zipmail.com.br",
    "aol.com", "protonmail.com", "proton.me", "gmx.com", "yandex.com",
}  # fmt: skip
DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,}$")


@dataclass(frozen=True)
class Candidate:
    cnpj_basico: str
    rank: int
    legal_name: str
    trade_name: str | None
    municipality: str | None
    domain: str
    shared_by: int  # companies whose e-mail uses this domain


def usable(domain: str) -> bool:
    return bool(DOMAIN.match(domain)) and domain not in FREE_MAIL and "xxx" not in domain


QUERY = """
with mail as (
    select cnpj_basico, lower(split_part(email, '@', 2)) as domain,
           is_headquarters
    from establishment
    where email like '%%@%%.%%'
),
shared as (
    select domain, count(distinct cnpj_basico) as shared_by from mail group by domain
)
select distinct on (s.cnpj_basico)
       s.cnpj_basico, s.rank, c.legal_name, s.trade_name,
       coalesce(mi.name, mu.name) as municipality, m.domain, sh.shared_by
from company_score s
join company c using (cnpj_basico)
join mail m using (cnpj_basico)
join shared sh using (domain)
left join municipality mu on mu.code = s.municipality_code
left join municipality_ibge mi on mi.code = s.municipality_code
where s.rank <= %(top)s
order by s.cnpj_basico, m.is_headquarters desc, sh.shared_by
"""


def candidates(conn: psycopg.Connection, top: int) -> list[Candidate]:
    """One candidate domain per company among the `top` ranked ones (headquarters first)."""
    rows = conn.execute(QUERY, {"top": top}).fetchall()
    found = [Candidate(*row) for row in rows]
    return sorted((c for c in found if usable(c.domain)), key=lambda c: c.rank)
