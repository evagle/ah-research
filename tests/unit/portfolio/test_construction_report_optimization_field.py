from __future__ import annotations

import pandas as pd

from ah_research.portfolio.constructor import ConstructionReport


def test_construction_report_has_optimization_result_field_defaulting_to_none() -> None:
    report = ConstructionReport(
        weights=pd.DataFrame({"symbol": ["600519.SH"], "weight": [1.0]}),
        final_position_count=1,
        constraint_results=[],
        method_used="top_quantile",
        weighting_scheme="equal",
    )
    assert report.optimization_result is None
