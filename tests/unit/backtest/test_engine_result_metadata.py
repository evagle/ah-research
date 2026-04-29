"""Tests for engine result metadata: benchmark resolution, config_hash, code_version.

Task 19: resolve_benchmark(spec, start, end, repo) -> pd.Series
  - "zero"       -> constant 1.0 series over trading days
  - pd.Series    -> reindex + ffill up to 3 days
  - "CSI300_TR"  -> repo.get_prices(["000300.SH"], ...) total_return col
  - "HSI_TR"     -> repo.get_prices(["HSI.HK"], ...) total_return col
  - anything else -> ValueError
config_hash and code_version are populated on every BacktestResult.
"""

from __future__ import annotations

import warnings
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from ah_research.backtest.costs import CostModelBundle
from ah_research.backtest.engine import resolve_benchmark
from ah_research.backtest.types import BacktestConfig
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ── Shared fixture ────────────────────────────────────────────────────────────


def _make_repo(start: date = date(2024, 1, 1), end: date = date(2024, 3, 31)) -> object:
    return build_synthetic_market(
        start=start,
        end=end,
        symbols=["600000.SH", "0001.HK"],
    )


def _trading_days(start: date = date(2024, 1, 2), end: date = date(2024, 3, 29)) -> list[date]:
    bdates = pd.bdate_range(start, end)
    return [d.date() for d in bdates]


# ── resolve_benchmark ─────────────────────────────────────────────────────────


class TestResolveBenchmarkZero:
    def test_zero_returns_constant_one(self) -> None:
        days = _trading_days()
        repo = _make_repo()
        series = resolve_benchmark("zero", days[0], days[-1], repo, trading_days=days)
        assert (series == 1.0).all()
        assert len(series) == len(days)

    def test_zero_index_matches_trading_days(self) -> None:
        days = _trading_days()
        repo = _make_repo()
        series = resolve_benchmark("zero", days[0], days[-1], repo, trading_days=days)
        expected_idx = pd.DatetimeIndex([pd.Timestamp(d) for d in days])
        assert list(series.index) == list(expected_idx)


class TestResolveBenchmarkSeries:
    def test_series_passthrough_reindexed(self) -> None:
        days = _trading_days()
        repo = _make_repo()
        # Provide a series on a subset of days (with a gap)
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d in days])
        values = list(range(len(days)))
        src = pd.Series(values, index=idx, dtype=float)
        # Drop a few points in the middle to create gaps
        src_sparse = src.drop(idx[5:8])
        result = resolve_benchmark(src_sparse, days[0], days[-1], repo, trading_days=days)
        # Forward-filled up to 3 days → the 3-day gap should be filled
        assert result.notna().all()
        assert len(result) == len(days)

    def test_series_gaps_gt_3_warns_and_fills_limit(self) -> None:
        days = _trading_days()
        repo = _make_repo()
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d in days])
        src = pd.Series(1.0, index=idx)
        # Create a 5-day gap (days 10-14 removed)
        src_sparse = src.drop(idx[10:15])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = resolve_benchmark(src_sparse, days[0], days[-1], repo, trading_days=days)
        # Should warn about gaps > 3 days
        assert any(
            "gap" in str(warning.message).lower() or "fill" in str(warning.message).lower()
            for warning in w
        ), f"Expected a warning; got {[str(x.message) for x in w]}"
        # Result should still have the right length
        assert len(result) == len(days)


class TestResolveBenchmarkCSI300:
    def test_csi300_tr_returns_series(self) -> None:
        days = _trading_days()
        repo = _make_repo()
        series = resolve_benchmark("CSI300_TR", days[0], days[-1], repo, trading_days=days)
        assert isinstance(series, pd.Series)
        assert len(series) > 0
        assert series.notna().all()
        # Should be aligned to trading days
        assert list(series.index) == [pd.Timestamp(d) for d in days]

    def test_csi300_tr_uses_prices(self) -> None:
        """CSI300_TR should use repo price data (total_return or close_hfq)."""
        start = date(2024, 1, 1)
        end = date(2024, 3, 31)
        # Build a repo that includes 000300.SH
        repo = build_synthetic_market(
            start=start,
            end=end,
            symbols=["000300.SH", "600000.SH"],
        )
        days = _trading_days()
        series = resolve_benchmark("CSI300_TR", days[0], days[-1], repo, trading_days=days)
        # Should be positive (it's a price series normalized to first bar)
        assert (series > 0).all()


