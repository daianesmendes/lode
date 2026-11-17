from lode.site.candidates import Candidate
from lode.site.labels import Label, draw, read, write


def found(n):
    return [Candidate(f"{i:08d}", i, f"C{i}", None, "X", f"c{i}.com.br", 1) for i in range(n)]


def test_draw_is_fixed_and_split_into_dev_and_test():
    first, again = draw(found(500)), draw(found(500))
    assert first == again  # same seed, same sample
    assert len(first) == 100 and len({x.cnpj_basico for x in first}) == 100
    assert [x.split for x in first].count("dev") == 30
    assert all(x.split == "dev" for x in first[:30])


def test_labels_survive_a_round_trip(tmp_path):
    path = tmp_path / "labels.csv"
    labels = [Label("11111111", "dev", 3, "alfa.com.br", 1, "yes", "no", "group site")]
    labels.append(Label("22222222", "test", 9, "contabil.com.br", 40))
    write(path, labels)
    back = read(path)
    assert back == labels
    assert [x.done for x in back] == [True, False]
