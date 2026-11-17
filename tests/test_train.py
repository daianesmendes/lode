import numpy as np

from lode.model.pipeline import to_frame
from lode.model.train import choose, train
from tests.test_pipeline import row


def test_train_beats_random_and_reports_both_models():
    rng = np.random.default_rng(1)
    capitals = rng.lognormal(9, 2, size=600)
    rows = [row(i, capital=f"{c:.2f}", won=c > 100000) for i, c in enumerate(capitals)]
    result = train(to_frame(rows), seed=1)
    assert result.train_rows == 480 and result.holdout_rows == 120
    assert set(result.models) == {"logistic", "boosting"}
    for name in ("logistic", "boosting"):
        assert result.holdout[name]["pr_auc"] > result.holdout["random"]["pr_auc"]
        low, high = result.pr_auc_interval[name]
        assert low <= result.holdout[name]["pr_auc"] <= high
    assert result.coefficients["capital"] > 0
    assert result.importance.index[0] == "capital"  # the only signal in this toy data


def test_boosting_must_win_clearly_on_every_fold():
    logistic = np.array([0.15, 0.16, 0.17, 0.15, 0.16])
    assert choose({"logistic": logistic, "boosting": logistic + 0.02}) == "boosting"
    # better on average, but only thanks to one lucky fold: not a clear win
    lucky = logistic + np.array([0.08, -0.01, -0.01, -0.01, -0.01])
    assert choose({"logistic": logistic, "boosting": lucky}) == "logistic"
    assert choose({"logistic": logistic, "boosting": logistic}) == "logistic"
