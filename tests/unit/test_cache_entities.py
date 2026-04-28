"""Tests for cache entities other than prices: fundamentals (bitemporal PIT),
index constituents (PIT), calendars, FX, sectors, corporate actions."""

from datetime import date

import pandas as pd

from ah_research.data.cache import DuckDBCache

# ── fundamentals ─────────────────────────────────────────────────────────────


def _fundamentals_row(
    symbol: str,
    report_dt: str,
    pub_dt: str,
    kind: str = "audited",
    known_as_of: str | None = None,
    revenue: float = 1e10,
) -> dict:
    return {
        "symbol": symbol,
        "report_date": pd.Timestamp(report_dt),
        "publication_date": pd.Timestamp(pub_dt),
        "known_as_of": pd.Timestamp(known_as_of or pub_dt),
        "statement_kind": kind,
        "revenue": revenue,
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


def test_fundamentals_roundtrip(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    df = pd.DataFrame([_fundamentals_row("600519.SH", "2024-03-31", "2024-04-28")])
    cache.write_fundamentals(df)
    out = cache.read_fundamentals_asof(["600519.SH"], date(2024, 6, 30))
    assert len(out) == 1
    cache.close()


def test_fundamentals_asof_excludes_future_publications(tmp_path):
    """A PIT query at 2024-04-15 must NOT see a report published on 2024-04-28."""
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_fundamentals(
        pd.DataFrame([_fundamentals_row("600519.SH", "2024-03-31", "2024-04-28")])
    )
    out = cache.read_fundamentals_asof(["600519.SH"], date(2024, 4, 15))
    assert len(out) == 0
    cache.close()


def test_fundamentals_asof_prefers_audited_over_preliminary(tmp_path):
    """After both prelim + audited are public, audited wins."""
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_fundamentals(
        pd.DataFrame(
            [
                _fundamentals_row(
                    "600519.SH", "2024-03-31", "2024-04-15", "preliminary", revenue=1e10
                ),
                _fundamentals_row(
                    "600519.SH", "2024-03-31", "2024-05-15", "audited", revenue=1.02e10
                ),
            ]
        )
    )
    out = cache.read_fundamentals_asof(["600519.SH"], date(2024, 6, 30))
    assert len(out) == 1
    assert out["statement_kind"].iloc[0] == "audited"
    assert float(out["revenue"].iloc[0]) == 1.02e10
    cache.close()


def test_fundamentals_asof_returns_preliminary_when_audited_not_yet_public(tmp_path):
    """Between prelim-publication and audit-publication, prelim is the PIT truth."""
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_fundamentals(
        pd.DataFrame(
            [
                _fundamentals_row(
                    "600519.SH", "2024-03-31", "2024-04-15", "preliminary", revenue=1e10
                ),
                _fundamentals_row(
                    "600519.SH", "2024-03-31", "2024-05-15", "audited", revenue=1.02e10
                ),
            ]
        )
    )
    out = cache.read_fundamentals_asof(["600519.SH"], date(2024, 4, 30))
    assert len(out) == 1
    assert out["statement_kind"].iloc[0] == "preliminary"
    cache.close()


def test_fundamentals_asof_restatement_wins_when_known(tmp_path):
    """A restated row with later known_as_of replaces the original audited."""
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_fundamentals(
        pd.DataFrame(
            [
                _fundamentals_row(
                    "600519.SH",
                    "2024-03-31",
                    "2024-05-15",
                    "audited",
                    known_as_of="2024-05-15",
                    revenue=1e10,
                ),
                _fundamentals_row(
                    "600519.SH",
                    "2024-03-31",
                    "2024-05-15",
                    "restated",
                    known_as_of="2024-11-20",
                    revenue=0.95e10,
                ),
            ]
        )
    )
    # Before the restatement, audited is PIT truth
    out = cache.read_fundamentals_asof(["600519.SH"], date(2024, 8, 1))
    assert out["statement_kind"].iloc[0] == "audited"
    assert float(out["revenue"].iloc[0]) == 1e10

    # After the restatement, restated is PIT truth
    out = cache.read_fundamentals_asof(["600519.SH"], date(2024, 12, 31))
    assert out["statement_kind"].iloc[0] == "restated"
    assert float(out["revenue"].iloc[0]) == 0.95e10
    cache.close()


# ── constituents ─────────────────────────────────────────────────────────────


def _constituent_row(
    symbol: str,
    idx: str = "CSI300",
    effective_from: str = "2020-01-01",
    effective_to: str | None = None,
    weight: float = 0.01,
) -> dict:
    return {
        "index_name": idx,
        "symbol": symbol,
        "weight": weight,
        "effective_from": pd.Timestamp(effective_from),
        "effective_to": pd.Timestamp(effective_to) if effective_to else pd.NaT,
    }


def test_constituents_roundtrip(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_constituents(pd.DataFrame([_constituent_row("600519.SH", "CSI300")]))
    out = cache.read_constituents_asof("CSI300", date(2024, 6, 30))
    assert len(out) == 1
    cache.close()


def test_constituents_asof_excludes_not_yet_effective(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_constituents(
        pd.DataFrame([_constituent_row("600519.SH", effective_from="2025-01-01")])
    )
    out = cache.read_constituents_asof("CSI300", date(2024, 6, 30))
    assert len(out) == 0
    cache.close()


def test_constituents_asof_excludes_already_exited(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_constituents(
        pd.DataFrame(
            [
                _constituent_row(
                    "600519.SH",
                    effective_from="2020-01-01",
                    effective_to="2022-06-30",
                )
            ]
        )
    )
    out = cache.read_constituents_asof("CSI300", date(2024, 6, 30))
    assert len(out) == 0
    cache.close()


def test_constituents_asof_includes_open_ended_membership(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_constituents(
        pd.DataFrame([_constituent_row("600519.SH", effective_from="2020-01-01")])
    )
    out = cache.read_constituents_asof("CSI300", date(2030, 1, 1))
    assert len(out) == 1
    cache.close()


def test_constituents_asof_boundary_inclusive_from_exclusive_to(tmp_path):
    """effective_from is inclusive; effective_to is exclusive (half-open interval)."""
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_constituents(
        pd.DataFrame(
            [
                _constituent_row(
                    "600519.SH",
                    effective_from="2024-01-01",
                    effective_to="2024-06-30",
                )
            ]
        )
    )
    # asof = effective_from → included
    assert len(cache.read_constituents_asof("CSI300", date(2024, 1, 1))) == 1
    # asof = day before effective_to → included
    assert len(cache.read_constituents_asof("CSI300", date(2024, 6, 29))) == 1
    # asof = effective_to → excluded (half-open)
    assert len(cache.read_constituents_asof("CSI300", date(2024, 6, 30))) == 0
    cache.close()


# ── calendar ─────────────────────────────────────────────────────────────────


def test_calendar_roundtrip(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_calendar(
        pd.DataFrame(
            [
                {"exchange": "SH", "date": pd.Timestamp("2024-01-02"), "is_trading_day": True},
                {"exchange": "SH", "date": pd.Timestamp("2024-01-06"), "is_trading_day": False},
            ]
        )
    )
    out = cache.read_calendar("SH", date(2024, 1, 1), date(2024, 1, 10))
    assert len(out) == 2
    cache.close()


def test_calendar_filters_by_exchange(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_calendar(
        pd.DataFrame(
            [
                {"exchange": "SH", "date": pd.Timestamp("2024-01-02"), "is_trading_day": True},
                {"exchange": "HK", "date": pd.Timestamp("2024-01-02"), "is_trading_day": True},
            ]
        )
    )
    out = cache.read_calendar("SH", date(2024, 1, 1), date(2024, 1, 10))
    assert len(out) == 1
    assert out["exchange"].iloc[0] == "SH"
    cache.close()


# ── FX ───────────────────────────────────────────────────────────────────────


def test_fx_roundtrip(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_fx(
        pd.DataFrame(
            [
                {"date": pd.Timestamp("2024-01-02"), "pair": "CNY_HKD", "rate": 1.09},
                {"date": pd.Timestamp("2024-01-03"), "pair": "CNY_HKD", "rate": 1.10},
            ]
        )
    )
    out = cache.read_fx("CNY_HKD", date(2024, 1, 1), date(2024, 1, 31))
    assert len(out) == 2
    cache.close()


# ── sectors ──────────────────────────────────────────────────────────────────


def test_sectors_roundtrip(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_sectors(
        pd.DataFrame(
            [
                {"symbol": "600519.SH", "sector_l1": "Consumer", "sector_l2": "Consumer-A"},
                {"symbol": "0700.HK", "sector_l1": "Technology", "sector_l2": "Technology-A"},
            ]
        )
    )
    out = cache.read_sectors(["600519.SH"])
    assert len(out) == 1
    assert out["sector_l1"].iloc[0] == "Consumer"
    cache.close()


def test_sectors_upsert_updates_classification(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_sectors(
        pd.DataFrame([{"symbol": "600519.SH", "sector_l1": "Old", "sector_l2": "Old-A"}])
    )
    cache.write_sectors(
        pd.DataFrame([{"symbol": "600519.SH", "sector_l1": "New", "sector_l2": "New-A"}])
    )
    out = cache.read_sectors(["600519.SH"])
    assert len(out) == 1
    assert out["sector_l1"].iloc[0] == "New"
    cache.close()


# ── corporate actions ────────────────────────────────────────────────────────


def test_corporate_actions_roundtrip(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    cache.write_corporate_actions(
        pd.DataFrame(
            [
                {
                    "symbol": "600519.SH",
                    "ex_date": pd.Timestamp("2024-06-15"),
                    "kind": "cash_dividend",
                    "params_json": '{"amount_per_share": 30.88}',
                }
            ]
        )
    )
    out = cache.read_corporate_actions(["600519.SH"], date(2024, 1, 1), date(2024, 12, 31))
    assert len(out) == 1
    assert out["kind"].iloc[0] == "cash_dividend"
    cache.close()
