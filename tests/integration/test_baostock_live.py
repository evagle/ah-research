"""Live integration tests — hit the real Baostock API.

Gated by ``AH_RESEARCH_LIVE=1`` so CI and routine local test runs don't
require network. Verifies the full pipeline:
    Baostock → normalize_baostock_prices → convert_prices → PriceFrameSchema
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from ah_research.data.converters import convert_prices, normalize_baostock_prices
from ah_research.model.schemas import PriceFrameSchema

pytestmark = pytest.mark.skipif(
    os.environ.get("AH_RESEARCH_LIVE") != "1",
    reason="live integration; set AH_RESEARCH_LIVE=1 to enable",
)


@pytest.fixture(scope="module")
def baostock_client():
    from ah_research.integrations.baostock import BaostockClient

    client = BaostockClient()
    yield client
    client.close()


def test_fetch_prices_moutai(baostock_client):
    df = baostock_client.fetch_prices(["600519.SH"], date(2024, 6, 1), date(2024, 6, 10))
    assert len(df) >= 4  # at least 4 trading days in that window
    assert {"date", "symbol", "open", "high", "low", "close"} <= set(df.columns)


def test_full_pipeline_moutai(baostock_client):
    """Source → normalize → convert → schema-valid."""
    raw = baostock_client.fetch_prices(["600519.SH"], date(2024, 6, 1), date(2024, 6, 10))
    normalized = normalize_baostock_prices(raw)
    result = convert_prices(normalized, pd.DataFrame())
    PriceFrameSchema.validate(result)
    assert len(result) > 0
    # Moutai closed around 1500-1700 in mid-2024
    assert 1000 < result["close"].mean() < 2500


def test_fetch_prices_multi_symbol(baostock_client):
    df = baostock_client.fetch_prices(
        ["600519.SH", "000001.SZ"], date(2024, 6, 1), date(2024, 6, 10)
    )
    assert set(df["symbol"].unique()) == {"600519.SH", "000001.SZ"}


def test_fetch_prices_hk_symbol_returns_empty(baostock_client):
    """HK symbols are silently skipped (composable with AKShareClient)."""
    df = baostock_client.fetch_prices(["0700.HK"], date(2024, 6, 1), date(2024, 6, 10))
    assert len(df) == 0


def test_fetch_calendar(baostock_client):
    df = baostock_client.fetch_calendar("SH", date(2024, 6, 1), date(2024, 6, 15))
    assert len(df) == 15
    assert "is_trading_day" in df.columns
    # 2024-06-01 Saturday should be non-trading
    sat = df[df["date"] == pd.Timestamp("2024-06-01")]
    assert not bool(sat["is_trading_day"].iloc[0])


def test_fetch_constituents_csi300(baostock_client):
    df = baostock_client.fetch_constituents("CSI300", date(2024, 6, 30))
    assert len(df) == 300
    assert "symbol" in df.columns
    # All symbols should be SH or SZ
    assert df["symbol"].str.endswith((".SH", ".SZ")).all()


def test_fetch_corporate_actions_moutai_has_dividends(baostock_client):
    """Moutai pays large annual dividends; 2023 should show up."""
    df = baostock_client.fetch_corporate_actions(
        ["600519.SH"], date(2023, 1, 1), date(2024, 12, 31)
    )
    assert len(df) >= 1
    assert {"symbol", "ex_date", "kind", "params_json"} <= set(df.columns)
    assert df["kind"].iloc[0] == "cash_dividend"
