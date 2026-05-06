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
from ah_research.backtest.engine import resolve_benchmark, run_backtest
from ah_research.backtest.types import BacktestConfig, BacktestResult, Weights, hash_config
from tests.fixtures.phase2.synthetic_market import build_synthetic_market

# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def trading_days() -> list[date]:
    """Business-day list aligned with the default repo window."""
    return [d.date() for d in pd.bdate_range(date(2024, 1, 2), date(2024, 3, 29))]


@pytest.fixture
def repo() -> object:
    """Default repo with both A-share and HK symbols."""
    return build_synthetic_market(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        symbols=["600000.SH", "0001.HK"],
    )


@pytest.fixture
def repo_factory():
    """Callable factory for repos with custom symbol lists."""

    def _build(symbols: list[str]) -> object:
        return build_synthetic_market(
            start=date(2024, 1, 1),
            end=date(2024, 3, 31),
            symbols=symbols,
        )

    return _build


# ── resolve_benchmark: named specs ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("spec", "extra_symbols"),
    [
        # "zero" works without any extra symbols.
        ("zero", []),
        # CSI300_TR / HSI_TR need the index synthesized in the repo.
        ("CSI300_TR", ["000300.SH"]),
        ("HSI_TR", ["HSI.HK"]),
    ],
    ids=["zero", "CSI300_TR", "HSI_TR"],
)
def test_named_benchmark_returns_aligned_finite_series(
    spec: str,
    extra_symbols: list[str],
    trading_days: list[date],
    repo_factory,
) -> None:
    """Every supported named benchmark returns a NaN-free series indexed
    on the requested trading days."""
    repo = repo_factory(["600000.SH", "0001.HK", *extra_symbols])
    series = resolve_benchmark(
        spec, trading_days[0], trading_days[-1], repo, trading_days=trading_days
    )
    assert isinstance(series, pd.Series)
    assert len(series) == len(trading_days)
    assert series.notna().all()
    assert list(series.index) == [pd.Timestamp(d) for d in trading_days]


def test_zero_returns_constant_one(trading_days: list[date], repo: object) -> None:
    series = resolve_benchmark(
        "zero", trading_days[0], trading_days[-1], repo, trading_days=trading_days
    )
    assert (series == 1.0).all()


def test_csi300_normalised_to_positive_values(repo_factory, trading_days: list[date]) -> None:
    """CSI300_TR is a price series normalised to start at 1.0; must be > 0."""
    repo = repo_factory(["000300.SH", "600000.SH"])
    series = resolve_benchmark(
        "CSI300_TR", trading_days[0], trading_days[-1], repo, trading_days=trading_days
    )
    assert (series > 0).all()


# ── resolve_benchmark: explicit pd.Series passthrough ────────────────────────


def test_series_passthrough_fills_gaps_up_to_3_days(trading_days: list[date], repo: object) -> None:
    """Sparse Series with a 3-day gap is forward-filled cleanly."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in trading_days])
    src = pd.Series(range(len(trading_days)), index=idx, dtype=float)
    src_sparse = src.drop(idx[5:8])  # 3-day gap
    result = resolve_benchmark(
        src_sparse, trading_days[0], trading_days[-1], repo, trading_days=trading_days
    )
    assert result.notna().all()
    assert len(result) == len(trading_days)


def test_series_gap_over_3_days_warns(trading_days: list[date], repo: object) -> None:
    """Gap > 3 days emits a UserWarning about fill-limit being exceeded."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in trading_days])
    src = pd.Series(1.0, index=idx)
    src_sparse = src.drop(idx[10:15])  # 5-day gap
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = resolve_benchmark(
            src_sparse, trading_days[0], trading_days[-1], repo, trading_days=trading_days
        )
    assert any(
        "gap" in str(w.message).lower() or "fill" in str(w.message).lower() for w in caught
    ), f"Expected a gap/fill warning; got {[str(x.message) for x in caught]}"
    assert len(result) == len(trading_days)


# ── resolve_benchmark: error path ────────────────────────────────────────────


def test_unknown_spec_raises_value_error(trading_days: list[date], repo: object) -> None:
    with pytest.raises(ValueError, match="Unknown benchmark spec"):
        resolve_benchmark(
            "INVALID_SPEC",
            trading_days[0],
            trading_days[-1],
            repo,
            trading_days=trading_days,
        )


# ── BacktestResult metadata ──────────────────────────────────────────────────


class _FixedLongStrategy:
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


@pytest.fixture
def backtest_result() -> BacktestResult:
    """Single backtest run shared across metadata assertions."""
    repo = build_synthetic_market(
        start=date(2024, 1, 1), end=date(2024, 3, 31), symbols=["600000.SH"]
    )
    cfg = BacktestConfig(
        start=date(2024, 1, 2),
        end=date(2024, 3, 29),
        initial_cash=Decimal("1000000"),
        benchmark="zero",
        cost_model=CostModelBundle(models={}),
    )
    return run_backtest(_FixedLongStrategy(), repo, cfg)


def test_config_hash_is_64_char_hex(backtest_result: BacktestResult) -> None:
    assert len(backtest_result.config_hash) == 64
    int(backtest_result.config_hash, 16)  # must parse as hex


def test_code_version_populated(backtest_result: BacktestResult) -> None:
    assert backtest_result.code_version
    assert isinstance(backtest_result.code_version, str)


def test_benchmark_curve_aligned_to_equity_curve(backtest_result: BacktestResult) -> None:
    assert list(backtest_result.benchmark_curve.index) == list(backtest_result.equity_curve.index)
    assert backtest_result.benchmark_curve.notna().all()


@pytest.mark.parametrize(
    ("override", "should_match"),
    [
        # Same config => same hash.
        ({}, True),
        # Different initial_cash => different hash.
        ({"initial_cash": Decimal("2000000")}, False),
    ],
    ids=["identical-configs", "differing-cash"],
)
def test_hash_config_responds_to_field_changes(
    override: dict[str, object], should_match: bool
) -> None:
    defaults: dict[str, object] = {
        "start": date(2024, 1, 2),
        "end": date(2024, 3, 29),
        "initial_cash": Decimal("1000000"),
        "benchmark": "zero",
    }
    base = BacktestConfig(**defaults)  # type: ignore[arg-type]
    other = BacktestConfig(**{**defaults, **override})  # type: ignore[arg-type]
    if should_match:
        assert hash_config(base) == hash_config(other)
    else:
        assert hash_config(base) != hash_config(other)
