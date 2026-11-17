"""Website check commands.

uv run python -m lode.site label     # label the evaluation sample by hand (resumable)
uv run python -m lode.site eval      # LLM vs hand labels vs a simple rule, on the dev split
"""

import argparse
import json
import os
import textwrap
import time
import webbrowser
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv

from lode.site import evaluate as E
from lode.site import labels as L
from lode.site.candidates import Candidate, candidates
from lode.site.check import check
from lode.site.guidelines import rules_text
from lode.site.llm import endpoints_from_env
from lode.site.page import cached, client

TOP = 2000
CACHE = Path("data/sites")
LABELS = Path("evals/site_labels.csv")
ANSWERS = Path("data/site_answers")


def connect() -> psycopg.Connection:
    load_dotenv()
    return psycopg.connect(os.environ["DATABASE_URL"])


def ask_answer(question: str, url: str | None) -> str | None:
    """y / n / u, or None to skip; 'o' opens the page, 'q' quits."""
    while True:
        reply = input(f"{question} [y/n/u, o=open, s=skip, q=quit] ").strip().lower()
        if reply in L.ANSWERS:
            return L.ANSWERS[reply]
        if reply == "o" and url:
            webbrowser.open(url)
            print(f"  opened {url} in your browser; look at it, then answer here")
        elif reply == "s":
            return None
        elif reply == "q":
            raise KeyboardInterrupt
        else:
            print("  answer with the letter y, n or u (o opens the page)")


def run_label(args: argparse.Namespace) -> None:
    with connect() as conn:
        found = {c.cnpj_basico: c for c in candidates(conn, TOP)}
    if not args.labels.exists():
        L.write(args.labels, L.draw(list(found.values())))
        print(f"new sample of {L.SIZE} companies written to {args.labels}")
    sample = L.read(args.labels)
    todo = [label for label in sample if not label.done]
    print(f"{len(sample) - len(todo)} of {len(sample)} labeled. Rules:\n\n{rules_text()}\n")
    with client() as http:
        try:
            for label in todo:
                company: Candidate = found[label.cnpj_basico]
                page = cached(CACHE, http, label.domain)
                done = sum(x.done for x in sample)
                print("=" * 100)
                print(f"[{done + 1}/{len(sample)}] {company.legal_name}")
                print(f"  trade name: {company.trade_name or '-'} · {company.municipality}")
                print(f"  e-mail domain: {label.domain} · page: {page.url or page.error}")
                print(f"  title: {page.title or '-'}")
                print(textwrap.fill(page.text[:1500] or "(no text)", 100, initial_indent="  "))
                # the page text can push the name off screen: repeat it next to the questions
                print(f"\n>>> {company.legal_name} · {label.domain}")
                # when nothing answered the robot, still let the person try it in a browser
                url = page.url or f"https://{label.domain}"
                site = ask_answer("Is this the company's website?", url)
                if site is None:
                    continue
                public = ask_answer("Does it sell to the public sector?", url)
                if public is None:
                    continue
                label.is_company_site, label.public_sector = site, public
                label.note = input("Note (optional, Enter to skip): ").strip()
                L.write(args.labels, sample)  # saved after every company
        except (KeyboardInterrupt, EOFError):
            print("\nstopped; progress is saved")
    print(f"{sum(x.done for x in sample)} of {len(sample)} labeled")


def llm_answer(api, chain, company: Candidate, page) -> dict:
    """The LLM's answer for one company, cached per prompt version."""
    path = E.answers_dir(ANSWERS) / f"{company.cnpj_basico}.json"
    if path.exists():
        return json.loads(path.read_text())
    answer = check(api, chain, company, page, log=lambda m: print(f"    {m}"))
    data = {
        **answer.value.model_dump(),
        "model": answer.model,
        "seconds": round(answer.seconds, 2),
        "input_tokens": answer.input_tokens,
        "output_tokens": answer.output_tokens,
    }
    E.save(path, data)
    time.sleep(1)  # stay well under the free tiers' requests per minute
    return data


def pct(value: float | None) -> str:
    return "  -  " if value is None else f"{value:5.0%}"


def run_eval(args: argparse.Namespace) -> None:
    load_dotenv()
    labels = [x for x in L.read(args.labels) if x.split == args.split and x.done]
    if args.split == "test" and len(labels) < L.SIZE - L.DEV:
        raise SystemExit(f"only {len(labels)} test companies labeled: finish labeling first")
    with connect() as conn:
        found = {c.cnpj_basico: c for c in candidates(conn, TOP)}
    chain = endpoints_from_env()
    rows = []
    with client() as http, httpx.Client(timeout=90) as api:
        for x in labels:
            page = cached(CACHE, http, x.domain)
            rows.append(
                (x, page, E.rule(x, page), llm_answer(api, chain, found[x.cnpj_basico], page))
            )
    print(f"\n{args.split}: {len(rows)} labeled companies, prompt version {E.prompt_version()}")
    print(f"pages with no text (blocked or down): {sum(not p.text for _, p, _, _ in rows)}\n")
    for i, question in enumerate(("is_company_site", "public_sector")):
        truth = [getattr(x, question) for x, _, _, _ in rows]
        print(f"{question:<16}{'accuracy':>9}{'yes precision':>15}{'yes recall':>12}")
        for name, guess in (
            ("rule", [r[i] for _, _, r, _ in rows]),
            ("LLM", [a[question] for _, _, _, a in rows]),
        ):
            s = E.score(truth, guess)
            print(
                f"  {name:<14}{pct(s.accuracy):>9}{pct(s.yes_precision):>15}{pct(s.yes_recall):>12}"
            )
        print()
    if args.split == "dev":  # the test split is never inspected case by case
        print("disagreements (label -> LLM):")
        for x, _, _, a in rows:
            if (x.is_company_site, x.public_sector) != (a["is_company_site"], a["public_sector"]):
                print(
                    f"- {found[x.cnpj_basico].legal_name[:45]} · {x.domain} · shared {x.shared_by}"
                )
                print(
                    f"    site {x.is_company_site} -> {a['is_company_site']}, "
                    f"public {x.public_sector} -> {a['public_sector']} · note: {x.note or '-'}"
                )
                print(f"    LLM evidence: {a['evidence'][:140]!r}")
    used = [a for _, _, _, a in rows if a["model"] != "none"]
    if used:
        tokens = sum((a["input_tokens"] or 0) + (a["output_tokens"] or 0) for a in used)
        seconds = sum(a["seconds"] for a in used) / len(used)
        print(
            f"\nLLM calls: {len(used)} · {tokens / len(used):,.0f} tokens and {seconds:.1f} s each"
        )


def main() -> None:
    parser = argparse.ArgumentParser(prog="lode.site", description="Website check with an LLM.")
    sub = parser.add_subparsers(dest="command", required=True)
    label = sub.add_parser("label", help="label the evaluation sample by hand")
    label.add_argument("--labels", type=Path, default=LABELS)
    label.set_defaults(run=run_label)
    evaluation = sub.add_parser("eval", help="compare the LLM with the hand labels")
    evaluation.add_argument("--split", choices=["dev", "test"], default="dev")
    evaluation.add_argument("--labels", type=Path, default=LABELS)
    evaluation.set_defaults(run=run_eval)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
