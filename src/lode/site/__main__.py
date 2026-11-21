"""Website check commands.

uv run python -m lode.site label     # label the evaluation sample by hand (resumable)
uv run python -m lode.site eval      # LLM vs hand labels vs a simple rule, on the dev split
uv run python -m lode.site run       # check the top companies' sites and store the answers
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

from lode.etl.load import SCHEMA
from lode.site import evaluate as E
from lode.site import labels as L
from lode.site.candidates import Candidate, candidates
from lode.site.check import check
from lode.site.guidelines import rules_text
from lode.site.llm import NoModelAnswered, endpoints_from_env
from lode.site.page import cached, client, readable

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
                if site == "yes":
                    public = ask_answer("Does it sell to the public sector?", url)
                    if public is None:
                        continue
                else:  # the rule: not its site (or can't tell) means public is unclear
                    public = "unclear"
                    print("  public sector: unclear (not the company's site)")
                label.is_company_site, label.public_sector = site, public
                label.note = input("Note (optional, Enter to skip): ").strip()
                L.write(args.labels, sample)  # saved after every company
        except (KeyboardInterrupt, EOFError):
            print("\nstopped; progress is saved")
    print(f"{sum(x.done for x in sample)} of {len(sample)} labeled")


def llm_answer(api, chain, company: Candidate, page, model: str | None = None) -> dict:
    """The LLM's answer for one company, cached per prompt version (and model, if fixed)."""
    path = E.answers_dir(ANSWERS, model) / f"{company.cnpj_basico}.json"
    if path.exists():
        return json.loads(path.read_text())
    for wait in (0, 20, 60, 120):  # one model alone has no fallback: wait out rate limits
        time.sleep(wait)
        try:
            answer = check(api, chain, company, page, log=lambda m: print(f"    {m}"))
            break
        except NoModelAnswered:
            if len(chain) > 1 or wait == 120:
                raise
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
    if args.model:  # one model on its own, no fallback: compare models on the same cases
        chain = [e for e in chain if e.model == args.model]
        if not chain:
            raise SystemExit(f"{args.model} is not in LLM_MODELS or LLM_FALLBACK_MODELS")
    rows = []
    with client() as http, httpx.Client(timeout=30) as api:
        for x in labels:
            page = cached(CACHE, http, x.domain)
            rows.append(
                (
                    x,
                    page,
                    E.rule(x, page),
                    llm_answer(api, chain, found[x.cnpj_basico], page, args.model),
                )
            )
    ok = [row for row in rows if readable(row[1])]
    print(f"\n{args.split}: {len(rows)} labeled companies, prompt version {E.prompt_version()}")
    print(f"model: {args.model or 'the whole fallback chain'}")
    print(f"unreadable pages (down, empty or a bot wall): {len(rows) - len(ok)}")
    for title, subset in (("all companies", rows), ("readable pages only", ok)):
        print(f"\n== {title} ({len(subset)})")
        for i, question in enumerate(("is_company_site", "public_sector")):
            truth = [getattr(x, question) for x, _, _, _ in subset]
            print(f"{question:<16}{'accuracy':>9}{'yes precision':>15}{'yes recall':>12}")
            for name, guess in (
                ("rule", [r[i] for _, _, r, _ in subset]),
                ("LLM", [a[question] for _, _, _, a in subset]),
            ):
                sc = E.score(truth, guess)
                print(
                    f"  {name:<14}{pct(sc.accuracy):>9}{pct(sc.yes_precision):>15}"
                    f"{pct(sc.yes_recall):>12}"
                )
    print()
    if args.split == "dev":  # the test split is never inspected case by case
        print("disagreements on readable pages (label -> LLM):")
        for x, _, _, a in ok:
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


SITE_COLUMNS = (
    "cnpj_basico domain url readable page_company is_company_site public_sector what_it_does "
    "evidence model prompt_version"
).split()


def no_nul(row: tuple) -> tuple:
    """Postgres text cannot hold NUL bytes, and a page (or the quote taken from it) may."""
    return tuple(v.replace("\x00", "") if isinstance(v, str) else v for v in row)


def run_checks(args: argparse.Namespace) -> None:
    """Check every top company with a candidate domain, then store all answers at once.

    Pages and LLM answers are cached on disk, so a run stopped by a rate limit, a sleeping
    laptop or Ctrl+C resumes where it stopped and costs nothing for the companies already done.
    """
    with connect() as conn:
        found = candidates(conn, args.top)
    chain = endpoints_from_env()
    version = E.prompt_version()
    rows, failed = [], 0
    with client() as http, httpx.Client(timeout=30) as api:
        for i, company in enumerate(found, start=1):
            page = cached(CACHE, http, company.domain)
            try:
                a = llm_answer(api, chain, company, page)
            except NoModelAnswered:
                failed += 1  # every model refused right now: left for the next run
                continue
            rows.append(no_nul(
                (company.cnpj_basico, company.domain, page.url, readable(page),
                 a.get("page_company", ""), a["is_company_site"], a["public_sector"],
                 a["what_it_does"], a["evidence"], a["model"], version)
            ))  # fmt: skip
            if i % 50 == 0:
                print(f"[{i}/{len(found)}] checked, {failed} left for a later run", flush=True)
    with connect() as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(SCHEMA.read_text())
        cur.execute("truncate site_check")
        with cur.copy(f"copy site_check ({', '.join(SITE_COLUMNS)}) from stdin") as copy:
            for row in rows:
                copy.write_row(row)
    verified = sum(r[5] == "yes" for r in rows)
    print(f"stored {len(rows)} checks ({verified} verified sites); {failed} left for a later run")


def main() -> None:
    parser = argparse.ArgumentParser(prog="lode.site", description="Website check with an LLM.")
    sub = parser.add_subparsers(dest="command", required=True)
    label = sub.add_parser("label", help="label the evaluation sample by hand")
    label.add_argument("--labels", type=Path, default=LABELS)
    label.set_defaults(run=run_label)
    evaluation = sub.add_parser("eval", help="compare the LLM with the hand labels")
    evaluation.add_argument("--split", choices=["dev", "test"], default="dev")
    evaluation.add_argument("--labels", type=Path, default=LABELS)
    evaluation.add_argument("--model", help="evaluate one model alone, without fallback")
    evaluation.set_defaults(run=run_eval)
    batch = sub.add_parser("run", help="check the top companies and store the answers")
    batch.add_argument("--top", type=int, default=TOP)
    batch.set_defaults(run=run_checks)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
