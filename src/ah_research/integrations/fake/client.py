"""Deterministic fake implementations of every integration Protocol.

Design goals:
- **Deterministic** — seeded RNG, same inputs ⇒ same DataFrame.
- **Schema-shaped** — column names match what real converters expect, so
  converter tests exercise the full pipeline.
- **Bitemporal fundamentals** — each (symbol, report_date) emits a
  ``preliminary`` row (~30d after report) AND an ``audited`` row (~60d
  after report). PIT tests can then verify that a query at date D between
  the two publication dates sees only the preliminary figure.
- **Extensible** — ``corporate_actions`` is an empty frame by default;
  tests opt in via ``FakeSources(preset_actions=...)`` when they need
  specific dividend/split scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

_SECTOR_L1: list[str] = [
    "Financials",
    "Consumer",
    "Technology",
    "Industrials",
    "Energy",
    "Healthcare",
    "Materials",
    "Utilities",
]
_INDEX_SIZES: dict[str, int] = {"CSI300": 300, "HSI": 50, "CSI500": 500}
_CORPORATE_ACTION_COLUMNS: list[str] = ["symbol", "ex_date", "kind", "params_json"]


@dataclass
class FakeSources:
    """Container exposing one fake per Protocol.

    Usage in tests::

        fake = FakeSources(seed=42)
        fake.prices.fetch_prices(...)
        fake.fundamentals.fetch_fundamentals(...)
    """

    seed: int = 42
    preset_actions: pd.DataFrame | None = None

    prices: _FakePrices = field(init=False)
    fundamentals: _FakeFundamentals = field(init=False)
    fx: _FakeFX = field(init=False)
    calendar: _FakeCalendar = field(init=False)
    sectors: _FakeSectors = field(init=False)
    corporate_actions: _FakeCorporateActions = field(init=False)
    constituents: _FakeConstituents = field(init=False)

    def __post_init__(self) -> None:
        self.prices = _FakePrices(self.seed)
        self.fundamentals = _FakeFundamentals(self.seed)
        self.fx = _FakeFX(self.seed)
        self.calendar = _FakeCalendar()
        self.sectors = _FakeSectors()
        self.corporate_actions = _FakeCorporateActions(self.preset_actions)
        self.constituents = _FakeConstituents()


# ── Fakes ────────────────────────────────────────────────────────────────────


class _FakePrices:
    """Geometric-Brownian-motion price path per symbol, seeded per call."""

    def __init__(self, seed: int) -> None:
        self._seed = seed

    def fetch_prices(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        dates = pd.bdate_range(start, end)
        rows: list[dict[str, Any]] = []
        for sym in symbols:
            # Per-symbol deterministic RNG: seed combines global seed + symbol hash
            rng = np.random.default_rng(self._seed + hash(sym) % 2**32)
            base = 100.0 + (hash(sym) % 1000)
            returns = rng.normal(0, 0.01, len(dates))
            prices = base * np.exp(np.cumsum(returns))
            for d, p in zip(dates, prices, strict=True):
                rows.append(
                    {
                        "date": d,
                        "symbol": sym,
                        "open": p * 0.998,
                        "high": p * 1.01,
                        "low": p * 0.99,
                        "close": float(p),
                        "volume": int(1_000_000 + rng.uniform(-100_000, 100_000)),
                        "amount": float(p * 1_000_000),
                        "turnover": 0.01,
                        "is_suspended": False,
                        "is_st": False,
                    }
                )
        return pd.DataFrame(rows)


class _FakeFundamentals:
    """Bitemporal fundamentals: preliminary + audited per quarter."""

    _PRELIM_LAG_DAYS = 30
    _AUDIT_LAG_DAYS = 60

    def __init__(self, seed: int) -> None:
        self._seed = seed

    def fetch_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for sym in symbols:
            for report_dt in self._quarter_ends(start, end):
                rows.append(self._make_row(sym, report_dt, "preliminary"))
                rows.append(self._make_row(sym, report_dt, "audited"))
        return pd.DataFrame(rows)

    def _make_row(self, sym: str, report_dt: date, kind: str) -> dict[str, Any]:
        lag = self._PRELIM_LAG_DAYS if kind == "preliminary" else self._AUDIT_LAG_DAYS
        pub = report_dt + timedelta(days=lag)
        # Audited numbers are slightly revised from preliminary (deterministic fudge).
        revision = 1.0 if kind == "preliminary" else 1.02
        return {
            "symbol": sym,
            "report_date": pd.Timestamp(report_dt),
            "publication_date": pd.Timestamp(pub),
            "known_as_of": pd.Timestamp(pub),
            "statement_kind": kind,
            "revenue": 1e10 * revision,
            "net_income": 3e9 * revision,
            "net_income_ex_nonrecurring": 2.95e9 * revision,
            "operating_cash_flow": 3.5e9 * revision,
            "capex": 2e8,
            "total_assets": 8e10,
            "total_equity": 5e10,
            "total_debt": 1e10,
            "goodwill": 0.0,
            "minority_interest": 1e8,
            "d_and_a": 3e8,
            "working_capital_change": 1e8,
            "pe": 25.0,
            "pb": 8.0,
            "ps": 10.0,
            "ev_ebitda": 15.0,
            "roe": 0.25 * revision,
            "roic": 0.22 * revision,
            "roa": 0.15,
            "gross_margin": 0.92,
            "net_margin": 0.30,
            "dividend_yield": 0.02,
            "market_cap": 2e12,
            "market_cap_free_float": 1.5e12,
            "is_soe": sym.endswith(".SH"),
            "is_stock_connect_eligible": True,
        }

    @staticmethod
    def _quarter_ends(start: date, end: date) -> list[date]:
        """Enumerate calendar quarter ends in [start, end]."""
        ends = [(3, 31), (6, 30), (9, 30), (12, 31)]
        out: list[date] = []
        for year in range(start.year, end.year + 1):
            for month, day in ends:
                d = date(year, month, day)
                if start <= d <= end:
                    out.append(d)
        return out


class _FakeFX:
    def __init__(self, seed: int) -> None:
        self._seed = seed

    def fetch_fx(self, pair: str, start: date, end: date) -> pd.DataFrame:
        rng = np.random.default_rng(self._seed + hash(pair) % 2**32)
        dates = pd.bdate_range(start, end)
        rates = 0.91 + rng.normal(0, 0.005, len(dates))
        return pd.DataFrame({"date": dates, "pair": pair, "rate": rates})


class _FakeCalendar:
    """Weekday-based fake calendar. Does NOT honor national holidays."""

    def fetch_calendar(self, exchange: str, start: date, end: date) -> pd.DataFrame:
        dates = pd.date_range(start, end)
        return pd.DataFrame(
            {
                "exchange": exchange,
                "date": dates,
                "is_trading_day": [d.weekday() < 5 for d in dates],
            }
        )


class _FakeSectors:
    def fetch_sectors(self, symbols: list[str]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for i, s in enumerate(symbols):
            sector = _SECTOR_L1[i % len(_SECTOR_L1)]
            rows.append(
                {
                    "symbol": s,
                    "sector_l1": sector,
                    "sector_l2": f"{sector}-A",
                }
            )
        return pd.DataFrame(rows)


class _FakeCorporateActions:
    """Empty by default. Tests needing specific dividends pass
    ``preset_actions`` to ``FakeSources``."""

    def __init__(self, preset: pd.DataFrame | None) -> None:
        self._preset = preset

    def fetch_corporate_actions(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        if self._preset is None:
            return pd.DataFrame(columns=_CORPORATE_ACTION_COLUMNS)
        df = self._preset
        mask = (
            df["symbol"].isin(symbols)
            & (df["ex_date"] >= pd.Timestamp(start))
            & (df["ex_date"] <= pd.Timestamp(end))
        )
        return df.loc[mask].reset_index(drop=True)


class _FakeConstituents:
    """PIT semantics: returns ``N`` deterministic members per index, all with
    ``effective_from`` earlier than any reasonable ``asof``.

    Tests that need membership turnover over time should use
    ``repo.get_universe_over_time`` and compose multiple asof snapshots.
    """

    def fetch_constituents(self, index: str, asof: date) -> pd.DataFrame:
        n = _INDEX_SIZES.get(index, 100)
        exchange = "HK" if index == "HSI" else "SH"
        code_fmt = "{:04d}" if exchange == "HK" else "{:06d}"
        symbols = [f"{code_fmt.format(i + 1)}.{exchange}" for i in range(n)]
        return pd.DataFrame(
            {
                "index": index,
                "symbol": symbols,
                "weight": [1.0 / n] * n,
                "asof": [pd.Timestamp(asof)] * n,
            }
        )
