"""ConfigRepository — third carved-out collaborator from ``DataRepository``.

This module owns the *configuration / metadata* reads:

* ``get_index_constituents`` -- PIT-correct membership at a date.
* ``get_universe_over_time`` -- survivorship-free rebalance-sample
  membership frame (drives back-test universe iteration).
* ``get_sector`` -- current SWS / industry classification.

Holds a reference to the shared ``DuckDBCache`` and the two metadata
integration sources. Behaviour-preserving extraction.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from ah_research.data._validation import validate_date_range
from ah_research.data.cache import DuckDBCache
from ah_research.integrations import ConstituentsSource, SectorSource
from ah_research.logging import get_logger

log = get_logger(__name__)


class ConfigRepository:
    """Domain sub-repository for index constituents, universe-over-time,
    and sector classification."""

    def __init__(
        self,
        *,
        constituents_source: ConstituentsSource,
        sector_source: SectorSource,
        cache: DuckDBCache,
    ) -> None:
        self._constituents_source = constituents_source
        self._sector_source = sector_source
        self._cache = cache

    # ── index constituents ─────────────────────────────────────────────────

    def get_index_constituents(self, index: str, asof: date) -> pd.DataFrame:
        """Return PIT-correct constituents of ``index`` at ``asof``.

        On a cache miss, fetches one snapshot from the constituents source
        and writes it as an open-ended membership anchored at ``asof``.
        """
        if not self._cache.has_constituents_fetch(index, asof):
            self._fetch_and_cache_constituents(index, asof)
        return self._cache.read_constituents_asof(index, asof)

    def _fetch_and_cache_constituents(self, index: str, asof: date) -> None:
        log.info("fetch_constituents", index=index, asof=asof.isoformat())
        raw = self._constituents_source.fetch_constituents(index, asof)
        if len(raw) > 0:
            cache_rows = pd.DataFrame(
                {
                    "index_name": index,
                    "symbol": raw["symbol"],
                    "weight": raw["weight"],
                    "effective_from": pd.Timestamp(asof),
                    "effective_to": pd.NaT,
                }
            )
            self._cache.write_constituents(cache_rows)
        self._cache.log_constituents_fetch(index, asof)

    # ── universe over time (survivorship-free) ────────────────────────────

    def get_universe_over_time(
        self,
        index: str,
        start: date,
        end: date,
        *,
        freq: str = "ME",
    ) -> pd.DataFrame:
        """Return a long-format DataFrame of ``(date, symbol)`` rows giving
        the PIT-correct members of ``index`` at each sampled date.

        ``freq`` is a pandas offset alias (default month-end ``ME``). This
        is the survivorship-free driver for back-tests.
        """
        validate_date_range(start, end)
        sample_dates = pd.date_range(start, end, freq=freq)
        rows: list[pd.DataFrame] = []
        for ts in sample_dates:
            asof = ts.date()
            snapshot = self.get_index_constituents(index, asof)
            if len(snapshot) == 0:
                continue
            rows.append(
                pd.DataFrame(
                    {
                        "date": pd.Timestamp(asof),
                        "index_name": index,
                        "symbol": snapshot["symbol"].to_numpy(),
                        "weight": snapshot["weight"].to_numpy(),
                    }
                )
            )
        if not rows:
            return pd.DataFrame(columns=["date", "index_name", "symbol", "weight"])
        return pd.concat(rows, ignore_index=True)

    # ── sectors ────────────────────────────────────────────────────────────

    def get_sector(self, symbols: list[str]) -> pd.DataFrame:
        """Return the current SWS / industry classification for ``symbols``.

        Sector tags are effectively static (they change only on
        reclassification events which we don't model), so one fetch per
        symbol suffices.
        """
        if len(symbols) == 0:
            return pd.DataFrame(columns=["symbol", "sector_l1", "sector_l2"])
        cached = self._cache.read_sectors(symbols)
        cached_set = set(cached["symbol"].tolist()) if len(cached) > 0 else set()
        missing = [s for s in symbols if s not in cached_set]
        if missing:
            raw = self._sector_source.fetch_sectors(missing)
            if len(raw) > 0:
                self._cache.write_sectors(raw)
        return self._cache.read_sectors(symbols)
