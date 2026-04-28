"""Shared fixtures used across unit tests.

Fixtures here compose ``FakeSources`` + a fresh ``DuckDBCache`` into a
fully-wired ``DataRepository``, so repository tests do not need to know
about the integration boundary.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ah_research.data.cache import DuckDBCache
from ah_research.data.repository import DataRepository
from ah_research.integrations.fake import FakeSources

if TYPE_CHECKING:
    pass


@pytest.fixture
def fake_sources() -> FakeSources:
    return FakeSources(seed=42)


@pytest.fixture
def cache(tmp_path: Path):
    c = DuckDBCache(tmp_path / "cache.duckdb")
    yield c
    c.close()


@pytest.fixture
def repo(fake_sources: FakeSources, cache: DuckDBCache) -> DataRepository:
    return DataRepository(
        price_source=fake_sources.prices,
        fundamentals_source=fake_sources.fundamentals,
        fx_source=fake_sources.fx,
        calendar_source=fake_sources.calendar,
        sector_source=fake_sources.sectors,
        corp_actions_source=fake_sources.corporate_actions,
        constituents_source=fake_sources.constituents,
        cache=cache,
    )
