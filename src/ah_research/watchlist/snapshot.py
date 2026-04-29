"""WatchlistSnapshot dataclass — point-in-time metrics for a watchlist."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class WatchlistSnapshot:
    """Immutable point-in-time snapshot of fundamental + price metrics.

    Attributes
    ----------
    watchlist_name:
        The name of the watchlist this snapshot belongs to.
    snapshot_date:
        The ``asof`` date the metrics were fetched for.
    rows:
        DataFrame with one row per symbol.  Columns include ``symbol``
        plus any available metrics: ``pe``, ``pb``, ``dividend_yield``,
        ``roe``, ``market_cap``, ``sector_l1``, ``price``.
    """

    watchlist_name: str
    snapshot_date: date
    rows: pd.DataFrame
