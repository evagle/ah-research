"""Unit tests for build_corpus_summary."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from ah_research.filings.filings_repository import FilingsRepository
from ah_research.filings.profile_repository import ProfileRepository
from ah_research.filings.summary import build_corpus_summary

PHASE4_2_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2"
FILINGS_ROOT = PHASE4_2_ROOT / "filings"
PROFILES_ROOT = PHASE4_2_ROOT / "profiles"

_EXPECTED_COLUMNS = [
    "symbol",
    "n_annual",
    "latest_annual_year",
    "has_ipo",
    "n_research",
    "latest_research_date",
    "has_profile",
    "latest_profile_date",
    "profile_age_days",
    "annual_staleness_years",
]


# ---------------------------------------------------------------------------
# Test 1: Empty repos → empty DataFrame with 10 columns + correct dtypes
# ---------------------------------------------------------------------------


def test_empty_repos_returns_empty_df_with_correct_schema(tmp_path: Path) -> None:
    empty_filings_root = tmp_path / "filings"
    empty_profiles_root = tmp_path / "profiles"
    # Neither directory exists — repos return empty symbol lists

    fr = FilingsRepository(root=empty_filings_root)
    pr = ProfileRepository(root=empty_profiles_root)
    df = build_corpus_summary(fr, pr)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == _EXPECTED_COLUMNS
    assert len(df.columns) == 10


# ---------------------------------------------------------------------------
# Test 2: phase4_2 fixtures → 600000.SH row correctness
# ---------------------------------------------------------------------------


def test_phase4_2_fixtures_600000sh_row() -> None:
    fr = FilingsRepository(root=FILINGS_ROOT)
    pr = ProfileRepository(root=PROFILES_ROOT)
    df = build_corpus_summary(fr, pr)

    assert not df.empty
    assert "600000.SH" in df["symbol"].values

    row = df[df["symbol"] == "600000.SH"].iloc[0]
    assert row["n_annual"] == 2
    assert row["has_ipo"] is True or row["has_ipo"] == True  # noqa: E712
    assert row["n_research"] == 1
    assert row["has_profile"] is True or row["has_profile"] == True  # noqa: E712
    assert row["latest_annual_year"] == 2024


# ---------------------------------------------------------------------------
# Test 3: Deterministic as_of yields deterministic profile_age_days
# ---------------------------------------------------------------------------


def test_deterministic_as_of_yields_deterministic_profile_age_days() -> None:
    fr = FilingsRepository(root=FILINGS_ROOT)
    pr = ProfileRepository(root=PROFILES_ROOT)

    as_of = date(2026, 5, 1)
    df = build_corpus_summary(fr, pr, as_of=as_of)

    row = df[df["symbol"] == "600000.SH"].iloc[0]
    # profile date is 2026-04-28; as_of is 2026-05-01 → 3 days
    assert row["profile_age_days"] == 3

    row_001 = df[df["symbol"] == "000001.SZ"].iloc[0]
    # profile date is 2026-03-15; as_of is 2026-05-01 → 47 days
    assert row_001["profile_age_days"] == 47


# ---------------------------------------------------------------------------
# Test 4: Symbol without profile → has_profile=False, profile_age_days=NA
# ---------------------------------------------------------------------------


def test_symbol_without_profile_has_na_profile_fields() -> None:
    # 000001.SZ is in filings but has no profile in phase4_2 profiles fixture?
    # Actually 000001.SZ does have a profile. Use a filings-only scenario.
    # Create a filings root that has a symbol not in profiles root.
    fr = FilingsRepository(root=FILINGS_ROOT)
    # Use empty profiles root so nothing has a profile
    pr = ProfileRepository(root=Path("/nonexistent_profiles_dir_that_does_not_exist"))

    df = build_corpus_summary(fr, pr)

    # 000001.SZ is in filings only → no profile
    row = df[df["symbol"] == "000001.SZ"].iloc[0]
    assert row["has_profile"] == False  # noqa: E712
    assert pd.isna(row["profile_age_days"])
    assert pd.isna(row["latest_profile_date"])


# ---------------------------------------------------------------------------
# Test 5: Column dtypes exactly match spec
# ---------------------------------------------------------------------------


def test_column_dtypes_match_spec() -> None:
    fr = FilingsRepository(root=FILINGS_ROOT)
    pr = ProfileRepository(root=PROFILES_ROOT)
    df = build_corpus_summary(fr, pr)

    assert df["symbol"].dtype == object
    assert df["n_annual"].dtype == pd.Int64Dtype() or str(df["n_annual"].dtype) == "int64"
    assert df["latest_annual_year"].dtype == pd.Int64Dtype()
    assert df["has_ipo"].dtype == bool or str(df["has_ipo"].dtype) == "bool"
    assert df["n_research"].dtype == pd.Int64Dtype() or str(df["n_research"].dtype) == "int64"
    assert df["latest_research_date"].dtype == "datetime64[ns]"
    assert df["has_profile"].dtype == bool or str(df["has_profile"].dtype) == "bool"
    assert df["latest_profile_date"].dtype == "datetime64[ns]"
    assert df["profile_age_days"].dtype == pd.Int64Dtype()
    assert df["annual_staleness_years"].dtype == pd.Int64Dtype()


# ---------------------------------------------------------------------------
# Test 6: Empty DataFrame still has all 10 columns with correct dtypes
# ---------------------------------------------------------------------------


def test_empty_df_has_correct_dtypes(tmp_path: Path) -> None:
    fr = FilingsRepository(root=tmp_path / "f")
    pr = ProfileRepository(root=tmp_path / "p")
    df = build_corpus_summary(fr, pr)

    assert list(df.columns) == _EXPECTED_COLUMNS
    assert df["symbol"].dtype == object
    assert df["n_annual"].dtype == pd.Int64Dtype() or str(df["n_annual"].dtype) == "int64"
    assert df["latest_annual_year"].dtype == pd.Int64Dtype()
    assert df["has_ipo"].dtype == bool or str(df["has_ipo"].dtype) == "bool"
    assert df["n_research"].dtype == pd.Int64Dtype() or str(df["n_research"].dtype) == "int64"
    assert df["latest_research_date"].dtype == "datetime64[ns]"
    assert df["has_profile"].dtype == bool or str(df["has_profile"].dtype) == "bool"
    assert df["latest_profile_date"].dtype == "datetime64[ns]"
    assert df["profile_age_days"].dtype == pd.Int64Dtype()
    assert df["annual_staleness_years"].dtype == pd.Int64Dtype()
