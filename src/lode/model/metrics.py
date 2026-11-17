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


def bootstrap(y_true, scores, metric, n: int = 1000, seed: int = 0) -> np.ndarray:
    """The metric recomputed on `n` resamples (with replacement) of the evaluated companies.

    The spread of these values shows how much the metric depends on which companies happened to
    be in the holdout. The same `seed` draws the same resamples, so two rankings bootstrapped
    with the same seed can be compared resample by resample (a paired comparison).
    """
    y = np.asarray(y_true)
    s = np.asarray(scores, dtype=float)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if 0 < y[idx].sum() < len(idx):  # a resample needs winners and non-winners
            values.append(metric(y[idx], s[idx]))
    return np.asarray(values)


def interval(samples: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    """Percentile interval holding `level` of the bootstrap values."""
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(samples, [tail, 100 - tail])
    return float(low), float(high)
