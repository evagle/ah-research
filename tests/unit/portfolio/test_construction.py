"""Tests for portfolio construction primitives."""

import numpy as np
import pandas as pd
import pytest

from ah_research.portfolio.construction import (
    cap_at,
    sector_neutralize,
    signal_to_weights,
    top_quantile_weights,
)


def _signals(values: dict[str, float], d: str = "2024-01-31") -> pd.DataFrame:
    rows = [{"date": pd.Timestamp(d), "symbol": s, "signal": v} for s, v in values.items()]
    return pd.DataFrame(rows)


def test_top_quantile_selects_top_20pct() -> None:
    sig = _signals({f"60000{i}.SH": float(i) for i in range(10)})
    out = top_quantile_weights(sig, quantile=0.2)
    # top 2 of 10 = symbols with signals 8 and 9
    assert set(out["symbol"]) == {"600008.SH", "600009.SH"}
    # equal weight
    assert np.allclose(out["weight"].to_numpy(), 0.5)


def test_cap_at_caps_and_redistributes() -> None:
    # sum to 1 but single weight > cap
    w = pd.DataFrame(
        {
            "date": pd.Timestamp("2024-01-31"),
            "symbol": ["a", "b", "c"],
            "weight": [0.6, 0.3, 0.1],
        }
    )
    out = cap_at(w, max_weight=0.4)
    # a capped at 0.4, residue 0.2 redistributed pro-rata to b and c
    assert out.loc[out.symbol == "a", "weight"].item() == pytest.approx(0.4)
    assert out["weight"].sum() == pytest.approx(1.0)


def test_sector_neutralize_equalizes_sector_exposure() -> None:
    w = pd.DataFrame(
        {
            "date": pd.Timestamp("2024-01-31"),
            "symbol": ["a", "b", "c", "d"],
            "weight": [0.5, 0.3, 0.1, 0.1],
        }
    )
    sectors = pd.DataFrame(
        {
            "symbol": ["a", "b", "c", "d"],
            "sector_l1": ["tech", "tech", "finance", "finance"],
        }
    )
    out = sector_neutralize(w, sectors)
    # after neutralization, each sector has equal total weight = 0.5
    merged = out.merge(sectors, on="symbol")
    sector_sums = merged.groupby("sector_l1")["weight"].sum()
    assert np.allclose(sector_sums["tech"], sector_sums["finance"])


def test_signal_to_weights_top_quantile_composite() -> None:
    sig = _signals({f"60000{i}.SH": float(i) for i in range(10)})
    out = signal_to_weights(sig, method="top_quantile", quantile=0.2, max_weight=0.6)
    # 2 names, equal weight 0.5 each, both below cap 0.6 — untouched
    assert len(out) == 2
    assert all(out["weight"] == 0.5)
