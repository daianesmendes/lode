"""Compare the LLM's answers with the hand labels, and with a simple rule.

The rule is the baseline the LLM has to beat, the way "capital only" was for the scoring model:
a page that did not load is unclear, a domain shared by several companies is someone else's
(usually an accounting firm), anything else is the company's. For the public sector the rule
always says "no" on the company's own site, the most common answer.
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from lode.site.check import SYSTEM
from lode.site.labels import Label
from lode.site.page import Page

SHARED = 5  # a domain used by this many companies is not any one company's site


def rule(label: Label, page: Page) -> tuple[str, str]:
    """(is_company_site, public_sector) by the simple rule."""
    if page.url is None or not page.text:
        return "unclear", "unclear"
    if label.shared_by >= SHARED:
        return "no", "unclear"
    return "yes", "no"


def prompt_version() -> str:
    """Changes whenever the instructions change, so cached answers are never reused across
    two versions of the prompt."""
    return hashlib.sha256(SYSTEM.encode()).hexdigest()[:10]


def answers_dir(root: Path) -> Path:
    return root / prompt_version()


@dataclass
class Score:
    n: int
    accuracy: float
    yes_precision: float | None  # of the "yes" answers, how many were right
    yes_recall: float | None  # of the true "yes", how many were found


def score(truth: list[str], guess: list[str]) -> Score:
    pairs = list(zip(truth, guess, strict=True))
    said_yes = [t for t, g in pairs if g == "yes"]
    were_yes = [g for t, g in pairs if t == "yes"]
    return Score(
        n=len(pairs),
        accuracy=sum(t == g for t, g in pairs) / len(pairs),
        yes_precision=said_yes.count("yes") / len(said_yes) if said_yes else None,
        yes_recall=were_yes.count("yes") / len(were_yes) if were_yes else None,
    )


def confusion(truth: list[str], guess: list[str]) -> Counter:
    return Counter(zip(truth, guess, strict=True))


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))
