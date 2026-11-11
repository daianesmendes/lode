"""Which companies Lode looks at: the market sector (CNAE codes) and the region.

CNAE is Brazil's official activity classification. The Receita Federal open data stores each
company's activity as a 7-digit code ("6201501"), while people write it as "6201-5/01".
"""

from dataclasses import dataclass


def normalize_cnae(code: str) -> str:
    """Turn a CNAE subclass into the 7-digit form used by the Receita files.

    >>> normalize_cnae("6201-5/01")
    '6201501'
    """
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) != 7:
        raise ValueError(f"CNAE subclass must have 7 digits, got {code!r}")
    return digits


@dataclass(frozen=True)
class Sector:
    name: str
    cnaes: dict[str, str]  # 7-digit code -> description
    states: tuple[str, ...]  # UFs included in the load

    def includes(self, cnae: str) -> bool:
        return normalize_cnae(cnae) in self.cnaes


# CNAE division 62: information technology services (IBGE / CONCLA).
SOFTWARE = Sector(
    name="Software and IT services",
    cnaes={
        normalize_cnae(code): description
        for code, description in {
            "6201-5/01": "Custom software development",
            "6201-5/02": "Web design",
            "6202-3/00": "Development and licensing of customizable software",
            "6203-1/00": "Development and licensing of non-customizable software",
            "6204-0/00": "IT consulting",
            "6209-1/00": "IT support, maintenance and other IT services",
        }.items()
    },
    # One state keeps the demo inside a free-tier database (~500 MB).
    states=("SP",),
)
