"""build_corpus_summary — one-row-per-ticker coverage DataFrame."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd

from ah_research.filings.filings_repository import FilingsRepository
from ah_research.filings.profile_repository import ProfileRepository

_ANNUAL_RE = re.compile(r"^年报-(\d{4})\.md$")
_RESEARCH_DATE_RE = re.compile(r"(\d{8})\.md$")

# Ordered column list used to build the output DataFrame
_COLUMNS = [
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

# Dtypes for each column
_DTYPES: dict[str, Any] = {
    "symbol": "object",
    "n_annual": "int64",
    "latest_annual_year": "Int64",
    "has_ipo": "bool",
    "n_research": "int64",
    "latest_research_date": "datetime64[ns]",
    "has_profile": "bool",
    "latest_profile_date": "datetime64[ns]",
    "profile_age_days": "Int64",
    "annual_staleness_years": "Int64",
}


def _empty_df() -> pd.DataFrame:
    """Return an empty DataFrame with all 10 columns and correct dtypes."""
    df = pd.DataFrame(columns=_COLUMNS)
    for col, dtype in _DTYPES.items():
        if dtype == "datetime64[ns]":
            df[col] = pd.Series([], dtype="datetime64[ns]")
        elif dtype == "bool":
            df[col] = pd.Series([], dtype="bool")
        elif dtype == "Int64":
            df[col] = pd.Series([], dtype="Int64")
        elif dtype == "int64":
            df[col] = pd.Series([], dtype="int64")
        else:
            df[col] = pd.Series([], dtype="object")
    return df


def build_corpus_summary(
    filings_repo: FilingsRepository | None = None,
    profiles_repo: ProfileRepository | None = None,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    """One-row-per-ticker coverage table.

    Symbols = union(filings_repo.list_symbols(), profiles_repo.list_symbols())
    sorted alphabetically.

    Parameters
    ----------
    filings_repo:
        FilingsRepository instance. If None, defaults to FilingsRepository().
    profiles_repo:
        ProfileRepository instance. If None, defaults to ProfileRepository().
    as_of:
        Reference date for computing profile_age_days and annual_staleness_years.
        Defaults to today.

    Returns
    -------
    pd.DataFrame
        One row per symbol with 10 columns:
        symbol, n_annual, latest_annual_year, has_ipo, n_research,
        latest_research_date, has_profile, latest_profile_date,
        profile_age_days, annual_staleness_years.
    """
    if filings_repo is None:
        filings_repo = FilingsRepository()
    if profiles_repo is None:
        profiles_repo = ProfileRepository()
    if as_of is None:
        as_of = date.today()

    filings_symbols = set(filings_repo.list_symbols())
    profiles_symbols = set(profiles_repo.list_symbols())
    all_symbols = sorted(filings_symbols | profiles_symbols)

    if not all_symbols:
        return _empty_df()

    rows: list[dict[str, Any]] = []
    for symbol in all_symbols:
        row: dict[str, Any] = _build_row(symbol, filings_repo, profiles_repo, as_of)
        rows.append(row)

    df = pd.DataFrame(rows, columns=_COLUMNS)

    # Cast to correct dtypes
    df["symbol"] = df["symbol"].astype("object")
    df["n_annual"] = df["n_annual"].astype("int64")
    df["latest_annual_year"] = df["latest_annual_year"].astype("Int64")
    df["has_ipo"] = df["has_ipo"].astype("bool")
    df["n_research"] = df["n_research"].astype("int64")
    df["latest_research_date"] = pd.to_datetime(df["latest_research_date"]).astype("datetime64[ns]")
    df["has_profile"] = df["has_profile"].astype("bool")
    df["latest_profile_date"] = pd.to_datetime(df["latest_profile_date"]).astype("datetime64[ns]")
    df["profile_age_days"] = df["profile_age_days"].astype("Int64")
    df["annual_staleness_years"] = df["annual_staleness_years"].astype("Int64")

    return df.reset_index(drop=True)


def _build_row(
    symbol: str,
    filings_repo: FilingsRepository,
    profiles_repo: ProfileRepository,
    as_of: date,
) -> dict[str, Any]:
    """Build a single row dict for one symbol."""
    # --- filings side ---
    n_annual = 0
    latest_annual_year: int | None = None
    has_ipo = False
    n_research = 0
    latest_research_date: pd.Timestamp | None = None

    sym_dir = filings_repo.root / symbol
    if sym_dir.exists():
        annual_years: list[int] = []
        research_dates: list[date] = []

        for p in sym_dir.iterdir():
            m = _ANNUAL_RE.match(p.name)
            if m:
                annual_years.append(int(m.group(1)))
            elif p.name == "招股说明书.md":
                has_ipo = True

        n_annual = len(annual_years)
        if annual_years:
            latest_annual_year = max(annual_years)

        rdir = sym_dir / "research"
        if rdir.exists():
            for p in rdir.glob("*.md"):
                n_research += 1
                d = _extract_research_date(p.name)
                if d is not None:
                    research_dates.append(d)
        if research_dates:
            latest_research_date = pd.Timestamp(max(research_dates))

    # --- profiles side ---
    has_profile = False
    latest_profile_date: pd.Timestamp | None = None
    profile_age_days: int | None = None

    profile = profiles_repo.latest(symbol) if symbol in set(profiles_repo.list_symbols()) else None
    if profile is not None:
        has_profile = True
        latest_profile_date = pd.Timestamp(profile.date)
        profile_age_days = (as_of - profile.date).days

    # --- staleness ---
    annual_staleness_years: int | None = None
    if latest_annual_year is not None:
        annual_staleness_years = as_of.year - latest_annual_year

    return {
        "symbol": symbol,
        "n_annual": n_annual,
        "latest_annual_year": latest_annual_year,
        "has_ipo": has_ipo,
        "n_research": n_research,
        "latest_research_date": latest_research_date,
        "has_profile": has_profile,
        "latest_profile_date": latest_profile_date,
        "profile_age_days": profile_age_days,
        "annual_staleness_years": annual_staleness_years,
    }


def _extract_research_date(name: str) -> date | None:
    m = _RESEARCH_DATE_RE.search(name)
    if not m:
        return None
    s = m.group(1)
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None
