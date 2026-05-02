"""Unit tests for enrich_with_filings."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ah_research.filings.enrichment import enrich_with_filings
from ah_research.filings.filings_repository import FilingsRepository
from ah_research.filings.profile_repository import ProfileRepository

FIXTURES_FILINGS = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "filings"
)
FIXTURES_PROFILES = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"
)


@pytest.fixture
def filings_repo() -> FilingsRepository:
    return FilingsRepository(root=FIXTURES_FILINGS)


@pytest.fixture
def profiles_repo() -> ProfileRepository:
    return ProfileRepository(root=FIXTURES_PROFILES)


def test_empty_df_returns_columns(
    filings_repo: FilingsRepository, profiles_repo: ProfileRepository
):
    df = pd.DataFrame(index=pd.Index([], name="symbol", dtype="object"))
    out = enrich_with_filings(df, filings_repo=filings_repo, profiles_repo=profiles_repo)
    assert set(out.columns) >= {
        "has_ipo",
        "n_annual",
        "latest_annual_year",
        "n_research",
        "has_profile",
    }
    assert out["has_ipo"].dtype == "bool"
    assert str(out["n_annual"].dtype) == "int64"
    assert str(out["latest_annual_year"].dtype) == "Int64"
    assert str(out["n_research"].dtype) == "int64"
    assert out["has_profile"].dtype == "bool"
    assert len(out) == 0


def test_unknown_symbol_defaults(filings_repo: FilingsRepository, profiles_repo: ProfileRepository):
    df = pd.DataFrame(index=["999999.SH"])
    out = enrich_with_filings(df, filings_repo=filings_repo, profiles_repo=profiles_repo)
    row = out.loc["999999.SH"]
    assert row["has_ipo"] is False or row["has_ipo"] == False  # noqa: E712
    assert row["n_annual"] == 0
    assert pd.isna(row["latest_annual_year"])
    assert row["n_research"] == 0
    assert row["has_profile"] is False or row["has_profile"] == False  # noqa: E712


def test_real_fixture_600000(filings_repo: FilingsRepository, profiles_repo: ProfileRepository):
    df = pd.DataFrame(index=["600000.SH"])
    out = enrich_with_filings(df, filings_repo=filings_repo, profiles_repo=profiles_repo)
    row = out.loc["600000.SH"]
    assert row["has_ipo"] == True  # noqa: E712
    assert row["n_annual"] == 2
    assert row["latest_annual_year"] == 2024
    assert row["n_research"] == 1
    assert row["has_profile"] == True  # noqa: E712


def test_symbol_col_parameter(filings_repo: FilingsRepository, profiles_repo: ProfileRepository):
    df = pd.DataFrame({"ticker": ["600000.SH", "999999.SH"], "price": [10.0, 5.0]})
    out = enrich_with_filings(
        df, filings_repo=filings_repo, profiles_repo=profiles_repo, symbol_col="ticker"
    )
    assert out.shape[1] == df.shape[1] + 5
    assert out.loc[0, "n_annual"] == 2
    assert out.loc[1, "n_annual"] == 0


def test_does_not_mutate_input(filings_repo: FilingsRepository, profiles_repo: ProfileRepository):
    df = pd.DataFrame(index=["600000.SH"])
    original_cols = list(df.columns)
    enrich_with_filings(df, filings_repo=filings_repo, profiles_repo=profiles_repo)
    assert list(df.columns) == original_cols


def test_invalid_symbol_does_not_raise(
    filings_repo: FilingsRepository, profiles_repo: ProfileRepository
):
    df = pd.DataFrame(index=["not-a-symbol"])
    out = enrich_with_filings(df, filings_repo=filings_repo, profiles_repo=profiles_repo)
    row = out.loc["not-a-symbol"]
    assert row["has_ipo"] == False  # noqa: E712
    assert row["n_annual"] == 0
    assert pd.isna(row["latest_annual_year"])
    assert row["n_research"] == 0
    assert row["has_profile"] == False  # noqa: E712
