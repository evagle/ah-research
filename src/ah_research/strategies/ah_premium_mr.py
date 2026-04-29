"""AH premium mean-reversion strategy (WeightStrategy).

Trades dual-listed AH pairs by entering when the rolling z-score of the
A/H premium falls below -entry_z (A-leg cheap) and exiting when |z| < exit_z.
Positions are always long A-leg / short H-leg; the reverse (A rich) is skipped
because shorting A-shares is not permitted in the CSI framework.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from ah_research.backtest.types import Weights
from ah_research.data.ah_pairs import load_ah_pairs
from ah_research.data.repository import DataRepository
from ah_research.model.types import AHPair

log = logging.getLogger(__name__)

# Frequency alias for weekly Friday rebalance dates.
_WEEKLY_FREQ = "W-FRI"


@dataclass
class AHPremiumMeanReversionStrategy:
    """AH-premium mean-reversion strategy operating on dual-listed AH pairs.

    For each weekly rebalance date ``d``:

    1. Fetch ``lookback_days`` of daily close prices for each pair's A and H legs
       plus the CNY/HKD FX rate.
    2. Compute ``premium = close_A / (close_H * fx_cny_per_hkd) - 1`` daily.
       Note: ``get_fx_series("CNY_HKD")`` returns CNY-per-HKD (1 HKD = rate CNY),
       so ``close_H * rate`` converts H-close to CNY.
    3. Compute rolling 60-day z-score of premium ending at ``d``.
    4. Entry rule: ``z < -entry_z``  →  long A-leg (+leg_weight), short H-leg (-leg_weight).
    5. Skip rule:  ``z > +entry_z``  →  emit zero weight and log a structured WARNING
       (shorting A-shares is not permitted).
    6. Exit rule for open pairs: ``|z| < exit_z``  →  target weight 0 (unwind).
    7. Carry-forward: open pairs with ``-entry_z ≤ z < -exit_z``  →  hold last weights.
    8. Aggregate gross exposure across all open pairs; if it exceeds ``max_gross``,
       shrink all pair weights proportionally.

    State is stored in ``_open_pairs`` (a dict mapping pair name → weights dict) and
    is reset at the beginning of each call to ``generate()``.

    Recommended engine config: ``rebalance="W"``, ``allow_short=True``.
    """

    entry_z: float = 2.0
    exit_z: float = 0.5
    leg_weight: float = 0.05
    max_gross: float = 0.20
    lookback_days: int = 60
    name: str = field(default="ah_premium_mr")
    # AH premium strategy uses only price data and FX; no fundamentals.
    uses_fundamentals: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        # Mutable state: dict of pair_name -> {a_sym: float, h_sym: float}
        self._open_pairs: dict[str, dict[str, float]] = {}

    def generate(self, repo: DataRepository, start: date, end: date) -> Weights:
        """Generate weekly pair weights over [start, end]."""
        # Reset state for each fresh generate() call so successive calls are idempotent.
        self._open_pairs = {}

        pairs = load_ah_pairs()
        if not pairs:
            return _empty_weights()

        rebalance_dates = _weekly_rebalance_dates(start, end)
        all_rows: list[pd.DataFrame] = []

        for rb_date in rebalance_dates:
            # Fetch lookback window ending at rb_date
            lookback_start = date(
                rb_date.year - 1 if rb_date.month < 3 else rb_date.year,
                (rb_date.month - 3) % 12 + 1 if rb_date.month > 3 else rb_date.month + 9,
                1,
            )
            # Simpler: go back lookback_days * 1.5 calendar days to get enough trading days
            lookback_start = date.fromordinal(rb_date.toordinal() - int(self.lookback_days * 1.8))

            day_weights: dict[str, float] = {}

            for pair in pairs:
                a_sym = str(pair.a_symbol)
                h_sym = str(pair.h_symbol)
                pair_name = f"{a_sym}/{h_sym}"

                z = self._compute_z(repo, pair, lookback_start, rb_date)
                if z is None:
                    # Insufficient data — carry forward existing position if open
                    if pair_name in self._open_pairs:
                        for sym, w in self._open_pairs[pair_name].items():
                            day_weights[sym] = day_weights.get(sym, 0.0) + w
                    continue

                currently_open = pair_name in self._open_pairs

                if currently_open and abs(z) < self.exit_z:
                    # Exit: close the pair
                    del self._open_pairs[pair_name]

                elif not currently_open and z < -self.entry_z:
                    # Entry: A cheap, H rich → long A, short H
                    self._open_pairs[pair_name] = {
                        a_sym: self.leg_weight,
                        h_sym: -self.leg_weight,
                    }
                    for sym, w in self._open_pairs[pair_name].items():
                        day_weights[sym] = day_weights.get(sym, 0.0) + w

                elif not currently_open and z > self.entry_z:
                    # A rich, H cheap → would require shorting A-shares — skip.
                    log.warning(
                        "ah_premium_mr: pair %s has z=%.2f > +%.1f (A rich); "
                        "skipping (A-share short not permitted)",
                        pair_name,
                        z,
                        self.entry_z,
                    )
                    # Emit zero weights (implicitly — no entry added to day_weights)

                elif currently_open and -self.entry_z <= z < -self.exit_z:
                    # Carry forward existing position
                    for sym, w in self._open_pairs[pair_name].items():
                        day_weights[sym] = day_weights.get(sym, 0.0) + w

            if not day_weights:
                continue

            # Gross exposure cap
            gross = sum(abs(w) for w in day_weights.values())
            if gross > self.max_gross and gross > 0:
                scale = self.max_gross / gross
                day_weights = {s: w * scale for s, w in day_weights.items()}
                # Also scale open-pair state to keep it consistent
                for pname in self._open_pairs:
                    self._open_pairs[pname] = {
                        s: w * scale for s, w in self._open_pairs[pname].items()
                    }

            rows = [
                {"date": pd.Timestamp(rb_date), "symbol": sym, "weight": w}
                for sym, w in day_weights.items()
                if w != 0.0
            ]
            if rows:
                all_rows.append(pd.DataFrame(rows))

        if not all_rows:
            return _empty_weights()

        df = pd.concat(all_rows, ignore_index=True)
        return Weights.from_dataframe(df)

    def _compute_z(
        self,
        repo: DataRepository,
        pair: AHPair,
        lookback_start: date,
        as_of: date,
    ) -> float | None:
        """Return the rolling z-score of the AH premium at ``as_of``.

        Returns ``None`` if there is insufficient data to compute a stable z-score
        (fewer than ``lookback_days // 2`` observations after the join).
        """
        a_sym = str(pair.a_symbol)
        h_sym = str(pair.h_symbol)

        a_prices = repo.get_prices([a_sym], lookback_start, as_of)
        h_prices = repo.get_prices([h_sym], lookback_start, as_of)
        fx = repo.get_fx_series("CNY_HKD", lookback_start, as_of)

        if a_prices.empty or h_prices.empty or fx.empty:
            return None

        a_slim = a_prices[["date", "close"]].rename(columns={"close": "close_a"})
        h_slim = h_prices[["date", "close"]].rename(columns={"close": "close_h"})
        # CNY_HKD: rate is CNY-per-HKD so close_H (HKD) * rate = close_H in CNY.
        # This matches DataRepository.compute_ah_premium's convention.
        fx_slim = fx[["date", "rate"]].rename(columns={"rate": "fx_rate"})

        # Normalise all datetime columns to the same resolution (ns) to avoid
        # pandas MergeError when mixing datetime64[ns] and datetime64[us].
        for df in (a_slim, h_slim, fx_slim):
            df["date"] = df["date"].astype("datetime64[ns]")

        merged = a_slim.merge(h_slim, on="date", how="inner").sort_values("date")
        merged = pd.merge_asof(merged, fx_slim.sort_values("date"), on="date", direction="backward")
        merged = merged.dropna(subset=["fx_rate"])

        if len(merged) < max(10, self.lookback_days // 2):
            return None

        merged["premium"] = merged["close_a"] / (merged["close_h"] * merged["fx_rate"]) - 1.0

        rolling = merged["premium"].rolling(
            window=self.lookback_days, min_periods=max(10, self.lookback_days // 2)
        )
        roll_mean = rolling.mean()
        roll_std = rolling.std()

        last_prem = merged["premium"].iloc[-1]
        mean_val = roll_mean.iloc[-1]
        std_val = roll_std.iloc[-1]

        if pd.isna(mean_val) or pd.isna(std_val) or std_val < 1e-10:
            return None

        return float((last_prem - mean_val) / std_val)


# ── helpers ───────────────────────────────────────────────────────────────────


def _weekly_rebalance_dates(start: date, end: date) -> list[date]:
    """Return Friday rebalance dates within [start, end]."""
    idx = pd.date_range(start, end, freq=_WEEKLY_FREQ)
    return [ts.date() for ts in idx]


def _empty_weights() -> Weights:
    return Weights.from_dataframe(
        pd.DataFrame(
            {
                "date": pd.Series([], dtype="datetime64[ns]"),
                "symbol": pd.Series([], dtype=str),
                "weight": pd.Series([], dtype=float),
            }
        )
    )
