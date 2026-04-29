"""Portfolio construction primitives used by SignalStrategy.to_weights()."""

from __future__ import annotations

from typing import Literal

import pandas as pd


def top_quantile_weights(
    signals: pd.DataFrame,
    quantile: float,
    long_only: bool = True,
) -> pd.DataFrame:
    """Select top ``quantile`` fraction of symbols by signal per date; equal-weight.

    Args:
        signals: DataFrame with columns [date, symbol, signal].
        quantile: Fraction of universe to select, in (0, 1].
        long_only: If True, only long positions are generated (ignored currently,
            reserved for future short-side extension).

    Returns:
        DataFrame with columns [date, symbol, weight].
    """
    if not 0 < quantile <= 1.0:
        raise ValueError(f"quantile must be in (0, 1], got {quantile}")
    out_rows: list[pd.DataFrame] = []
    for _d, grp in signals.groupby("date"):
        n = len(grp)
        k = max(1, round(n * quantile))
        top = grp.nlargest(k, "signal").copy()
        top["weight"] = 1.0 / k
        out_rows.append(top[["date", "symbol", "weight"]])
    return pd.concat(out_rows, ignore_index=True)


def cap_at(weights: pd.DataFrame, max_weight: float) -> pd.DataFrame:
    """Cap each weight at ``max_weight``; redistribute excess pro-rata to uncapped names."""
    result: list[pd.DataFrame] = []
    for _d, grp in weights.groupby("date"):
        w = grp["weight"].to_numpy().copy().astype(float)
        while True:
            over = w > max_weight
            if not over.any():
                break
            excess = float((w[over] - max_weight).sum())
            w[over] = max_weight
            under_mask = (w < max_weight) & (w > 0)
            if not under_mask.any():
                break
            under_sum = float(w[under_mask].sum())
            if under_sum == 0:
                break
            w[under_mask] += excess * (w[under_mask] / under_sum)
        new = grp.copy()
        new["weight"] = w
        result.append(new)
    return pd.concat(result, ignore_index=True)


def sector_neutralize(weights: pd.DataFrame, sectors: pd.DataFrame) -> pd.DataFrame:
    """Rescale weights within each sector so every sector has equal total weight."""
    merged = weights.merge(sectors[["symbol", "sector_l1"]], on="symbol", how="left")
    results: list[pd.DataFrame] = []
    for _d, grp in merged.groupby("date"):
        sector_counts = grp.groupby("sector_l1")["weight"].transform("sum")
        n_sectors = grp["sector_l1"].nunique()
        target_sector_weight = 1.0 / n_sectors
        grp = grp.copy()
        grp["weight"] = grp["weight"] / sector_counts * target_sector_weight
        results.append(grp[["date", "symbol", "weight"]])
    return pd.concat(results, ignore_index=True)


def signal_to_weights(
    signals: pd.DataFrame,
    method: Literal["top_quantile"],
    quantile: float = 0.2,
    max_weight: float = 0.05,
    sector_neutral: bool = False,
    sectors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compose: top_quantile_weights → sector_neutralize? → cap_at.

    Args:
        signals: DataFrame with columns [date, symbol, signal].
        method: Construction method; currently only ``"top_quantile"`` is supported.
        quantile: Fraction of universe to select.
        max_weight: Maximum weight per name after redistribution.
        sector_neutral: If True, equalize sector exposures before capping.
        sectors: Required when ``sector_neutral=True``; DataFrame with
            columns [symbol, sector_l1].

    Returns:
        DataFrame with columns [date, symbol, weight].
    """
    if method != "top_quantile":
        raise NotImplementedError(f"method={method!r} is not implemented")
    w = top_quantile_weights(signals, quantile=quantile)
    if sector_neutral:
        if sectors is None:
            raise ValueError("sector_neutral=True requires a sectors DataFrame")
        w = sector_neutralize(w, sectors)
    w = cap_at(w, max_weight=max_weight)
    return w


__all__ = [
    "cap_at",
    "sector_neutralize",
    "signal_to_weights",
    "top_quantile_weights",
]
