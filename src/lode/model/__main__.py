"""Train and evaluate the scoring model.

uv run python -m lode.model --cutoff 2025-11-01 --horizon-end 2026-11-01
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="lode.model", description="Train the scoring model.")
    parser.add_argument("--cutoff", type=date.fromisoformat, default=date(2025, 11, 1))
    parser.add_argument("--horizon-end", type=date.fromisoformat, default=date(2026, 11, 1))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("models"))
    args = parser.parse_args()

    load_dotenv()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        frame = to_frame(build(conn, args.cutoff, args.horizon_end))
    result = train(frame, args.seed)
    report(result)

    args.out.mkdir(exist_ok=True)
    with open(args.out / "model.pkl", "wb") as f:
        pickle.dump(result.models[result.chosen], f)
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


if __name__ == "__main__":
    main()
