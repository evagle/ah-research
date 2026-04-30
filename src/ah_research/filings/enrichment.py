"""enrich_with_filings — add filing-derived columns to a symbol-indexed DataFrame."""

from __future__ import annotations

import pandas as pd

from ah_research.filings.filings_repository import FilingsRepository
from ah_research.filings.profile_repository import ProfileRepository

_NEW_COLUMNS = ("has_ipo", "n_annual", "latest_annual_year", "n_research", "has_profile")


def enrich_with_filings(
    df: pd.DataFrame,
    *,
    filings_repo: FilingsRepository | None = None,
    profiles_repo: ProfileRepository | None = None,
    symbol_col: str | None = None,
) -> pd.DataFrame:
    """Return a copy of *df* with 5 new filing-derived columns.

    Parameters
    ----------
    df:
        Input DataFrame.  Symbols are read from ``df.index`` unless
        *symbol_col* is specified.
    filings_repo:
        ``FilingsRepository`` instance to query.  Defaults to
        ``FilingsRepository()`` (reads from ``data/filings/``).
    profiles_repo:
        ``ProfileRepository`` instance to query.  Defaults to
        ``ProfileRepository()`` (reads from ``profiles/``).
    symbol_col:
        Name of a column in *df* that contains ticker symbols.  When
        ``None`` the index is used as the symbol source.

    Returns
    -------
    pd.DataFrame
        New DataFrame (input is never mutated) with the original columns
        plus:

        - ``has_ipo`` (bool) — IPO prospectus present in filings store
        - ``n_annual`` (int64) — number of annual reports
        - ``latest_annual_year`` (Int64, nullable) — highest year among
          annual reports, or ``pd.NA`` when none exist
        - ``n_research`` (int64) — number of broker research notes
        - ``has_profile`` (bool) — company profile present
    """
    out = df.copy()

    if filings_repo is None:
        filings_repo = FilingsRepository()
    if profiles_repo is None:
        profiles_repo = ProfileRepository()

    symbols = out[symbol_col] if symbol_col else out.index

    has_ipo: list[bool] = []
    n_annual: list[int] = []
    latest_year: list[int | None] = []  # None -> pd.NA after astype("Int64")
    n_research: list[int] = []
    has_profile: list[bool] = []

    for sym in symbols:
        try:
            filings = filings_repo.list_filings(str(sym))
        except Exception:
            filings = []

        annuals = [f for f in filings if f.kind == "annual"]
        research = [f for f in filings if f.kind == "research"]

        has_ipo.append(any(f.kind == "ipo" for f in filings))
        n_annual.append(len(annuals))

        years = [f.year for f in annuals if f.year is not None]
        latest_year.append(max(years) if years else None)

        n_research.append(len(research))

        try:
            has_profile.append(profiles_repo.latest(str(sym)) is not None)
        except Exception:
            has_profile.append(False)

    out["has_ipo"] = has_ipo
    out["n_annual"] = pd.array(n_annual, dtype="int64")
    # pd.array with None values → nullable Int64
    out["latest_annual_year"] = pd.Series(latest_year, index=out.index, dtype="Int64")
    out["n_research"] = pd.array(n_research, dtype="int64")
    out["has_profile"] = has_profile

    # Ensure empty input still gets correct dtypes on all columns
    if len(out) == 0:
        out["has_ipo"] = pd.array([], dtype="bool")
        out["n_annual"] = pd.array([], dtype="int64")
        out["latest_annual_year"] = pd.array([], dtype="Int64")
        out["n_research"] = pd.array([], dtype="int64")
        out["has_profile"] = pd.array([], dtype="bool")

    return out
