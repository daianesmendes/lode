"""The hand-labeled evaluation set: a fixed sample of companies and a person's answers.

The sample is drawn once, with a fixed seed, and written before any labeling, so it cannot
drift towards easy cases. The first DEV companies are for working on the prompt; the rest
are the test set, looked at only for the final numbers (the same idea as the model holdout).
Labels are given blind: the labeling tool never shows the LLM's answers.
"""

import csv
import random
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from lode.site.candidates import Candidate

SIZE = 100
DEV = 30
SEED = 7
ANSWERS = {"y": "yes", "n": "no", "u": "unclear"}


@dataclass
class Label:
    cnpj_basico: str
    split: str  # "dev" or "test"
    rank: int
    domain: str
    shared_by: int
    is_company_site: str = ""  # yes / no / unclear; empty until labeled
    public_sector: str = ""
    note: str = ""

    @property
    def done(self) -> bool:
        return bool(self.is_company_site and self.public_sector)


def draw(found: list[Candidate], size: int = SIZE, dev: int = DEV, seed: int = SEED):
    """A random sample of the candidates, in a random order: the first `dev` are dev."""
    picked = random.Random(seed).sample(found, min(size, len(found)))
    return [
        Label(c.cnpj_basico, "dev" if i < dev else "test", c.rank, c.domain, c.shared_by)
        for i, c in enumerate(picked)
    ]


def read(path: Path) -> list[Label]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            Label(**{**row, "rank": int(row["rank"]), "shared_by": int(row["shared_by"])})
            for row in csv.DictReader(f)
        ]


def write(path: Path, labels: list[Label]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[f.name for f in fields(Label)])
        writer.writeheader()
        writer.writerows(asdict(label) for label in labels)
