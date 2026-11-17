"""Website check commands.

uv run python -m lode.site label     # label the evaluation sample by hand (resumable)
"""

import argparse
import os
import textwrap
import webbrowser
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from lode.site import labels as L
from lode.site.candidates import Candidate, candidates
from lode.site.guidelines import rules_text
from lode.site.page import cached, client

TOP = 2000
CACHE = Path("data/sites")
LABELS = Path("evals/site_labels.csv")


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
                site = ask_answer("Is this the company's website?", page.url)
                if site is None:
                    continue
                public = ask_answer("Does it sell to the public sector?", page.url)
                if public is None:
                    continue
                label.is_company_site, label.public_sector = site, public
                label.note = input("Note (optional, Enter to skip): ").strip()
                L.write(args.labels, sample)  # saved after every company
        except (KeyboardInterrupt, EOFError):
            print("\nstopped; progress is saved")
    print(f"{sum(x.done for x in sample)} of {len(sample)} labeled")


def main() -> None:
    parser = argparse.ArgumentParser(prog="lode.site", description="Website check with an LLM.")
    sub = parser.add_subparsers(dest="command", required=True)
    label = sub.add_parser("label", help="label the evaluation sample by hand")
    label.add_argument("--labels", type=Path, default=LABELS)
    label.set_defaults(run=run_label)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
