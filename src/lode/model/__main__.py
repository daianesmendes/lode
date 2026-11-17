"""Train and evaluate the scoring model, then score every company.

uv run python -m lode.model train --cutoff 2025-11-01 --horizon-end 2026-11-01
uv run python -m lode.model score
"""

import argparse
import json
import os
import pickle
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from lode.model.features import build
from lode.model.pipeline import to_frame
from lode.model.score import model_version, score
from lode.model.train import Result, train


def report(result: Result) -> None:
    print(f"train {result.train_rows:,} rows, holdout {result.holdout_rows:,} rows\n")
    print("cross-validation PR-AUC (training rows, 5 folds):")
    for name, folds in result.cv_folds.items():
        print(f"  {name:<10} {folds.mean():.3f} ± {folds.std():.3f}  {result.best_params[name]}")
    print(f"chosen: {result.chosen}\n")

    print("holdout (reported only, never used to choose):")
    print(f"  {'ranking':<14}{'PR-AUC':>8}  {'95% interval':<15}{'prec@100':>9}{'lift@10%':>10}")
    for name, m in result.holdout.items():
        low, high = result.pr_auc_interval[name]
        print(
            f"  {name:<14}{m['pr_auc']:>8.3f}  {f'{low:.3f}–{high:.3f}':<15}"
            f"{m['precision_at_100']:>9.2f}{m['lift_at_10pct']:>10.1f}"
        )
    low, high = result.boosting_minus_logistic
    print(f"  boosting − logistic PR-AUC, paired 95% interval: {low:+.3f} to {high:+.3f}\n")

    print("logistic coefficients (standardized features):")
    print(result.coefficients.round(2).to_string(), "\n")
    print("boosting permutation importance (PR-AUC lost when the column is shuffled):")
    print(result.importance.round(3).to_string())


def connect() -> psycopg.Connection:
    load_dotenv()
    return psycopg.connect(os.environ["DATABASE_URL"])


def run_train(args: argparse.Namespace) -> None:
    with connect() as conn:
        frame = to_frame(build(conn, args.cutoff, args.horizon_end))
    result = train(frame, args.seed)
    report(result)

    args.out.mkdir(exist_ok=True)
    (args.out / "model.pkl").write_bytes(pickle.dumps(result.final_model))
    summary = {
        "cutoff": str(args.cutoff),
        "horizon_end": str(args.horizon_end),
        "seed": args.seed,
        "chosen": result.chosen,
        "best_params": result.best_params,
        "cv_pr_auc": {name: folds.tolist() for name, folds in result.cv_folds.items()},
        "train_rows": result.train_rows,
        "holdout_rows": result.holdout_rows,
        "holdout": result.holdout,
        "holdout_pr_auc_interval": result.pr_auc_interval,
        "boosting_minus_logistic": result.boosting_minus_logistic,
        "coefficients": result.coefficients.round(4).to_dict(),
        "importance": result.importance.round(4).to_dict(),
    }
    (args.out / "metrics.json").write_text(json.dumps(summary, indent=2))
    print(f"\nsaved {result.chosen}, refit on all {len(frame):,} rows, to {args.out}/model.pkl")


def run_score(args: argparse.Namespace) -> None:
    model_bytes = (args.out / "model.pkl").read_bytes()
    metrics = json.loads((args.out / "metrics.json").read_text())
    with connect() as conn:
        result = score(conn, pickle.loads(model_bytes), model_version(model_bytes), metrics)
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(prog="lode.model", description="Lode scoring model.")
    sub = parser.add_subparsers(dest="command", required=True)
    parser.add_argument("--out", type=Path, default=Path("models"))

    fit = sub.add_parser("train", help="train, evaluate on a holdout and save the chosen model")
    fit.add_argument("--cutoff", type=date.fromisoformat, default=date(2025, 11, 1))
    fit.add_argument("--horizon-end", type=date.fromisoformat, default=date(2026, 11, 1))
    fit.add_argument("--seed", type=int, default=42)
    fit.set_defaults(run=run_train)

    rank = sub.add_parser("score", help="score every company today and store it in Postgres")
    rank.set_defaults(run=run_score)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
