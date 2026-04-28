from datetime import date

import pandas as pd
import pytest

from ah_research.data.cache import DuckDBCache
from ah_research.exceptions import DataIntegrityError


def _price_row(d: str, sym: str = "600519.SH", close: float = 1710.0) -> dict:
    return {
        "date": pd.Timestamp(d),
        "symbol": sym,
        "open": close - 10,
        "high": close + 10,
        "low": close - 15,
        "close": close,
        "close_hfq": close,
        "total_return": close + 90,
        "volume": 1_000_000,
        "amount": close * 1_000_000,
        "turnover": 0.001,
        "is_suspended": False,
        "is_st": False,
        "limit_up": close * 1.1,
        "limit_down": close * 0.9,
        "hit_limit_up": False,
        "hit_limit_down": False,
    }


def test_cache_creates_file_on_init(tmp_path):
    path = tmp_path / "cache.duckdb"
    cache = DuckDBCache(path)
    assert path.exists()
    cache.close()


def test_cache_parent_dir_is_created(tmp_path):
    path = tmp_path / "nested" / "dir" / "cache.duckdb"
    cache = DuckDBCache(path)
    assert path.exists()
    cache.close()


def test_cache_applies_initial_migration(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    assert cache.schema_version() >= 1
    tables = cache.list_tables()
    for expected in (
        "prices",
        "fundamentals",
        "index_constituents",
        "calendars",
        "fx_rates",
        "sectors",
        "corporate_actions",
        "meta",
    ):
        assert expected in tables
    cache.close()


def test_cache_reopening_does_not_re_run_migration(tmp_path):
    """Migrations use IF NOT EXISTS / INSERT OR IGNORE so reopening is safe."""
    path = tmp_path / "cache.duckdb"
    c1 = DuckDBCache(path)
    v1 = c1.schema_version()
    c1.close()
    c2 = DuckDBCache(path)
    assert c2.schema_version() == v1
    c2.close()


def test_cache_context_manager(tmp_path):
    path = tmp_path / "cache.duckdb"
    with DuckDBCache(path) as cache:
        assert cache.schema_version() >= 1
    # After ``with`` exit, connection is closed — reopening should succeed.
    with DuckDBCache(path) as cache:
        assert cache.schema_version() >= 1


def test_cache_prices_roundtrip(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    df = pd.DataFrame(
        [_price_row("2024-01-02", close=1710.0), _price_row("2024-01-03", close=1705.0)]
    )
    cache.write_prices(df)
    out = cache.read_prices(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert len(out) == 2
    assert set(out["symbol"]) == {"600519.SH"}
    cache.close()


def test_cache_prices_idempotent_on_duplicate_writes(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    df = pd.DataFrame([_price_row("2024-01-02")])
    cache.write_prices(df)
    cache.write_prices(df)  # should replace, not duplicate
    out = cache.read_prices(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert len(out) == 1
    cache.close()


def test_cache_prices_upsert_updates_existing_rows(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_prices(pd.DataFrame([_price_row("2024-01-02", close=1710.0)]))
    cache.write_prices(pd.DataFrame([_price_row("2024-01-02", close=1900.0)]))
    out = cache.read_prices(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert len(out) == 1
    assert float(out["close"].iloc[0]) == 1900.0
    cache.close()


def test_cache_read_prices_filters_by_date_range(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_prices(
        pd.DataFrame(
            [
                _price_row("2023-12-31"),
                _price_row("2024-01-15"),
                _price_row("2024-06-01"),
            ]
        )
    )
    out = cache.read_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert len(out) == 1
    assert pd.Timestamp(out["date"].iloc[0]).date() == date(2024, 1, 15)
    cache.close()


def test_cache_read_prices_filters_by_symbol(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_prices(
        pd.DataFrame(
            [
                _price_row("2024-01-02", sym="600519.SH"),
                _price_row("2024-01-02", sym="0700.HK"),
            ]
        )
    )
    out = cache.read_prices(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert len(out) == 1
    assert out["symbol"].iloc[0] == "600519.SH"
    cache.close()


def test_cache_read_prices_empty_when_no_data(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    out = cache.read_prices(["NONEXISTENT.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert len(out) == 0
    cache.close()


def test_cache_price_coverage_empty(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    assert cache.price_coverage("600519.SH") is None
    cache.close()


def test_cache_price_coverage_after_write(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_prices(pd.DataFrame([_price_row("2024-01-02"), _price_row("2024-06-15")]))
    coverage = cache.price_coverage("600519.SH")
    assert coverage is not None
    lo, hi = coverage
    assert lo == date(2024, 1, 2)
    assert hi == date(2024, 6, 15)
    cache.close()


def test_cache_corrupt_meta_raises_data_integrity_error(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache._conn.execute("DELETE FROM meta WHERE key = 'schema_version'")
    with pytest.raises(DataIntegrityError):
        cache.schema_version()
    cache.close()
