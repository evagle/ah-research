import pandas as pd
import pytest

from ah_research.portfolio.optimizer.result import OptimizationResult


def _fixture() -> OptimizationResult:
    return OptimizationResult(
        weights=pd.Series({"600519.SH": 0.6, "000858.SZ": 0.4}),
        objective="mean_variance",
        solver_status="optimal",
        objective_value=-0.0123,
        active_constraints=("max_weight",),
        slack={},
        expected_return=0.08,
        expected_variance=0.02,
        risk_contributions=None,
        solver_name="osqp",
        solve_time_ms=15.3,
        inputs_hash="a" * 64,
    )


def test_result_is_frozen():
    r = _fixture()
    with pytest.raises((AttributeError, Exception)):
        r.objective_value = 999.0


def test_to_dict_has_all_fields():
    r = _fixture()
    d = r.to_dict()
    assert d["objective"] == "mean_variance"
    assert d["weights"] == {"600519.SH": 0.6, "000858.SZ": 0.4}
    assert d["solver_status"] == "optimal"
    assert d["active_constraints"] == ["max_weight"]
    assert d["solve_time_ms"] == 15.3
    assert d["inputs_hash"] == "a" * 64


def test_to_markdown_includes_weights_and_status():
    r = _fixture()
    md = r.to_markdown()
    assert "600519.SH" in md
    assert "0.6" in md
    assert "optimal" in md
    assert "mean_variance" in md


def test_risk_parity_result_has_risk_contributions():
    rc = pd.Series({"600519.SH": 0.5, "000858.SZ": 0.5})
    r = OptimizationResult(
        weights=pd.Series({"600519.SH": 0.55, "000858.SZ": 0.45}),
        objective="risk_parity",
        solver_status="optimal",
        objective_value=0.01,
        active_constraints=(),
        slack={},
        expected_return=None,
        expected_variance=0.015,
        risk_contributions=rc,
        solver_name="clarabel",
        solve_time_ms=40.0,
        inputs_hash="b" * 64,
    )
    md = r.to_markdown()
    assert "Risk contributions" in md
    assert r.to_dict()["risk_contributions"] == {"600519.SH": 0.5, "000858.SZ": 0.5}


def test_hash_is_sha256_string():
    r = _fixture()
    assert len(r.inputs_hash) == 64
