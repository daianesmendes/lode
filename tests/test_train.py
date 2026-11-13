import numpy as np

from lode.model.pipeline import to_frame
from lode.model.train import train
from tests.test_pipeline import row


def test_train_beats_random_when_there_is_signal():
    rng = np.random.default_rng(1)
    capitals = rng.lognormal(9, 2, size=600)
    rows = [row(i, capital=f"{c:.2f}", won=c > 100000) for i, c in enumerate(capitals)]
    result = train(to_frame(rows), seed=1)
    assert result.train_rows == 480 and result.holdout_rows == 120
    assert result.holdout["logistic"]["pr_auc"] > result.holdout["random"]["pr_auc"]
    assert result.coefficients["capital"] > 0
