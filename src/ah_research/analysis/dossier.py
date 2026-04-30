"""Company dossier: section dataclasses, build_dossier(), and renderers."""

from __future__ import annotations

import dataclasses
import subprocess
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import pandas as pd

from ah_research.model.types import AHPair, Symbol

# ── Section dataclasses ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class OverviewSection:
    symbol: Symbol
    name_en: str | None
    name_zh: str | None
    sector_l1: str
    sector_l2: str | None
    market_cap: float
    market_cap_free_float: float
    is_soe: bool
    is_stock_connect_eligible: bool
    listing_date: date | None


@dataclass(frozen=True)
class FundamentalsSection:
    revenue_series: pd.Series
    net_income_series: pd.Series
    operating_cash_flow_series: pd.Series
    capex_series: pd.Series
    roe_series: pd.Series
    roic_series: pd.Series
    gross_margin_series: pd.Series
    net_margin_series: pd.Series
    latest_fiscal_year: int


@dataclass(frozen=True)
class OwnerEarningsSection:
    series: pd.Series
    latest_fy: float
    avg_10y: float
    cv_10y: float


@dataclass(frozen=True)
class ValuationBandsSection:
    pe_bands: dict[str, float]
    pe_current: float
    pe_current_percentile: float
    pb_bands: dict[str, float]
    pb_current: float
    pb_current_percentile: float
    ps_bands: dict[str, float]
    ps_current: float
    ps_current_percentile: float
    window_years: int


@dataclass(frozen=True)
class DividendSection:
    history: pd.DataFrame
    ttm_yield: float
    cagr_5y: float
    cagr_10y: float
    n_consecutive_years: int
    consistency_grade: str


@dataclass(frozen=True)
class AHPremiumSection:
    paired_symbol: Symbol
    pair_name_en: str
    current_premium: float
    current_z_score: float
    premium_2y_series: pd.DataFrame
    historical_max: dict[str, Any]
    historical_min: dict[str, Any]


@dataclass(frozen=True)
class PeersSection:
    peer_symbols: list[Symbol]
    peer_table: pd.DataFrame


@dataclass(frozen=True)
class FilingsSection:
    n_annual: int
    latest_annual_year: int | None
    has_ipo: bool
    n_research: int
    latest_research_date: date | None
    latest_annual_path: str | None


@dataclass(frozen=True)
class ProfileSection:
    has_profile: bool
    latest_profile_date: date | None
    section_names: tuple[str, ...]
    latest_profile_path: str | None


@dataclass(frozen=True)
class DossierMetadata:
    asof: date
    repo_snapshot_date: date
    code_version: str
    warnings: list[str]


# ── Localization headers ──────────────────────────────────────────────────────

_HEADERS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Dossier",
        "overview": "Overview",
        "fundamentals": "Fundamentals (10-Year Trajectory)",
        "owner_earnings": "Owner Earnings",
        "valuation": "Valuation Bands",
        "dividend": "Dividend History",
        "ah_premium": "AH Premium",
        "peers": "Sector Peers",
        "metadata": "Reproducibility",
    },
    "zh": {
        "title": "公司档案",
        "overview": "概览",
        "fundamentals": "基本面(10年轨迹)",
        "owner_earnings": "所有者盈余",
        "valuation": "估值分位",
        "dividend": "分红历史",
        "ah_premium": "A/H溢价",
        "peers": "同业对比",
        "metadata": "可复现性信息",
    },
}


def _series_to_md_table(s: pd.Series, label: str) -> str:
    """Convert a pd.Series to a compact markdown table."""
    if s.empty:
        return f"*No {label} data available.*\n"
    rows = ["| Date | Value |", "| --- | --- |"]
    for idx, val in s.items():
        rows.append(f"| {idx} | {val:.2f} |")
    return "\n".join(rows) + "\n"


def _bands_to_md_table(bands: dict[str, float], current: float, pct: float) -> str:
    rows = ["| Percentile | Value |", "| --- | --- |"]
    for k, v in bands.items():
        rows.append(f"| {k} | {v:.2f} |")
    rows.append(f"| **current** | **{current:.2f}** (pct: {pct:.1f}) |")
    return "\n".join(rows) + "\n"


