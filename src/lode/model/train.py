"""Train the candidate models, choose one by cross-validation, score both on a holdout.

The holdout is split off first and only reported, never used to decide anything: the
hyperparameters and the choice between the models are made by cross-validation inside the
training rows. Deciding on the holdout would make its numbers optimistic.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline

from lode.model.metrics import bootstrap, evaluate, interval
from lode.model.pipeline import FEATURES, LABEL, boosting, logistic

HOLDOUT = 0.2
FOLDS = 5
BOOTSTRAP = 1000


def candidates(seed: int) -> dict[str, tuple[Pipeline, dict]]:
    return {
        "logistic": (logistic(), {"model__C": [0.01, 0.1, 1.0, 10.0]}),
        "boosting": (
            boosting(seed),
            {
                "model__learning_rate": [0.05, 0.1],
                "model__max_leaf_nodes": [15, 31],
                "model__min_samples_leaf": [20, 100],
            },
        ),
    }


@dataclass
class Result:
    chosen: str
    models: dict[str, Pipeline]
    best_params: dict[str, dict]
    cv_folds: dict[str, np.ndarray]  # PR-AUC of the best setting on each fold
    train_rows: int
    holdout_rows: int
    holdout: dict[str, dict[str, float]]  # ranking name -> metrics
    pr_auc_interval: dict[str, tuple[float, float]]
    boosting_minus_logistic: tuple[float, float]  # paired bootstrap interval of PR-AUC
    coefficients: pd.Series
    importance: pd.Series  # PR-AUC lost when one input column is shuffled (boosting)
    final_model: Pipeline  # the chosen model refit on every labeled row, used for scoring


def fold_scores(search: GridSearchCV) -> np.ndarray:
    i = search.best_index_
    return np.array([search.cv_results_[f"split{k}_test_score"][i] for k in range(FOLDS)])


def choose(cv_folds: dict[str, np.ndarray]) -> str:
    """Boosting wins only if its edge over the logistic, fold by fold, is clearly above zero:
    the mean gain must be larger than how much the gain varies between folds."""
    gain = cv_folds["boosting"] - cv_folds["logistic"]
    return "boosting" if gain.mean() > gain.std() else "logistic"


def train(frame: pd.DataFrame, seed: int = 42) -> Result:
    y = frame[LABEL]
    x_train, x_test, y_train, y_test = train_test_split(
        frame[FEATURES], y, test_size=HOLDOUT, stratify=y, random_state=seed
    )
    folds = StratifiedKFold(FOLDS, shuffle=True, random_state=seed)  # same folds for both
    models, best_params, cv_folds = {}, {}, {}
    for name, (pipeline, grid) in candidates(seed).items():
        search = GridSearchCV(pipeline, grid, scoring="average_precision", cv=folds)
        search.fit(x_train, y_train)
        models[name] = search.best_estimator_
        best_params[name] = {k.removeprefix("model__"): v for k, v in search.best_params_.items()}
        cv_folds[name] = fold_scores(search)

    rng = np.random.default_rng(seed)
    rankings = {
        "random": rng.random(len(x_test)),
        "capital only": x_test["capital"].to_numpy(),
        **{name: model.predict_proba(x_test)[:, 1] for name, model in models.items()},
    }
    samples = {
        name: bootstrap(y_test, scores, average_precision_score, BOOTSTRAP, seed)
        for name, scores in rankings.items()
    }

    log = models["logistic"]
    names = [n.split("__", 1)[1] for n in log["prep"].get_feature_names_out()]
    importance = permutation_importance(
        models["boosting"],
        x_test,
        y_test,
        scoring="average_precision",
        n_repeats=5,
        random_state=seed,
    )
    # The holdout has done its job (measuring). The model that scores companies learns from
    # every labeled row, with the hyperparameters already chosen by cross-validation.
    chosen = choose(cv_folds)
    final_model = clone(models[chosen]).fit(frame[FEATURES], y)
    return Result(
        chosen=chosen,
        models=models,
        best_params=best_params,
        cv_folds=cv_folds,
        train_rows=len(x_train),
        holdout_rows=len(x_test),
        holdout={name: evaluate(y_test, scores) for name, scores in rankings.items()},
        pr_auc_interval={name: interval(s) for name, s in samples.items()},
        boosting_minus_logistic=interval(samples["boosting"] - samples["logistic"]),
        coefficients=pd.Series(log["model"].coef_[0], index=names).sort_values(),
        importance=pd.Series(importance.importances_mean, index=FEATURES).sort_values(
            ascending=False
        ),
        final_model=final_model,
    )
