"""``ah warmup`` — pre-fetch prices + fundamentals for a universe so
subsequent interactive queries hit the cache.

Three modes:
- ``sample``  — 5 hand-picked liquid names across SH/SZ/HK
- ``csi300``  — all ~300 CSI 300 members as of today
- ``hsi``     — all ~50 HSI members as of today

The real client wiring (Baostock for A-shares, AKshare for HK / FX / sectors)
lands in Phase 1 Tasks 1.21 and 1.22. Until then, ``run()`` accepts a
``test_mode`` kwarg that routes through ``FakeSources`` — this keeps the
CLI path testable without network.
"""

from __future__ import annotations

from datetime import date, timedelta

import typer

from ah_research.config import get_settings
from ah_research.data.cache import DuckDBCache
from ah_research.data.repository import DataRepository
from ah_research.logging import configure_logging, get_logger

log = get_logger(__name__)

_SAMPLE_UNIVERSE: list[str] = [
    "600519.SH",  # Kweichow Moutai
    "601318.SH",  # Ping An
    "600036.SH",  # China Merchants Bank
    "0700.HK",  # Tencent
    "9988.HK",  # Alibaba
]


def compute_symbols(
    universe: str,
    *,
    test_mode: bool = False,
) -> list[str]:
    """Resolve a universe name into a concrete symbol list.

    In ``test_mode`` the function bypasses live integration clients and
    returns a deterministic list via the fake sources (used by unit tests).
    """
    universe_lower = universe.lower()
    if universe_lower == "sample":
        return list(_SAMPLE_UNIVERSE)
    if test_mode:
        from ah_research.integrations.fake import FakeSources

        index = "CSI300" if universe_lower == "csi300" else "HSI"
        fake = FakeSources(seed=42)
        df = fake.constituents.fetch_constituents(index, date.today())
        return df["symbol"].tolist()
    raise NotImplementedError(
        f"universe={universe!r} requires live integration (Phase 1 Tasks 1.21/1.22)"
    )


def run(
    *,
    universe: str = "sample",
    years: int = 5,
    test_mode: bool = False,
) -> None:
    """Main entrypoint. Fetch + cache ``years`` of prices and fundamentals
    for the resolved universe."""
    configure_logging()
    settings = get_settings()
    end = date.today()
    start = end - timedelta(days=365 * years)

    symbols = compute_symbols(universe, test_mode=test_mode)
    typer.echo(f"Warming cache for {len(symbols)} symbols over {years}y ({start} → {end})")

    if test_mode:
        from ah_research.integrations.fake import FakeSources

        fake = FakeSources(seed=42)
        sources = fake
    else:
        raise NotImplementedError(
            "live integration clients (Baostock / AKshare) not yet wired; "
            "run with --test-mode or wait for Phase 1 Tasks 1.21/1.22"
        )

    with DuckDBCache(settings.cache_duckdb_path) as cache:
        repo = DataRepository(
            price_source=sources.prices,
            fundamentals_source=sources.fundamentals,
            fx_source=sources.fx,
            calendar_source=sources.calendar,
            sector_source=sources.sectors,
            corp_actions_source=sources.corporate_actions,
            constituents_source=sources.constituents,
            cache=cache,
        )
        repo.get_prices(symbols, start, end)
        repo.get_fundamentals(symbols, start, end)

    typer.echo(f"\n✓ Warmup done. Cache at {settings.cache_duckdb_path}.\n")
