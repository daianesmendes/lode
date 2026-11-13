import pytest

from lode.model.metrics import evaluate, lift_at, precision_at_k

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
