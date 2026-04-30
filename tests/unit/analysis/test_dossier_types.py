# tests/unit/analysis/test_dossier_types.py
import dataclasses
from datetime import date

import pandas as pd
import pytest

from ah_research.analysis.dossier import (
    DividendSection,
    Dossier,
    DossierMetadata,
    FundamentalsSection,
    OverviewSection,
    OwnerEarningsSection,
    PeersSection,
    ValuationBandsSection,
)
from ah_research.model.types import parse_symbol


def test_overview_section_frozen() -> None:
    ov = OverviewSection(
        symbol=parse_symbol("600000.SH"),
        name_en="Foo Bank",
        name_zh="XX银行",
        sector_l1="Finance",
        sector_l2="Banks",
        market_cap=1e11,
        market_cap_free_float=6e10,
        is_soe=True,
        is_stock_connect_eligible=True,
        listing_date=date(1999, 11, 10),
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        ov.market_cap = 0  # type: ignore[misc]


def test_dossier_accepts_none_ah_premium() -> None:
    sym = parse_symbol("600000.SH")
    asof = date(2024, 12, 31)
    overview = OverviewSection(
        symbol=sym,
        name_en=None,
        name_zh=None,
        sector_l1="Finance",
        sector_l2=None,
        market_cap=0.0,
        market_cap_free_float=0.0,
        is_soe=False,
        is_stock_connect_eligible=False,
        listing_date=None,
    )
    fs = FundamentalsSection(
        revenue_series=pd.Series(dtype=float),
        net_income_series=pd.Series(dtype=float),
        operating_cash_flow_series=pd.Series(dtype=float),
        capex_series=pd.Series(dtype=float),
        roe_series=pd.Series(dtype=float),
        roic_series=pd.Series(dtype=float),
        gross_margin_series=pd.Series(dtype=float),
        net_margin_series=pd.Series(dtype=float),
        latest_fiscal_year=2023,
    )
    oe = OwnerEarningsSection(
        series=pd.Series(dtype=float),
        latest_fy=0.0,
        avg_10y=0.0,
        cv_10y=0.0,
    )
    vbs = ValuationBandsSection(
        pe_bands={"p10": 5.0, "p25": 7.0, "p50": 10.0, "p75": 13.0, "p90": 20.0},
        pe_current=10.0,
        pe_current_percentile=50.0,
        pb_bands={"p10": 0.5, "p25": 0.8, "p50": 1.0, "p75": 1.5, "p90": 2.0},
        pb_current=1.0,
        pb_current_percentile=50.0,
        ps_bands={"p10": 0.5, "p25": 0.8, "p50": 1.0, "p75": 1.5, "p90": 2.0},
        ps_current=1.0,
        ps_current_percentile=50.0,
        window_years=10,
    )
    div = DividendSection(
        history=pd.DataFrame(),
        ttm_yield=0.0,
        cagr_5y=0.0,
        cagr_10y=0.0,
        n_consecutive_years=0,
        consistency_grade="F",
    )
    peers = PeersSection(peer_symbols=[], peer_table=pd.DataFrame())
    meta = DossierMetadata(
        asof=asof,
        repo_snapshot_date=asof,
        code_version="abc1234",
        warnings=[],
    )
    dossier = Dossier(
        symbol=sym,
        asof=asof,
        overview=overview,
        fundamentals=fs,
        owner_earnings=oe,
        valuation_bands=vbs,
        dividend_history=div,
        ah_premium=None,
        peers=peers,
        metadata=meta,
    )
    assert dossier.ah_premium is None
    assert dossier.symbol.code == "600000"