class TestResolveBenchmarkHSI:
    def test_hsi_tr_returns_series(self) -> None:
        start = date(2024, 1, 1)
        end = date(2024, 3, 31)
        repo = build_synthetic_market(
            start=start,
            end=end,
            symbols=["HSI.HK", "0001.HK"],
        )
        days = _trading_days()
        series = resolve_benchmark("HSI_TR", days[0], days[-1], repo, trading_days=days)
        assert isinstance(series, pd.Series)
        assert len(series) > 0
        assert series.notna().all()


class TestResolveBenchmarkUnknown:
    def test_unknown_spec_raises_value_error(self) -> None:
        days = _trading_days()
        repo = _make_repo()
        with pytest.raises(ValueError, match="Unknown benchmark spec"):
            resolve_benchmark("INVALID_SPEC", days[0], days[-1], repo, trading_days=days)


# ── BacktestResult metadata ────────────────────────────────────────────────────


class TestBacktestResultMetadata:
    def _run(self, benchmark: str = "zero") -> object:
        from ah_research.backtest.engine import run_backtest
        from ah_research.backtest.types import Weights

        class FixedLongStrategy:
            name = "fixed_long"

            def generate(self, repo: object, start: date, end: date) -> Weights:
                eom = pd.date_range(start, end, freq="ME")
                df = pd.DataFrame(
                    {
                        "date": eom,
                        "symbol": ["600000.SH"] * len(eom),
                        "weight": [1.0] * len(eom),
                    }
                )
                return Weights.from_dataframe(df)

        repo = build_synthetic_market(
            start=date(2024, 1, 1),
            end=date(2024, 3, 31),
            symbols=["600000.SH"],
        )
        cfg = BacktestConfig(
            start=date(2024, 1, 2),
            end=date(2024, 3, 29),
            initial_cash=Decimal("1000000"),
            benchmark=benchmark,
            cost_model=CostModelBundle(models={}),
        )
        return run_backtest(FixedLongStrategy(), repo, cfg)

    def test_result_has_64_char_config_hash(self) -> None:
        result = self._run()
        assert len(result.config_hash) == 64, f"Expected 64 chars, got {len(result.config_hash)}"
        # Must be hex
        int(result.config_hash, 16)

    def test_result_has_non_empty_code_version(self) -> None:
        result = self._run()
        assert result.code_version, "code_version must be non-empty"
        assert isinstance(result.code_version, str)

    def test_different_configs_produce_different_hashes(self) -> None:
        from ah_research.backtest.types import hash_config

        cfg1 = BacktestConfig(
            start=date(2024, 1, 2),
            end=date(2024, 3, 29),
            initial_cash=Decimal("1000000"),
            benchmark="zero",
        )
        cfg2 = BacktestConfig(
            start=date(2024, 1, 2),
            end=date(2024, 3, 29),
            initial_cash=Decimal("2000000"),  # different
            benchmark="zero",
        )
        assert hash_config(cfg1) != hash_config(cfg2)

    def test_same_config_produces_same_hash(self) -> None:
        from ah_research.backtest.types import hash_config

        cfg1 = BacktestConfig(
            start=date(2024, 1, 2),
            end=date(2024, 3, 29),
            initial_cash=Decimal("1000000"),
            benchmark="zero",
        )
        cfg2 = BacktestConfig(
            start=date(2024, 1, 2),
            end=date(2024, 3, 29),
            initial_cash=Decimal("1000000"),
            benchmark="zero",
        )
        assert hash_config(cfg1) == hash_config(cfg2)

    def test_benchmark_curve_aligned_to_equity_curve(self) -> None:
        result = self._run()
        assert list(result.benchmark_curve.index) == list(result.equity_curve.index)
        assert result.benchmark_curve.notna().all()