@dataclass(frozen=True)
class Dossier:
    symbol: Symbol
    asof: date
    overview: OverviewSection
    fundamentals: FundamentalsSection
    owner_earnings: OwnerEarningsSection
    valuation_bands: ValuationBandsSection
    dividend_history: DividendSection
    ah_premium: AHPremiumSection | None
    peers: PeersSection
    metadata: DossierMetadata

    # ── Renderers ─────────────────────────────────────────────────────────

    def to_markdown(self, language: str = "en") -> str:
        """Render dossier as Markdown with English (default) or Chinese headers."""
        lang = language if language in _HEADERS else "en"
        h = _HEADERS[lang]
        lines: list[str] = []

        # Title
        lines.append(f"# {h['title']}: {self.symbol}")
        lines.append(f"*As of: {self.asof}*\n")

        # Warnings
        if self.metadata.warnings:
            for w in self.metadata.warnings:
                lines.append(f"> **Warning:** {w}\n")

        # Overview
        lines.append(f"## {h['overview']}")
        ov = self.overview
        lines.append(f"- Symbol: {ov.symbol}")
        if ov.name_en:
            lines.append(f"- Name (EN): {ov.name_en}")
        if ov.name_zh:
            lines.append(f"- Name (ZH): {ov.name_zh}")
        lines.append(f"- Sector L1: {ov.sector_l1}")
        if ov.sector_l2:
            lines.append(f"- Sector L2: {ov.sector_l2}")
        lines.append(f"- Market Cap: {ov.market_cap:,.0f}")
        lines.append(f"- Free Float: {ov.market_cap_free_float:,.0f}")
        lines.append(f"- SOE: {ov.is_soe}")
        lines.append(f"- Stock Connect: {ov.is_stock_connect_eligible}")
        if ov.listing_date:
            lines.append(f"- Listing Date: {ov.listing_date}")
        lines.append("")

        # Fundamentals
        lines.append(f"## {h['fundamentals']}")
        fs = self.fundamentals
        lines.append(f"*Latest Fiscal Year: {fs.latest_fiscal_year}*\n")
        lines.append("**Revenue Series**")
        lines.append(_series_to_md_table(fs.revenue_series, "revenue"))
        lines.append("**Net Income Series**")
        lines.append(_series_to_md_table(fs.net_income_series, "net income"))
        lines.append("**ROE Series**")
        lines.append(_series_to_md_table(fs.roe_series, "ROE"))

        # Owner Earnings
        lines.append(f"## {h['owner_earnings']}")
        oe = self.owner_earnings
        lines.append(f"- Latest FY: {oe.latest_fy:.2f}")
        lines.append(f"- 10Y Average: {oe.avg_10y:.2f}")
        lines.append(f"- 10Y CV: {oe.cv_10y:.2f}")
        lines.append(_series_to_md_table(oe.series, "owner earnings"))

        # Valuation Bands
        lines.append(f"## {h['valuation']}")
        vb = self.valuation_bands
        lines.append(f"*Window: {vb.window_years} years*\n")
        lines.append("**P/E Bands**")
        lines.append(_bands_to_md_table(vb.pe_bands, vb.pe_current, vb.pe_current_percentile))
        lines.append("**P/B Bands**")
        lines.append(_bands_to_md_table(vb.pb_bands, vb.pb_current, vb.pb_current_percentile))
        lines.append("**P/S Bands**")
        lines.append(_bands_to_md_table(vb.ps_bands, vb.ps_current, vb.ps_current_percentile))

        # Dividend History
        lines.append(f"## {h['dividend']}")
        dv = self.dividend_history
        lines.append(f"- Consistency Grade: {dv.consistency_grade}")
        lines.append(f"- TTM Yield: {dv.ttm_yield:.2%}")
        lines.append(f"- 5Y CAGR: {dv.cagr_5y:.2%}")
        lines.append(f"- 10Y CAGR: {dv.cagr_10y:.2%}")
        lines.append(f"- Consecutive Years: {dv.n_consecutive_years}")
        lines.append("")

        # AH Premium (optional)
        if self.ah_premium is not None:
            ah = self.ah_premium
            lines.append(f"## {h['ah_premium']}")
            lines.append(f"- Paired Symbol: {ah.paired_symbol}")
            lines.append(f"- Company: {ah.pair_name_en}")
            lines.append(f"- Current Premium: {ah.current_premium:.2%}")
            lines.append(f"- Z-Score: {ah.current_z_score:.2f}")
            lines.append("")

        # Peers
        if self.peers.peer_symbols:
            lines.append(f"## {h['peers']}")
            for ps in self.peers.peer_symbols:
                lines.append(f"- {ps}")
            lines.append("")

        # Metadata / Reproducibility
        lines.append(f"## {h['metadata']}")
        meta = self.metadata
        lines.append(f"- As-Of: {meta.asof}")
        lines.append(f"- Repo Snapshot: {meta.repo_snapshot_date}")
        lines.append(f"- Code Version: {meta.code_version}")
        lines.append("")

        return "\n".join(lines)

    def to_html(self, language: str = "en") -> str:
        """Render dossier as HTML (hand-rolled from markdown sections)."""
        md = self.to_markdown(language=language)
        html_lines: list[str] = ["<html><body>"]
        for line in md.splitlines():
            if line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("| "):
                # table row
                if "<table>" not in html_lines[-1] if html_lines else True:
                    html_lines.append("<table>")
                cells = [c.strip() for c in line.strip("|").split("|")]
                row_html = "".join(f"<td>{c}</td>" for c in cells)
                html_lines.append(f"<tr>{row_html}</tr>")
            elif line.startswith("---") and "|" in (html_lines[-1] if html_lines else ""):
                pass  # skip markdown table divider
            elif line.startswith("- "):
                html_lines.append(f"<li>{line[2:]}</li>")
            elif line.startswith("> "):
                html_lines.append(f"<blockquote>{line[2:]}</blockquote>")
            elif line.startswith("*") and line.endswith("*"):
                html_lines.append(f"<em>{line.strip('*')}</em>")
            elif line.strip():
                html_lines.append(f"<p>{line}</p>")
        html_lines.append("</body></html>")
        return "\n".join(html_lines)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (pd.Series/DataFrame as list-of-records)."""

        def _convert(obj: Any) -> Any:
            if isinstance(obj, pd.Series):
                return [{"index": str(k), "value": v} for k, v in obj.items()]
            if isinstance(obj, pd.DataFrame):
                return obj.to_dict(orient="records")
            if isinstance(obj, Symbol):
                return str(obj)
            if isinstance(obj, AHPair):
                return {"a_symbol": str(obj.a_symbol), "h_symbol": str(obj.h_symbol)}
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            return obj

        raw = dataclasses.asdict(self)
        return {k: _convert(v) for k, v in raw.items()}


# ── build_dossier() ───────────────────────────────────────────────────────────


def build_dossier(
    symbol: Symbol | str,
    repo: Any,
    asof: date | None = None,
    peers_n: int = 5,
) -> Dossier:
    """Build a full Dossier for *symbol* from *repo* as of *asof*.

    Raises ValueError (matching "not available") if the symbol has no price
    data at *asof* — i.e., it is delisted or outside the repo's coverage.
    """
    from ah_research.analysis.dividend_history import dividend_consistency_grade
    from ah_research.analysis.owner_earnings import owner_earnings_series
    from ah_research.analysis.valuation_bands import compute_valuation_bands
    from ah_research.data.ah_pairs import load_ah_pairs
    from ah_research.model.types import parse_symbol

    sym: Symbol = parse_symbol(symbol) if isinstance(symbol, str) else symbol
    asof = asof or date.today()
    warnings: list[str] = []

    # Verify symbol is available at asof
    sym_str = str(sym)
    try:
        prices = repo.get_prices([sym_str], start=asof, end=asof)
        if prices is None or len(prices) == 0:
            raise ValueError(f"Symbol {sym} not available in repo at asof={asof}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Symbol {sym} not available in repo at asof={asof}: {exc}") from exc

    # 10-year lookback
    ten_year_start = date(asof.year - 10, asof.month, asof.day)

    fundamentals = repo.get_fundamentals([sym_str], start=ten_year_start, end=asof, asof=asof)
    corp_actions = repo.get_corporate_actions([sym_str], start=ten_year_start, end=asof)
    sector_df = repo.get_sector([sym_str])

    # OverviewSection
    sec_row: dict[str, Any] = {}
    if not sector_df.empty:
        row = sector_df.iloc[0]
        sec_row = {
            "sector_l1": str(row.get("sector_l1", "Unknown")),
            "sector_l2": row.get("sector_l2"),
        }
    else:
        sec_row = {"sector_l1": "Unknown", "sector_l2": None}

    latest_fund: pd.Series | None = None
    if not fundamentals.empty and "publication_date" in fundamentals.columns:
        latest_fund = fundamentals.sort_values("publication_date").iloc[-1]
    elif not fundamentals.empty:
        latest_fund = fundamentals.iloc[-1]

    overview = OverviewSection(
        symbol=sym,
        name_en=None,
        name_zh=None,
        sector_l1=str(sec_row.get("sector_l1", "Unknown")),
        sector_l2=str(sec_row["sector_l2"]) if sec_row.get("sector_l2") is not None else None,
        market_cap=float(latest_fund["market_cap"])
        if latest_fund is not None and "market_cap" in latest_fund.index
        else 0.0,
        market_cap_free_float=float(latest_fund.get("market_cap_free_float", 0.0))
        if latest_fund is not None
        else 0.0,
        is_soe=bool(latest_fund.get("is_soe", False)) if latest_fund is not None else False,
        is_stock_connect_eligible=bool(latest_fund.get("is_stock_connect_eligible", False))
        if latest_fund is not None
        else False,
        listing_date=None,
    )

    # FundamentalsSection
    def _get_series(col: str) -> pd.Series[float]:
        if fundamentals.empty or col not in fundamentals.columns:
            return cast("pd.Series[float]", pd.Series([], dtype=float))
        if "report_date" not in fundamentals.columns:
            return cast("pd.Series[float]", pd.Series([], dtype=float))
        sorted_f = fundamentals.sort_values("report_date")
        return cast("pd.Series[float]", sorted_f.set_index("report_date")[col].astype(float))

    latest_fy_year = asof.year - 1
    if not fundamentals.empty and "report_date" in fundamentals.columns:
        latest_fy_year = int(pd.to_datetime(fundamentals["report_date"]).max().year)

    fs = FundamentalsSection(
        revenue_series=_get_series("revenue"),
        net_income_series=_get_series("net_income"),
        operating_cash_flow_series=_get_series("operating_cash_flow"),
        capex_series=_get_series("capex"),
        roe_series=_get_series("roe"),
        roic_series=_get_series("roic"),
        gross_margin_series=_get_series("gross_margin"),
        net_margin_series=_get_series("net_margin"),
        latest_fiscal_year=latest_fy_year,
    )

    # OwnerEarningsSection
    oe_series = owner_earnings_series(fundamentals)
    oe = OwnerEarningsSection(
        series=oe_series,
        latest_fy=float(oe_series.iloc[-1]) if not oe_series.empty else 0.0,
        avg_10y=float(oe_series.mean()) if not oe_series.empty else 0.0,
        cv_10y=(
            float(oe_series.std() / abs(oe_series.mean()))
            if not oe_series.empty and oe_series.mean() != 0
            else 0.0
        ),
    )

    # ValuationBandsSection
    pe_band = compute_valuation_bands(sym_str, repo, asof, "pe", 10)
    pb_band = compute_valuation_bands(sym_str, repo, asof, "pb", 10)
    ps_band = compute_valuation_bands(sym_str, repo, asof, "ps", 10)
    vbs = ValuationBandsSection(
        pe_bands=pe_band.bands,
        pe_current=pe_band.current,
        pe_current_percentile=pe_band.current_percentile,
        pb_bands=pb_band.bands,
        pb_current=pb_band.current,
        pb_current_percentile=pb_band.current_percentile,
        ps_bands=ps_band.bands,
        ps_current=ps_band.current,
        ps_current_percentile=ps_band.current_percentile,
        window_years=pe_band.window_years,
    )
    if pe_band.window_years < 10:
        warnings.append(f"Valuation bands cover only {pe_band.window_years} years of history")

    # DividendSection
    grade = dividend_consistency_grade(corp_actions, asof, window_years=10)
    div_rows = (
        corp_actions[corp_actions["kind"] == "cash_dividend"].sort_values("ex_date")
        if not corp_actions.empty and "kind" in corp_actions.columns
        else pd.DataFrame()
    )
    dividend = DividendSection(
        history=div_rows.reset_index(drop=True),
        ttm_yield=0.0,
        cagr_5y=0.0,
        cagr_10y=0.0,
        n_consecutive_years=0,
        consistency_grade=grade,
    )

    # AHPremiumSection (if dual-listed)
    ah_section: AHPremiumSection | None = None
    pairs = load_ah_pairs()
    matching_pair: AHPair | None = next(
        (p for p in pairs if str(p.a_symbol) == sym_str or str(p.h_symbol) == sym_str),
        None,
    )
    if matching_pair is not None:
        other_leg = (
            matching_pair.h_symbol
            if str(matching_pair.a_symbol) == sym_str
            else matching_pair.a_symbol
        )
        try:
            premium_df = repo.compute_ah_premium(matching_pair, asof, asof)
            if premium_df is not None and len(premium_df) > 0:
                ah_section = AHPremiumSection(
                    paired_symbol=other_leg,
                    pair_name_en=matching_pair.name_en,
                    current_premium=float(premium_df["premium"].iloc[-1]),
                    current_z_score=0.0,
                    premium_2y_series=pd.DataFrame(),
                    historical_max={"value": 0.0, "date": asof},
                    historical_min={"value": 0.0, "date": asof},
                )
        except Exception as exc:
            warnings.append(f"AH premium unavailable: {exc}")

    # PeersSection (stub — peers require full universe scan, deferred)
    peers = PeersSection(peer_symbols=[], peer_table=pd.DataFrame())

    # Metadata
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            cwd="/Users/brian_huang/repos/ah-research",
        ).strip()
    except Exception:
        sha = "unknown"

    metadata = DossierMetadata(
        asof=asof,
        repo_snapshot_date=asof,
        code_version=sha,
        warnings=warnings,
    )

    return Dossier(
        symbol=sym,
        asof=asof,
        overview=overview,
        fundamentals=fs,
        owner_earnings=oe,
        valuation_bands=vbs,
        dividend_history=dividend,
        ah_premium=ah_section,
        peers=peers,
        metadata=metadata,
    )
