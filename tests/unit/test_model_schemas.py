import pandas as pd
import pandera.pandas as pa
import pytest

from ah_research.model.schemas import (
    CorporateActionSchema,
    FundamentalsFrameSchema,
    PriceFrameSchema,
    TradingCalendarSchema,
)

# ── PriceFrameSchema ─────────────────────────────────────────────────────────


def _valid_price_row() -> dict:
    return {
        "date": pd.Timestamp("2024-06-15"),
        "symbol": "600519.SH",
        "open": 1700.0,
        "high": 1720.0,
        "low": 1690.0,
        "close": 1710.0,
        "close_hfq": 1710.0,
        "total_return": 1800.0,
        "volume": 1_000_000,
        "amount": 1_700_000_000.0,
        "turnover": 0.001,
        "is_suspended": False,
        "is_st": False,
        "limit_up": 1881.0,
        "limit_down": 1539.0,
        "hit_limit_up": False,
        "hit_limit_down": False,
    }


def test_price_frame_validates_minimal_ok():
    df = pd.DataFrame([_valid_price_row()])
    PriceFrameSchema.validate(df)


def test_price_frame_rejects_negative_volume():
    row = _valid_price_row()
    row["volume"] = -1
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        PriceFrameSchema.validate(df)


def test_price_frame_rejects_negative_amount():
    row = _valid_price_row()
    row["amount"] = -1.0
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        PriceFrameSchema.validate(df)


def test_price_frame_rejects_missing_required_column():
    row = _valid_price_row()
    del row["is_st"]
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        PriceFrameSchema.validate(df)


def test_price_frame_rejects_extra_column_in_strict_mode():
    row = _valid_price_row()
    row["unexpected"] = 1.0
    df = pd.DataFrame([row])
    with pytest.raises((pa.errors.SchemaError, pa.errors.SchemaErrors)):
        PriceFrameSchema.validate(df)


def test_price_frame_accepts_multiple_rows():
    row1 = _valid_price_row()
    row2 = {**_valid_price_row(), "date": pd.Timestamp("2024-06-16")}
    df = pd.DataFrame([row1, row2])
    PriceFrameSchema.validate(df)


# ── FundamentalsFrameSchema ──────────────────────────────────────────────────


def _valid_fundamentals_row() -> dict:
    return {
        "symbol": "600519.SH",
        "report_date": pd.Timestamp("2024-03-31"),
        "publication_date": pd.Timestamp("2024-04-28"),
        "known_as_of": pd.Timestamp("2024-04-28"),
        "statement_kind": "audited",
        "revenue": 10_000_000_000.0,
        "net_income": 3_000_000_000.0,
        "net_income_ex_nonrecurring": 2_950_000_000.0,
        "operating_cash_flow": 3_500_000_000.0,
        "capex": 200_000_000.0,
        "total_assets": 80_000_000_000.0,
        "total_equity": 50_000_000_000.0,
        "total_debt": 10_000_000_000.0,
        "goodwill": 0.0,
        "minority_interest": 100_000_000.0,
        "d_and_a": 300_000_000.0,
        "working_capital_change": 100_000_000.0,
        "pe": 25.0,
        "pb": 8.0,
        "ps": 10.0,
        "ev_ebitda": 15.0,
        "roe": 0.25,
        "roic": 0.22,
        "roa": 0.15,
        "gross_margin": 0.92,
        "net_margin": 0.50,
        "dividend_yield": 0.018,
        "market_cap": 2_000_000_000_000.0,
        "market_cap_free_float": 1_500_000_000_000.0,
        "is_soe": True,
        "is_stock_connect_eligible": True,
    }


def test_fundamentals_frame_validates_minimal_ok():
    df = pd.DataFrame([_valid_fundamentals_row()])
    FundamentalsFrameSchema.validate(df)


def test_fundamentals_rejects_bad_statement_kind():
    row = _valid_fundamentals_row()
    row["statement_kind"] = "garbage"
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsFrameSchema.validate(df)


def test_fundamentals_accepts_preliminary_and_restated():
    for kind in ("preliminary", "audited", "restated"):
        row = _valid_fundamentals_row()
        row["statement_kind"] = kind
        df = pd.DataFrame([row])
        FundamentalsFrameSchema.validate(df)


def test_fundamentals_requires_publication_date():
    row = _valid_fundamentals_row()
    del row["publication_date"]
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsFrameSchema.validate(df)


def test_fundamentals_requires_known_as_of():
    row = _valid_fundamentals_row()
    del row["known_as_of"]
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsFrameSchema.validate(df)


# ── TradingCalendarSchema ────────────────────────────────────────────────────


def test_calendar_validates_minimal_ok():
    df = pd.DataFrame(
        [
            {"exchange": "SH", "date": pd.Timestamp("2024-01-02"), "is_trading_day": True},
            {"exchange": "SH", "date": pd.Timestamp("2024-01-06"), "is_trading_day": False},
        ]
    )
    TradingCalendarSchema.validate(df)


def test_calendar_rejects_unknown_exchange():
    df = pd.DataFrame(
        [{"exchange": "NASDAQ", "date": pd.Timestamp("2024-01-02"), "is_trading_day": True}]
    )
    with pytest.raises(pa.errors.SchemaError):
        TradingCalendarSchema.validate(df)


# ── CorporateActionSchema ────────────────────────────────────────────────────


def test_corporate_action_validates_minimal_ok():
    df = pd.DataFrame(
        [
            {
                "symbol": "600519.SH",
                "ex_date": pd.Timestamp("2024-06-15"),
                "kind": "cash_dividend",
                "params_json": '{"amount_per_share": 30.88}',
            }
        ]
    )
    CorporateActionSchema.validate(df)


def test_corporate_action_rejects_unknown_kind():
    df = pd.DataFrame(
        [
            {
                "symbol": "600519.SH",
                "ex_date": pd.Timestamp("2024-06-15"),
                "kind": "not_a_kind",
                "params_json": "{}",
            }
        ]
    )
    with pytest.raises(pa.errors.SchemaError):
        CorporateActionSchema.validate(df)
