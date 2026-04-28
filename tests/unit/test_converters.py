"""Tests for data/converters.py — back-adjustment, total-return, price-limit
detection, and pandera-validated domain conversion.
"""

import json

import pandas as pd
import pytest

from ah_research.data.converters import (
    compute_adjusted_prices,
    convert_fundamentals,
    convert_prices,
)
from ah_research.model.schemas import FundamentalsFrameSchema, PriceFrameSchema


def _raw_source_df(symbol: str = "600519.SH", is_st: bool = False) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "symbol": [symbol] * 3,
            "open": [1700.0, 1710.0, 1690.0],
            "high": [1720.0, 1715.0, 1710.0],
            "low": [1695.0, 1700.0, 1680.0],
            "close": [1710.0, 1705.0, 1700.0],
            "volume": [1_000_000, 900_000, 950_000],
            "amount": [1.7e9, 1.5e9, 1.6e9],
            "turnover": [0.001, 0.001, 0.001],
            "is_suspended": [False, False, False],
            "is_st": [is_st] * 3,
        }
    )


def _action_row(kind: str, ex_date: str, params: dict, symbol: str = "600519.SH") -> dict:
    return {
        "symbol": symbol,
        "ex_date": pd.Timestamp(ex_date),
        "kind": kind,
        "params_json": json.dumps(params),
    }


# ── compute_adjusted_prices ──────────────────────────────────────────────────


def test_no_actions_is_identity_for_hfq_and_tr():
    raw = _raw_source_df()
    result = compute_adjusted_prices(raw, pd.DataFrame())
    assert (result["close_hfq"] == result["close"]).all()
    assert (result["total_return"] == result["close"]).all()


def test_cash_dividend_scales_pre_ex_close_hfq_down():
    """Cash dividend on 2024-01-03 of 30 per share, prev_close = 1710.
    hfq factor = (1710 - 30) / 1710 ≈ 0.9825.
    Day 1 close_hfq should be 1710 * 0.9825 ≈ 1680.
    Day 2, 3 close_hfq should equal close (unchanged).
    """
    raw = _raw_source_df()
    actions = pd.DataFrame([_action_row("cash_dividend", "2024-01-03", {"amount_per_share": 30.0})])
    result = compute_adjusted_prices(raw, actions)

    day1 = result[result["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]
    day3 = result[result["date"] == pd.Timestamp("2024-01-04")].iloc[0]

    expected_factor = (1710.0 - 30.0) / 1710.0
    assert day1["close_hfq"] == pytest.approx(1710.0 * expected_factor, rel=1e-9)
    assert day2["close_hfq"] == 1705.0
    assert day3["close_hfq"] == 1700.0


def test_cash_dividend_reinvests_into_total_return():
    """TR factor = 1 + div / prev_close. Post-ex-date TR is scaled UP."""
    raw = _raw_source_df()
    actions = pd.DataFrame([_action_row("cash_dividend", "2024-01-03", {"amount_per_share": 30.0})])
    result = compute_adjusted_prices(raw, actions)

    day1 = result[result["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]

    tr_factor = 1.0 + 30.0 / 1710.0
    assert day1["total_return"] == pytest.approx(1710.0, rel=1e-9)
    assert day2["total_return"] == pytest.approx(1705.0 * tr_factor, rel=1e-9)


def test_split_2_for_1_halves_pre_close_hfq():
    """ratio = shares_after / shares_before = 2 (2-for-1).
    Pre-ex prices scale by 1/ratio = 0.5.
    """
    raw = _raw_source_df()
    actions = pd.DataFrame([_action_row("split", "2024-01-03", {"ratio": 2.0})])
    result = compute_adjusted_prices(raw, actions)

    day1 = result[result["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]

    assert day1["close_hfq"] == pytest.approx(1710.0 * 0.5, rel=1e-9)
    assert day2["close_hfq"] == 1705.0  # unchanged


def test_multiple_actions_compose_multiplicatively():
    """Two dividends on different dates must compose: pre-first-ex prices
    carry BOTH factors; between the two, prices carry only the later factor;
    after both, prices are unchanged.
    """
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
            ),
            "symbol": ["600519.SH"] * 5,
            "open": [100.0] * 5,
            "high": [105.0] * 5,
            "low": [95.0] * 5,
            "close": [100.0, 100.0, 100.0, 100.0, 100.0],
            "volume": [1_000_000] * 5,
            "amount": [1e8] * 5,
            "turnover": [0.01] * 5,
            "is_suspended": [False] * 5,
            "is_st": [False] * 5,
        }
    )
    actions = pd.DataFrame(
        [
            _action_row("cash_dividend", "2024-01-04", {"amount_per_share": 5.0}),
            _action_row("cash_dividend", "2024-01-08", {"amount_per_share": 10.0}),
        ]
    )
    result = compute_adjusted_prices(raw, actions)

    f1 = 95.0 / 100.0  # first div factor: (100 - 5) / 100
    f2 = 90.0 / 100.0  # second div factor: (100 - 10) / 100

    # Pre both ex-dates: prices carry BOTH factors
    assert result.iloc[0]["close_hfq"] == pytest.approx(100.0 * f1 * f2, rel=1e-9)
    assert result.iloc[1]["close_hfq"] == pytest.approx(100.0 * f1 * f2, rel=1e-9)
    # After first, before second: prices carry only the later factor
    assert result.iloc[2]["close_hfq"] == pytest.approx(100.0 * f2, rel=1e-9)
    assert result.iloc[3]["close_hfq"] == pytest.approx(100.0 * f2, rel=1e-9)
    # After both: prices unchanged
    assert result.iloc[4]["close_hfq"] == 100.0


def test_action_with_no_pre_prices_is_ignored():
    """If an action's ex-date is on or before the first price we have, there
    is no prev_close, so we skip rather than divide by zero."""
    raw = _raw_source_df()
    actions = pd.DataFrame([_action_row("cash_dividend", "2024-01-01", {"amount_per_share": 30.0})])
    result = compute_adjusted_prices(raw, actions)
    # Nothing adjusted because ex_date < first price date
    assert (result["close_hfq"] == result["close"]).all()


# ── convert_prices (full pipeline, pandera-validated) ────────────────────────


def test_convert_prices_passes_pandera():
    raw = _raw_source_df()
    result = convert_prices(raw, pd.DataFrame())
    PriceFrameSchema.validate(result)


def test_convert_prices_a_share_non_st_uses_10pct_limit():
    raw = _raw_source_df(is_st=False)
    result = convert_prices(raw, pd.DataFrame())
    # Day 2 prev_close = 1710, so limit_up = 1710 * 1.10 = 1881
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert day2["limit_up"] == pytest.approx(1881.0, abs=0.01)
    assert day2["limit_down"] == pytest.approx(1539.0, abs=0.01)


def test_convert_prices_a_share_st_uses_5pct_limit():
    raw = _raw_source_df(is_st=True)
    result = convert_prices(raw, pd.DataFrame())
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]
    # ST limit is ±5%: 1710 * 1.05 = 1795.5
    assert day2["limit_up"] == pytest.approx(1795.5, abs=0.01)
    assert day2["limit_down"] == pytest.approx(1624.5, abs=0.01)


def test_convert_prices_chinext_uses_20pct_limit():
    raw = _raw_source_df(symbol="300750.SZ")  # ChiNext code starts with 300
    result = convert_prices(raw, pd.DataFrame())
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]
    # ChiNext limit is ±20%: 1710 * 1.20 = 2052.0
    assert day2["limit_up"] == pytest.approx(2052.0, abs=0.01)


def test_convert_prices_star_market_uses_20pct_limit():
    raw = _raw_source_df(symbol="688001.SH")  # STAR Market code starts with 688
    result = convert_prices(raw, pd.DataFrame())
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert day2["limit_up"] == pytest.approx(2052.0, abs=0.01)


def test_convert_prices_hk_has_no_real_limit():
    raw = _raw_source_df(symbol="0700.HK")
    result = convert_prices(raw, pd.DataFrame())
    # HK sentinel: limit_up very large, limit_down effectively zero.
    # hit_limit_up should always be False under any realistic high price.
    assert not result["hit_limit_up"].any()
    assert not result["hit_limit_down"].any()


def test_convert_prices_flags_hit_limit_up():
    """Day 2 open at 1881, high = 1881 (= limit_up for 1710 prev close).
    hit_limit_up should be True for day 2.
    """
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "symbol": ["600519.SH"] * 2,
            "open": [1700.0, 1881.0],
            "high": [1720.0, 1881.0],  # hits limit_up
            "low": [1695.0, 1881.0],
            "close": [1710.0, 1881.0],
            "volume": [1_000_000, 900_000],
            "amount": [1.7e9, 1.5e9],
            "turnover": [0.001, 0.001],
            "is_suspended": [False, False],
            "is_st": [False, False],
        }
    )
    result = convert_prices(raw, pd.DataFrame())
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert bool(day2["hit_limit_up"]) is True


