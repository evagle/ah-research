"""Live integration tests — hit the real AKShare API.

Gated by ``AH_RESEARCH_LIVE=1``. Verifies full HK pipeline + FX.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from ah_research.data.converters import convert_prices, normalize_akshare_prices
from ah_research.model.schemas import PriceFrameSchema

pytestmark = pytest.mark.skipif(
    os.environ.get("AH_RESEARCH_LIVE") != "1",
    reason="live integration; set AH_RESEARCH_LIVE=1 to enable",
)


@pytest.fixture(scope="module")
def akshare_client():
    from ah_research.integrations.akshare import AKShareClient

    return AKShareClient()


def test_fetch_hk_prices_tencent(akshare_client):
    df = akshare_client.fetch_prices(["0700.HK"], date(2024, 6, 1), date(2024, 6, 10))
    assert len(df) >= 4
    assert "symbol" in df.columns
    assert df["symbol"].iloc[0] == "0700.HK"


def test_full_pipeline_tencent(akshare_client):
    raw = akshare_client.fetch_prices(["0700.HK"], date(2024, 6, 1), date(2024, 6, 10))
    normalized = normalize_akshare_prices(raw)
    result = convert_prices(normalized, pd.DataFrame())
    PriceFrameSchema.validate(result)
    assert len(result) > 0
    # Tencent traded around 300-400 HKD in mid-2024
    assert 200 < result["close"].mean() < 500
    # HK has no real price limit → hit flags should all be False
    assert not result["hit_limit_up"].any()
    assert not result["hit_limit_down"].any()


def test_fetch_a_share_symbol_returns_empty(akshare_client):
    """A-share symbols are silently skipped (composable with BaostockClient)."""
    df = akshare_client.fetch_prices(["600519.SH"], date(2024, 6, 1), date(2024, 6, 10))
    assert len(df) == 0


def test_fetch_fx_cny_hkd(akshare_client):
    df = akshare_client.fetch_fx("CNY_HKD", date(2024, 6, 1), date(2024, 6, 10))
    assert len(df) >= 4
    assert "rate" in df.columns
    # CNY/HKD around 0.9 in mid-2024 (normalised from per-100 by client)
    assert 0.85 < df["rate"].mean() < 0.95


def test_fetch_fx_unsupported_pair_raises(akshare_client):
    from ah_research.exceptions import SourceDataError

    with pytest.raises(SourceDataError):
        akshare_client.fetch_fx("USD_JPY", date(2024, 6, 1), date(2024, 6, 10))
