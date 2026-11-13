"""How good a ranking of companies is, measured the way the product uses it.

With less than 1% of winners, accuracy says nothing: predicting "nobody wins" is 99% accurate.
What matters is whether the winners are near the top of the list, so the metrics look at the
top of the ranking and compare it with picking companies at random (the base rate).
"""

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


def _top(y_true, scores, k: int) -> np.ndarray:
    """Labels of the k highest scores. Ties keep the input order (stable sort)."""
    order = np.argsort(-np.asarray(scores, dtype=float), kind="stable")
    return np.asarray(y_true)[order[:k]]


def precision_at_k(y_true, scores, k: int) -> float:
    """Share of winners among the k companies with the highest score."""
    return float(_top(y_true, scores, k).mean())


def lift_at(y_true, scores, fraction: float) -> float:
    """How many times better than random the top `fraction` of the ranking is."""
    k = max(1, round(len(scores) * fraction))
    return precision_at_k(y_true, scores, k) / float(np.mean(y_true))


def evaluate(y_true, scores) -> dict[str, float]:
    return {
        "base_rate": float(np.mean(y_true)),
        "pr_auc": float(average_precision_score(y_true, scores)),
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "precision_at_100": precision_at_k(y_true, scores, 100),
        "lift_at_10pct": lift_at(y_true, scores, 0.10),
    }