def test_convert_prices_flags_hit_limit_down():
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "symbol": ["600519.SH"] * 2,
            "open": [1700.0, 1539.0],
            "high": [1720.0, 1539.0],
            "low": [1695.0, 1539.0],
            "close": [1710.0, 1539.0],
            "volume": [1_000_000, 900_000],
            "amount": [1.7e9, 1.5e9],
            "turnover": [0.001, 0.001],
            "is_suspended": [False, False],
            "is_st": [False, False],
        }
    )
    result = convert_prices(raw, pd.DataFrame())
    day2 = result[result["date"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert bool(day2["hit_limit_down"]) is True


def test_convert_prices_first_row_does_not_hit_limits():
    """With no prev_close we can't compute a limit; the first row must report
    no-hit regardless of price movement."""
    raw = _raw_source_df()
    result = convert_prices(raw, pd.DataFrame())
    day1 = result[result["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert bool(day1["hit_limit_up"]) is False
    assert bool(day1["hit_limit_down"]) is False


# ── convert_fundamentals ─────────────────────────────────────────────────────


def _raw_fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "600519.SH",
                "report_date": pd.Timestamp("2024-03-31"),
                "publication_date": pd.Timestamp("2024-04-28"),
                "known_as_of": pd.Timestamp("2024-04-28"),
                "statement_kind": "audited",
                "revenue": 1e10,
                "net_income": 3e9,
                "net_income_ex_nonrecurring": 2.95e9,
                "operating_cash_flow": 3.5e9,
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
                "roe": 0.25,
                "roic": 0.22,
                "roa": 0.15,
                "gross_margin": 0.92,
                "net_margin": 0.30,
                "dividend_yield": 0.02,
                "market_cap": 2e12,
                "market_cap_free_float": 1.5e12,
                "is_soe": True,
                "is_stock_connect_eligible": True,
            }
        ]
    )


def test_convert_fundamentals_passes_schema():
    result = convert_fundamentals(_raw_fundamentals())
    FundamentalsFrameSchema.validate(result)


def test_convert_fundamentals_defaults_known_as_of_to_publication_date():
    raw = _raw_fundamentals().drop(columns=["known_as_of"])
    result = convert_fundamentals(raw)
    assert (result["known_as_of"] == result["publication_date"]).all()


def test_convert_fundamentals_defaults_statement_kind_to_audited():
    raw = _raw_fundamentals().drop(columns=["statement_kind"])
    result = convert_fundamentals(raw)
    assert (result["statement_kind"] == "audited").all()
