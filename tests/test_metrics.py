import numpy as np
import pytest
from sklearn.metrics import average_precision_score

from lode.model.metrics import bootstrap, evaluate, interval, lift_at, precision_at_k

# 10 companies, 2 winners. The scores put one winner first and the other in 6th place.
Y = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0]
SCORES = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]


def test_precision_at_k_counts_winners_in_the_top():
    assert precision_at_k(Y, SCORES, 1) == 1.0
    assert precision_at_k(Y, SCORES, 5) == 0.2  # 1 winner among the top 5
    assert precision_at_k(Y, SCORES, 10) == 0.2  # the whole list: the base rate


def test_ties_keep_the_input_order():
    assert precision_at_k([0, 1], [0.5, 0.5], 1) == 0.0


def test_lift_compares_the_top_with_random_picking():
    assert lift_at(Y, SCORES, 0.1) == 5.0  # top 1 is a winner; random gets 0.2
    assert lift_at(Y, SCORES, 1.0) == 1.0


def test_evaluate_reports_every_metric():
    result = evaluate(Y, SCORES)
    assert result["base_rate"] == 0.2
    assert result["pr_auc"] == pytest.approx((1 / 1 + 2 / 6) / 2)  # precision at each winner
    assert result["roc_auc"] == pytest.approx(12 / 16)  # winner-vs-loser pairs ranked right
    assert result["lift_at_10pct"] == 5.0


def test_bootstrap_of_a_perfect_ranking_has_no_spread():
    y = [1, 1, 0, 0, 0, 0]
    samples = bootstrap(y, [6, 5, 4, 3, 2, 1], average_precision_score, n=200)
    assert interval(samples) == (1.0, 1.0)


def test_bootstrap_interval_contains_the_metric_on_the_full_data():
    rng = np.random.default_rng(3)
    y = rng.random(2000) < 0.05
    scores = y + rng.normal(0, 1, 2000)  # a noisy but useful ranking
    low, high = interval(bootstrap(y, scores, average_precision_score, n=300))
    assert low < average_precision_score(y, scores) < high


def test_same_seed_gives_paired_resamples():
    rng = np.random.default_rng(4)
    y = rng.random(500) < 0.1
    scores = rng.random(500)
    a = bootstrap(y, scores, average_precision_score, n=50, seed=7)
    b = bootstrap(y, scores, average_precision_score, n=50, seed=7)
    assert (a - b == 0).all()
