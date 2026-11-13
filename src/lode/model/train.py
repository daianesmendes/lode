"""Train the baseline, choose its regularization by cross-validation, score it on a holdout.

The holdout is split off first and used once, at the end. Everything that is chosen (the
regularization strength C) is chosen by cross-validation inside the training rows.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline

from lode.model.metrics import evaluate
from lode.model.pipeline import LABEL, logistic

HOLDOUT = 0.2
C_GRID = [0.01, 0.1, 1.0, 10.0]


@dataclass
class Result:
    model: Pipeline
    best_c: float
    train_rows: int
    holdout_rows: int
    holdout: dict[str, dict[str, float]]  # ranking name -> metrics
    coefficients: pd.Series


def train(frame: pd.DataFrame, seed: int = 42) -> Result:
    y = frame[LABEL]
    x_train, x_test, y_train, y_test = train_test_split(
        frame, y, test_size=HOLDOUT, stratify=y, random_state=seed
    )
    search = GridSearchCV(
        logistic(),
        {"model__C": C_GRID},
        scoring="average_precision",  # PR-AUC
        cv=StratifiedKFold(5, shuffle=True, random_state=seed),
    )
    search.fit(x_train, y_train)
    model = search.best_estimator_

    rng = np.random.default_rng(seed)
    rankings = {
        "random": rng.random(len(x_test)),
        "capital only": x_test["capital"].to_numpy(),
        "logistic": model.predict_proba(x_test)[:, 1],
    }
    names = [n.split("__", 1)[1] for n in model["prep"].get_feature_names_out()]
    coefficients = pd.Series(model["model"].coef_[0], index=names).sort_values()
    return Result(
        model=model,
        best_c=search.best_params_["model__C"],
        train_rows=len(x_train),
        holdout_rows=len(x_test),
        holdout={name: evaluate(y_test, scores) for name, scores in rankings.items()},
        coefficients=coefficients,
    )
