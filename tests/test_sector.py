import pytest

from lode.sector import SOFTWARE, normalize_cnae


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("6201-5/01", "6201501"), ("6201501", "6201501"), (" 6204-0/00 ", "6204000")],
)
def test_normalize_cnae_accepts_written_and_raw_forms(raw, expected):
    assert normalize_cnae(raw) == expected


@pytest.mark.parametrize("bad", ["", "62", "6201-5/011", "62.01-5"])
def test_normalize_cnae_rejects_codes_without_7_digits(bad):
    with pytest.raises(ValueError):
        normalize_cnae(bad)


def test_software_sector_is_cnae_division_62():
    assert SOFTWARE.cnaes, "sector must list at least one CNAE"
    assert all(code.startswith("62") for code in SOFTWARE.cnaes)


def test_sector_membership():
    assert SOFTWARE.includes("6201-5/01")
    assert not SOFTWARE.includes("4120-4/00")  # building construction
