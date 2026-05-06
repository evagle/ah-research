"""FundamentalsRepository — second carved-out collaborator from
``DataRepository``.

This module owns the bitemporal fundamentals read with PIT filtering.
A single public method (``get_fundamentals``) plus its private cache-
fetch helper. Holds a reference to the shared ``DuckDBCache`` and the
``FundamentalsSource`` integration. Behaviour-preserving extraction.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from ah_research.data._validation import validate_date_range
from ah_research.data.cache import DuckDBCache
from ah_research.data.converters import convert_fundamentals
from ah_research.integrations import FundamentalsSource
from ah_research.logging import get_logger

log = get_logger(__name__)


class FundamentalsRepository:
    """Domain sub-repository for bitemporal fundamentals reads."""

    def __init__(
        self,
        *,
        fundamentals_source: FundamentalsSource,
        cache: DuckDBCache,
    ) -> None:
        self._fundamentals_source = fundamentals_source
        self._cache = cache

    def get_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
        *,
        asof: date | None = None,
    ) -> pd.DataFrame:
        """Return bitemporal fundamentals, PIT-filtered to ``asof``.

        If ``asof`` is ``None``, defaults to ``end``. Raises
        ``LeakageDetected`` if ``asof > end``.
        """
        validate_date_range(start, end)
        if asof is None:
            asof = end
        elif asof > end:
            from ah_research.exceptions import LeakageDetected

            raise LeakageDetected(f"asof ({asof}) is after end ({end}); that leaks future info")

        if len(symbols) == 0:
            return pd.DataFrame()

        to_fetch = [
            sym
            for sym in symbols
            if not self._cache.has_fundamentals_fetch_covering(sym, start, end)
        ]
        if to_fetch:
            self._fetch_and_cache_fundamentals(to_fetch, start, end)

        return self._cache.read_fundamentals_asof(symbols, asof)

    def _fetch_and_cache_fundamentals(self, symbols: list[str], start: date, end: date) -> None:
        log.info(
            "fetch_fundamentals",
            symbols=symbols,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        raw = self._fundamentals_source.fetch_fundamentals(symbols, start, end)
        if len(raw) > 0:
            converted = convert_fundamentals(raw)
            self._cache.write_fundamentals(converted)
        for sym in symbols:
            self._cache.log_fundamentals_fetch(sym, start, end)
