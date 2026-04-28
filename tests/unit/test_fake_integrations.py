from datetime import date

import pandas as pd

from ah_research.integrations.fake import FakeSources


def test_fake_price_source_deterministic():
    fake = FakeSources(seed=42)
    df1 = fake.prices.fetch_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 10))
    df2 = fake.prices.fetch_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 10))
    assert df1.equals(df2)
    assert len(df1) > 0
    assert "close" in df1.columns


def test_fake_price_source_multiple_symbols():
    fake = FakeSources(seed=42)
    df = fake.prices.fetch_prices(["600519.SH", "0700.HK"], date(2024, 1, 1), date(2024, 1, 10))
    assert set(df["symbol"].unique()) == {"600519.SH", "0700.HK"}


def test_fake_prices_have_trading_state_flags():
    fake = FakeSources(seed=42)
    df = fake.prices.fetch_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 10))
    assert "is_suspended" in df.columns
    assert "is_st" in df.columns


def test_fake_fundamentals_bitemporal_rows():
    """Each (symbol, report_date) should have BOTH preliminary + audited rows.

    This exercises the PIT filter: at date D between pub_prelim and pub_audited,
    a PIT query must see the preliminary row; after pub_audited, it sees audited.
    """
    fake = FakeSources(seed=42)
    df = fake.fundamentals.fetch_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31))
    kinds_per_report = df.groupby(["symbol", "report_date"])["statement_kind"].nunique()
    assert (kinds_per_report >= 2).all(), "expected both preliminary and audited per report"


def test_fake_fundamentals_publication_after_report():
    fake = FakeSources(seed=42)
    df = fake.fundamentals.fetch_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31))
    assert (df["publication_date"] > df["report_date"]).all()


def test_fake_fundamentals_known_as_of_equals_publication_for_non_restatement():
    fake = FakeSources(seed=42)
    df = fake.fundamentals.fetch_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31))
    non_restated = df[df["statement_kind"] != "restated"]
    assert (non_restated["known_as_of"] == non_restated["publication_date"]).all()


def test_fake_constituents_returns_stable_list():
    fake = FakeSources(seed=42)
    df = fake.constituents.fetch_constituents("CSI300", date(2024, 1, 1))
    assert len(df) == 300
    assert "symbol" in df.columns
    assert "weight" in df.columns


def test_fake_constituents_hsi_count():
    fake = FakeSources(seed=42)
    df = fake.constituents.fetch_constituents("HSI", date(2024, 1, 1))
    assert len(df) == 50
    # HSI should be all HK
    assert df["symbol"].str.endswith(".HK").all()


def test_fake_calendar_flags_weekends():
    fake = FakeSources(seed=42)
    df = fake.calendar.fetch_calendar("SH", date(2024, 1, 1), date(2024, 1, 14))
    sat = df[df["date"] == pd.Timestamp("2024-01-06")]["is_trading_day"].iloc[0]
    assert bool(sat) is False


def test_fake_fx_returns_business_days():
    fake = FakeSources(seed=42)
    df = fake.fx.fetch_fx("CNY_HKD", date(2024, 1, 1), date(2024, 1, 31))
    assert "date" in df.columns
    assert "rate" in df.columns
    assert len(df) > 0


def test_fake_sectors_assigns_sector_for_each_symbol():
    fake = FakeSources(seed=42)
    df = fake.sectors.fetch_sectors(["600519.SH", "000001.SZ", "0700.HK"])
    assert len(df) == 3
    assert {"symbol", "sector_l1", "sector_l2"} <= set(df.columns)


def test_fake_corporate_actions_empty_by_default():
    fake = FakeSources(seed=42)
    df = fake.corporate_actions.fetch_corporate_actions(
        ["600519.SH"], date(2024, 1, 1), date(2024, 12, 31)
    )
    assert isinstance(df, pd.DataFrame)
    assert {"symbol", "ex_date", "kind", "params_json"} <= set(df.columns)
