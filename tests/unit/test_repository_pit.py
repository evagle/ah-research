"""Tests for DataRepository PIT reads: fundamentals, constituents,
universe-over-time, corporate actions."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from ah_research.data.repository import DataRepository
from ah_research.exceptions import LeakageDetected, UserInputError
from ah_research.model.schemas import FundamentalsFrameSchema

# ── get_fundamentals ─────────────────────────────────────────────────────────


def test_get_fundamentals_returns_schema_valid(repo: DataRepository):
    df = repo.get_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31))
    FundamentalsFrameSchema.validate(df)


def test_get_fundamentals_defaults_asof_to_end(repo: DataRepository):
    """When asof is omitted, it defaults to end — so the query returns
    everything PIT-known at the analysis period's end."""
    df = repo.get_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31))
    # All returned rows must be known by the end date
    assert (df["publication_date"] <= pd.Timestamp("2024-12-31")).all()
    assert (df["known_as_of"] <= pd.Timestamp("2024-12-31")).all()


def test_get_fundamentals_asof_filters_future_publications(repo: DataRepository):
    """A PIT query at 2022-06-30 must not return reports published after."""
    df = repo.get_fundamentals(
        ["600519.SH"],
        date(2020, 1, 1),
        date(2024, 12, 31),
        asof=date(2022, 6, 30),
    )
    assert (df["publication_date"] <= pd.Timestamp("2022-06-30")).all()
    assert (df["known_as_of"] <= pd.Timestamp("2022-06-30")).all()


def test_get_fundamentals_raises_leakage_when_asof_after_end(repo: DataRepository):
    """Asof > end would leak knowledge gained after the analysis window."""
    with pytest.raises(LeakageDetected):
        repo.get_fundamentals(
            ["600519.SH"],
            date(2020, 1, 1),
            date(2022, 12, 31),
            asof=date(2024, 6, 30),
        )


def test_get_fundamentals_raises_on_reversed_dates(repo: DataRepository):
    with pytest.raises(UserInputError):
        repo.get_fundamentals(["600519.SH"], date(2024, 12, 31), date(2020, 1, 1))


def test_get_fundamentals_empty_symbols_returns_empty(repo: DataRepository):
    df = repo.get_fundamentals([], date(2020, 1, 1), date(2024, 12, 31))
    assert len(df) == 0


# ── get_index_constituents ───────────────────────────────────────────────────


def test_get_index_constituents_returns_csi300_size(repo: DataRepository):
    df = repo.get_index_constituents("CSI300", date(2024, 6, 30))
    assert len(df) == 300


def test_get_index_constituents_hsi_all_hk(repo: DataRepository):
    df = repo.get_index_constituents("HSI", date(2024, 6, 30))
    assert len(df) == 50
    assert df["symbol"].str.endswith(".HK").all()


def test_get_index_constituents_second_call_hits_cache(repo: DataRepository, monkeypatch):
    from unittest.mock import MagicMock

    _ = repo.get_index_constituents("CSI300", date(2024, 6, 30))
    spy = MagicMock(wraps=repo._constituents_source.fetch_constituents)
    monkeypatch.setattr(repo._constituents_source, "fetch_constituents", spy)

    _ = repo.get_index_constituents("CSI300", date(2024, 6, 30))
    assert spy.call_count == 0


# ── get_universe_over_time ───────────────────────────────────────────────────


def test_get_universe_over_time_has_date_and_symbol(repo: DataRepository):
    df = repo.get_universe_over_time("CSI300", date(2024, 1, 1), date(2024, 6, 30))
    assert {"date", "symbol", "weight"} <= set(df.columns)
    assert len(df) > 0


def test_get_universe_over_time_monthly_samples(repo: DataRepository):
    df = repo.get_universe_over_time("CSI300", date(2024, 1, 1), date(2024, 6, 30), freq="ME")
    sample_dates = df["date"].unique()
    # 2024-01 through 2024-06 month ends = 6 samples
    assert len(sample_dates) == 6


def test_get_universe_over_time_300_members_per_sample(repo: DataRepository):
    df = repo.get_universe_over_time("CSI300", date(2024, 1, 1), date(2024, 6, 30))
    per_sample = df.groupby("date")["symbol"].nunique()
    assert (per_sample == 300).all()


# ── get_corporate_actions ────────────────────────────────────────────────────


def test_get_corporate_actions_empty_when_source_empty(repo: DataRepository):
    df = repo.get_corporate_actions(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_get_corporate_actions_returns_preset_dividends(cache, fake_sources, tmp_path):
    from ah_research.integrations.fake import FakeSources

    actions = pd.DataFrame(
        [
            {
                "symbol": "600519.SH",
                "ex_date": pd.Timestamp("2024-06-15"),
                "kind": "cash_dividend",
                "params_json": '{"amount_per_share": 30.0}',
            }
        ]
    )
    fake = FakeSources(seed=42, preset_actions=actions)
    repo = DataRepository(
        price_source=fake.prices,
        fundamentals_source=fake.fundamentals,
        fx_source=fake.fx,
        calendar_source=fake.calendar,
        sector_source=fake.sectors,
        corp_actions_source=fake.corporate_actions,
        constituents_source=fake.constituents,
        cache=cache,
    )
    df = repo.get_corporate_actions(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert len(df) == 1
    assert df["kind"].iloc[0] == "cash_dividend"
