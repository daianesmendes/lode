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
from lode.model.train import train


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

    print(f"train {result.train_rows:,} rows, holdout {result.holdout_rows:,} rows")
    print(f"chosen C = {result.best_c}\n")
    print(f"{'ranking':<14}{'PR-AUC':>8}{'ROC-AUC':>9}{'prec@100':>10}{'lift@10%':>10}")
    for name, m in result.holdout.items():
        print(
            f"{name:<14}{m['pr_auc']:>8.3f}{m['roc_auc']:>9.3f}"
            f"{m['precision_at_100']:>10.2f}{m['lift_at_10pct']:>10.1f}"
        )
    print("\ncoefficients (standardized features):")
    print(result.coefficients.round(2).to_string())

    args.out.mkdir(exist_ok=True)
    with open(args.out / "logistic.pkl", "wb") as f:
        pickle.dump(result.model, f)
    report = {
        "cutoff": str(args.cutoff),
        "horizon_end": str(args.horizon_end),
        "seed": args.seed,
        "best_c": result.best_c,
        "train_rows": result.train_rows,
        "holdout_rows": result.holdout_rows,
        "holdout": result.holdout,
        "coefficients": result.coefficients.round(4).to_dict(),
    }
    (args.out / "metrics.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
