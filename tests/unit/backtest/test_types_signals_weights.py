"""Tests for Signals and Weights wrapper types."""

import pandas as pd
import pandera.errors
import pytest

from ah_research.backtest.types import Signals, Weights


def test_signals_accepts_valid_df() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "symbol": ["600000.SH", "000001.SZ"],
            "signal": [0.1, -0.2],
        }
    )
    s = Signals.from_dataframe(df)
    assert len(s.df) == 2


def test_signals_rejects_bad_symbol() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "symbol": ["BADSYM"],
            "signal": [0.1],
        }
    )
    with pytest.raises(pandera.errors.SchemaError):
        Signals.from_dataframe(df)


def test_signals_rejects_dupes() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "symbol": ["600000.SH", "600000.SH"],
            "signal": [0.1, 0.2],
        }
    )
    with pytest.raises(pandera.errors.SchemaError):
        Signals.from_dataframe(df)


def test_weights_allows_negative_weight() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "symbol": ["600000.SH", "0001.HK"],
            "weight": [0.5, -0.5],
        }
    )
    w = Weights.from_dataframe(df)
    assert w.df["weight"].sum() == 0.0


def test_weights_rejects_nan() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "symbol": ["600000.SH"],
            "weight": [float("nan")],
        }
    )
    with pytest.raises(pandera.errors.SchemaError):
        Weights.from_dataframe(df)
