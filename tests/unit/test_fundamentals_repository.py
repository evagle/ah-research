"""Unit tests for ``data.fundamentals_repository.FundamentalsRepository``
(carved out in H4).

Pins the contract of the fundamentals sub-repository in isolation: PIT
filtering, the leakage guard, and date-range validation.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ah_research.data.cache import DuckDBCache
from ah_research.data.fundamentals_repository import FundamentalsRepository
from ah_research.exceptions import LeakageDetected, UserInputError
from ah_research.integrations.fake import FakeSources
from ah_research.model.schemas import FundamentalsFrameSchema

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
def fundamentals_repo(fake_sources: FakeSources, cache: DuckDBCache) -> FundamentalsRepository:
    return FundamentalsRepository(
        fundamentals_source=fake_sources.fundamentals,
        cache=cache,
    )


# ── happy paths ─────────────────────────────────────────────────────────────


def test_returns_schema_valid_frame(fundamentals_repo: FundamentalsRepository) -> None:
    df = fundamentals_repo.get_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31))
    FundamentalsFrameSchema.validate(df)


def test_defaults_asof_to_end(fundamentals_repo: FundamentalsRepository) -> None:
    """When asof is omitted, it defaults to end -- so the query returns
    everything PIT-known at the analysis period's end."""
    df = fundamentals_repo.get_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31))
    assert (df["publication_date"] <= pd.Timestamp("2024-12-31")).all()
    assert (df["known_as_of"] <= pd.Timestamp("2024-12-31")).all()


def test_explicit_asof_filters_future_publications(
    fundamentals_repo: FundamentalsRepository,
) -> None:
    """A PIT query at 2022-06-30 must not return reports published after."""
    df = fundamentals_repo.get_fundamentals(
        ["600519.SH"],
        date(2020, 1, 1),
        date(2024, 12, 31),
        asof=date(2022, 6, 30),
    )
    assert (df["publication_date"] <= pd.Timestamp("2022-06-30")).all()
    assert (df["known_as_of"] <= pd.Timestamp("2022-06-30")).all()


def test_empty_symbols_returns_empty(fundamentals_repo: FundamentalsRepository) -> None:
    df = fundamentals_repo.get_fundamentals([], date(2020, 1, 1), date(2024, 12, 31))
    assert len(df) == 0


# ── error paths ─────────────────────────────────────────────────────────────


def test_raises_leakage_when_asof_after_end(
    fundamentals_repo: FundamentalsRepository,
) -> None:
    """asof > end leaks knowledge gained after the analysis window."""
    with pytest.raises(LeakageDetected):
        fundamentals_repo.get_fundamentals(
            ["600519.SH"],
            date(2020, 1, 1),
            date(2022, 12, 31),
            asof=date(2024, 6, 30),
        )


def test_raises_on_reversed_dates(fundamentals_repo: FundamentalsRepository) -> None:
    with pytest.raises(UserInputError):
        fundamentals_repo.get_fundamentals(["600519.SH"], date(2024, 12, 31), date(2020, 1, 1))
