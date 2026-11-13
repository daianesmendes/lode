"""Turn the feature rows into numbers a model can use, inside a scikit-learn Pipeline.

Every statistic a transformation needs (medians, means, which legal natures are common) is
learned in ``fit``, that is, from the training rows only. Computing them on the whole table
would leak information from the held-out companies into the model.
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

COUNTS = [
    "age_years",
    "establishments",
    "secondary_cnaes",
    "partners",
    "partners_person",
    "partners_company",
    "partners_foreign",
]
FLAGS = ["hq_in_capital", "simples"]
# Not a feature: `partners_changed` says the partner list changed AFTER the cutoff, which nobody
# knew on that date. It leaked the future (winners change partners more often), so it stays in
# the table only as a data-quality warning.
NOT_FEATURES = ["partners_changed"]
AGE_BANDS = ["youngest_age_band", "oldest_age_band"]  # empty when there is no partner
CAPITAL = ["capital"]  # from R$ 0 to billions: log scale
CATEGORIES = ["size_code", "legal_nature"]
LABEL = "won"

# Legal natures: the 5 most common get their own column, the rest share an "other" column.
TOP_LEGAL_NATURES = 5


def to_frame(rows: list[dict]) -> pd.DataFrame:
    """Rows from features.build as a DataFrame with plain numeric types (no Decimal)."""
    frame = pd.DataFrame(rows).set_index("cnpj_basico")
    numeric = COUNTS + AGE_BANDS + CAPITAL
    frame[numeric] = frame[numeric].astype(float)
    frame[FLAGS + [LABEL]] = frame[FLAGS + [LABEL]].astype(int)
    return frame


def preprocessing() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("counts", StandardScaler(), COUNTS),
            ("flags", "passthrough", FLAGS),
            (
                "age_bands",
                make_pipeline(
                    SimpleImputer(strategy="median", add_indicator=True), StandardScaler()
                ),
                AGE_BANDS,
            ),
            (
                "capital",
                make_pipeline(
                    FunctionTransformer(np.log1p, feature_names_out="one-to-one"), StandardScaler()
                ),
                CAPITAL,
            ),
            (
                "categories",
                OneHotEncoder(
                    max_categories=TOP_LEGAL_NATURES + 1,  # + 1 for the "other" column
                    handle_unknown="infrequent_if_exist",
                    sparse_output=False,
                ),
                CATEGORIES,
            ),
        ]
    )


def logistic(c: float = 1.0) -> Pipeline:
    """Baseline model: every coefficient can be read and explained."""
    return Pipeline([("prep", preprocessing()), ("model", LogisticRegression(C=c, max_iter=2000))])
