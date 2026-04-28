from ah_research.config import get_settings
from ah_research.scripts.ah_warmup import compute_symbols, run


def test_compute_symbols_sample_returns_5():
    syms = compute_symbols("sample")
    assert "600519.SH" in syms
    assert "0700.HK" in syms
    assert len(syms) == 5


def test_compute_symbols_csi300_via_test_mode():
    syms = compute_symbols("csi300", test_mode=True)
    assert len(syms) == 300


def test_compute_symbols_hsi_via_test_mode():
    syms = compute_symbols("hsi", test_mode=True)
    assert len(syms) == 50
    assert all(s.endswith(".HK") for s in syms)


def test_run_sample_populates_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path))
    get_settings.cache_clear()

    run(universe="sample", years=1, test_mode=True)

    cache_path = tmp_path / "cache.duckdb"
    assert cache_path.exists()
