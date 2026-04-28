from ah_research.data.ah_pairs import load_ah_pairs


def test_load_ah_pairs_returns_pairs_only():
    pairs = load_ah_pairs()
    assert len(pairs) >= 20
    for p in pairs:
        assert p.a_symbol.exchange.value in ("SH", "SZ")
        assert p.h_symbol.exchange.value == "HK"


def test_loaded_pairs_include_ping_an():
    pairs = load_ah_pairs()
    names = [p.name_zh for p in pairs]
    assert "中国平安" in names


def test_loaded_pairs_include_icbc():
    pairs = load_ah_pairs()
    names = [p.name_zh for p in pairs]
    assert "工商银行" in names


def test_loaded_pairs_are_unique_by_a_symbol():
    pairs = load_ah_pairs()
    a_codes = [str(p.a_symbol) for p in pairs]
    assert len(a_codes) == len(set(a_codes))
