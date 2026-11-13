from decimal import Decimal

import numpy as np

from lode.model.pipeline import logistic, preprocessing, to_frame


def row(n, legal_nature="2062", band=4, won=False, capital="1000.00"):
    return {
        "cnpj_basico": f"{n:08d}",
        "age_years": Decimal("5.5"),
        "establishments": 1,
        "hq_in_capital": True,
        "secondary_cnaes": 3,
        "capital": Decimal(capital),
        "size_code": "01",
        "legal_nature": legal_nature,
        "simples": True,
        "partners_changed": False,
        "partners": 1,
        "partners_person": 1,
        "partners_company": 0,
        "partners_foreign": 0,
        "youngest_age_band": band,
        "oldest_age_band": band,
        "won": won,
    }


def test_to_frame_uses_plain_numbers():
    frame = to_frame([row(1, capital="450000.00", won=True)])
    assert frame.index.tolist() == ["00000001"]
    assert frame.loc["00000001", "capital"] == 450000.0
    assert frame["won"].dtype.kind == "i" and frame["simples"].dtype.kind == "i"


def test_missing_age_band_gets_the_median_of_the_training_rows_only():
    train = to_frame([row(1, band=2), row(2, band=4), row(3, band=None)])
    prep = preprocessing().fit(train)
    imputer = prep.named_transformers_["age_bands"][0]
    assert imputer.statistics_.tolist() == [3.0, 3.0]
    # a held-out row with an extreme band does not change what was learned
    prep.transform(to_frame([row(4, band=9)]))
    assert imputer.statistics_.tolist() == [3.0, 3.0]


def test_rare_and_unseen_legal_natures_share_the_other_column():
    natures = ["2062"] * 6 + ["2135"] * 5 + ["2240"] * 4 + ["2054"] * 3 + ["2305"] * 2
    natures += ["2011", "2038"]  # rare: only one company each
    prep = preprocessing().fit(to_frame([row(i, legal_nature=n) for i, n in enumerate(natures)]))
    names = [n for n in prep.get_feature_names_out() if "legal_nature" in n]
    assert len(names) == 6  # 5 most common + other
    assert names[-1].endswith("infrequent_sklearn")
    unseen = prep.transform(to_frame([row(99, legal_nature="9999")]))
    columns = list(prep.get_feature_names_out())
    assert unseen[0, columns.index(names[-1])] == 1.0


def test_facts_from_after_the_cutoff_are_not_features():
    prep = preprocessing().fit(to_frame([row(1), row(2)]))
    assert not any("partners_changed" in n for n in prep.get_feature_names_out())


def test_logistic_learns_a_probability_per_company():
    rng = np.random.default_rng(0)
    rows = [
        row(i, capital=f"{c:.2f}", won=c > 50000)
        for i, c in enumerate(rng.lognormal(9, 2, size=200))
    ]
    frame = to_frame(rows)
    model = logistic().fit(frame, frame["won"])
    proba = model.predict_proba(frame)[:, 1]
    assert proba.shape == (200,) and ((proba >= 0) & (proba <= 1)).all()
    # more capital, higher probability: the only signal in this toy data
    assert proba[frame["capital"].argmax()] > proba[frame["capital"].argmin()]
