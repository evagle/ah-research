"""Unit tests for ``data.config_repository.ConfigRepository`` (carved out in H4).

Pins the contract of the metadata sub-repository in isolation:
index constituents PIT-correct membership, survivorship-free
universe-over-time, and sector classification with cache-hit semantics.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ah_research.data.cache import DuckDBCache
from ah_research.data.config_repository import ConfigRepository
from ah_research.integrations.fake import FakeSources

# ── Shared fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def fake_sources() -> FakeSources:
    return FakeSources(seed=42)


@pytest.fixture
def cache(tmp_path: Path):
    c = DuckDBCache(tmp_path / "cache.duckdb")
    yield c
    c.close()


@pytest.fixture
def config_repo(fake_sources: FakeSources, cache: DuckDBCache) -> ConfigRepository:
    return ConfigRepository(
        constituents_source=fake_sources.constituents,
        sector_source=fake_sources.sectors,
        cache=cache,
    )


# ── get_index_constituents ─────────────────────────────────────────────────


def test_csi300_size(config_repo: ConfigRepository) -> None:
    df = config_repo.get_index_constituents("CSI300", date(2024, 6, 30))
    assert len(df) == 300


def test_hsi_all_hk_symbols(config_repo: ConfigRepository) -> None:
    df = config_repo.get_index_constituents("HSI", date(2024, 6, 30))
    assert len(df) == 50
    assert df["symbol"].str.endswith(".HK").all()


def test_index_constituents_second_call_hits_cache(
    config_repo: ConfigRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second call for the same (index, asof) must not re-fetch."""
    _ = config_repo.get_index_constituents("CSI300", date(2024, 6, 30))
    spy = MagicMock(wraps=config_repo._constituents_source.fetch_constituents)
    monkeypatch.setattr(config_repo._constituents_source, "fetch_constituents", spy)

    _ = config_repo.get_index_constituents("CSI300", date(2024, 6, 30))
    assert spy.call_count == 0


# ── get_universe_over_time ──────────────────────────────────────────────────


def test_universe_over_time_has_required_columns(config_repo: ConfigRepository) -> None:
    df = config_repo.get_universe_over_time("CSI300", date(2024, 1, 1), date(2024, 6, 30))
    assert {"date", "symbol", "weight"} <= set(df.columns)
    assert len(df) > 0


def test_universe_over_time_monthly_samples(config_repo: ConfigRepository) -> None:
    df = config_repo.get_universe_over_time(
        "CSI300", date(2024, 1, 1), date(2024, 6, 30), freq="ME"
    )
    sample_dates = df["date"].unique()
    # 2024-01 through 2024-06 month-ends = 6 samples.
    assert len(sample_dates) == 6


def test_universe_over_time_300_members_per_sample(config_repo: ConfigRepository) -> None:
    df = config_repo.get_universe_over_time("CSI300", date(2024, 1, 1), date(2024, 6, 30))
    per_sample = df.groupby("date")["symbol"].nunique()
    assert (per_sample == 300).all()


# ── get_sector ──────────────────────────────────────────────────────────────


def test_sector_returns_one_row_per_symbol(config_repo: ConfigRepository) -> None:
    df = config_repo.get_sector(["600519.SH", "0700.HK"])
    assert len(df) == 2


def test_sector_empty_input_returns_shaped_empty_frame(
    config_repo: ConfigRepository,
) -> None:
    df = config_repo.get_sector([])
    assert len(df) == 0
    assert {"symbol", "sector_l1", "sector_l2"} <= set(df.columns)


def test_sector_second_call_does_not_refetch(
    config_repo: ConfigRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sectors are static -- once cached, the second call must not touch
    the underlying source."""
    _ = config_repo.get_sector(["600519.SH"])
    spy = MagicMock(wraps=config_repo._sector_source.fetch_sectors)
    monkeypatch.setattr(config_repo._sector_source, "fetch_sectors", spy)

    _ = config_repo.get_sector(["600519.SH"])
    assert spy.call_count == 0


def test_sector_only_fetches_missing_symbols(
    config_repo: ConfigRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache for one symbol primed; second call with two symbols only
    fetches the new one."""
    _ = config_repo.get_sector(["600519.SH"])
    spy = MagicMock(wraps=config_repo._sector_source.fetch_sectors)
    monkeypatch.setattr(config_repo._sector_source, "fetch_sectors", spy)

    _ = config_repo.get_sector(["600519.SH", "0700.HK"])
    assert spy.call_count == 1
    fetched = spy.call_args.args[0] if spy.call_args.args else spy.call_args.kwargs["symbols"]
    assert fetched == ["0700.HK"]
