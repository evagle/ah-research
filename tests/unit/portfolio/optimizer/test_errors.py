from ah_research.portfolio.optimizer.errors import (
    InfeasibleError,
    NumericalError,
    OptimizerError,
    ValidationError,
)


def test_all_errors_derive_from_optimizer_error():
    for cls in (InfeasibleError, NumericalError, ValidationError):
        assert issubclass(cls, OptimizerError)


def test_optimizer_error_derives_from_exception():
    assert issubclass(OptimizerError, Exception)


def test_infeasible_error_carries_constraint_summary():
    err = InfeasibleError(
        "problem is infeasible",
        constraints_summary="max_weight=0.1; sector_neutral_to={'tech': 0.5}",
    )
    assert "infeasible" in str(err)
    assert err.constraints_summary is not None
    assert "max_weight" in err.constraints_summary
