"""Shared factory helpers for CLI scripts.

Exists so ``_make_repo`` is not copy-pasted across ah_construct, ah_dossier,
ah_watchlist, etc. The individual scripts re-export under the ``_make_repo``
name to preserve existing tests that patch by path.
"""

from __future__ import annotations


def make_repo() -> object:
    """Build a DataRepository from the default cache + FakeSources.

    Kept as a thin factory returning ``object`` so the scripts layer does not
    leak ``DataRepository`` types into module top-levels (preserves existing
    type-check surface).
    """
    from ah_research.config import get_settings
    from ah_research.data.cache import DuckDBCache
    from ah_research.data.repository import DataRepository
    from ah_research.integrations.fake import FakeSources

    settings = get_settings()
    sources = FakeSources(seed=42)
    cache = DuckDBCache(settings.cache_duckdb_path)
    return DataRepository(
        price_source=sources.prices,
        fundamentals_source=sources.fundamentals,
        fx_source=sources.fx,
        calendar_source=sources.calendar,
        sector_source=sources.sectors,
        corp_actions_source=sources.corporate_actions,
        constituents_source=sources.constituents,
        cache=cache,
    )
