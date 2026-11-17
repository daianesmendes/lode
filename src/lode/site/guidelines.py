"""The answers a website check gives, and the rules for each. The LLM prompt and the human
labeling tool show these same rules, so the evaluation measures the model, not a mismatch
between two definitions."""

COMPANY_SITE = {
    "yes": "The page is the company's own site, or the site of its corporate group "
    "(a multinational's global site counts).",
    "no": "The page belongs to someone else (an accounting firm, a hosting company, another "
    "business), or is a parked or for-sale domain.",
    "unclear": "The page is empty, broken or too generic to tell.",
}

PUBLIC_SECTOR = {
    "yes": "The page says the company sells to or serves the public sector: city halls, "
    "state or federal bodies, public tenders (licitações), government clients.",
    "no": "It is the company's site and nothing on it points to public-sector clients.",
    "unclear": "Not the company's site, or the page says too little to tell.",
}

WHAT_IT_DOES = (
    "One short sentence, in English, on what the company offers. Empty when the page is not "
    "the company's site."
)


def rules_text() -> str:
    lines = ["Is this the company's website?"]
    lines += [f"- {answer}: {rule}" for answer, rule in COMPANY_SITE.items()]
    lines += ["", "Does it sell to the public sector?"]
    lines += [f"- {answer}: {rule}" for answer, rule in PUBLIC_SECTOR.items()]
    lines += ["", f"What does it do? {WHAT_IT_DOES}"]
    return "\n".join(lines)
