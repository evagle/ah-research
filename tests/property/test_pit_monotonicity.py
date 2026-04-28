"""Hypothesis property: PIT filter is monotone in asof.

For any asof date D within the analysis window, the returned frame must
contain NO rows with ``publication_date > D`` or ``known_as_of > D``.
Additionally, asof1 <= asof2 implies row-set(asof1) ⊆ row-set(asof2).
"""

from datetime import date, timedelta

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_ANALYSIS_START = date(2020, 1, 1)
_ANALYSIS_END = date(2024, 12, 31)
_WINDOW_DAYS = (_ANALYSIS_END - _ANALYSIS_START).days

# The `repo` fixture is function-scoped; hypothesis warns because it is not
# reset between generated inputs. That is intentional here — the cache is
# monotonically growing, so reusing it across examples is semantically fine
# (and much faster than re-priming per example).
_pit_settings = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@given(asof_offset=st.integers(min_value=0, max_value=_WINDOW_DAYS))
@_pit_settings
def test_get_fundamentals_asof_never_includes_future(repo, asof_offset):
    asof = _ANALYSIS_START + timedelta(days=asof_offset)
    df = repo.get_fundamentals(["600519.SH"], _ANALYSIS_START, _ANALYSIS_END, asof=asof)
    if len(df) > 0:
        assert (df["publication_date"] <= pd.Timestamp(asof)).all()
        assert (df["known_as_of"] <= pd.Timestamp(asof)).all()


@given(
    offsets=st.tuples(
        st.integers(min_value=0, max_value=_WINDOW_DAYS),
        st.integers(min_value=0, max_value=_WINDOW_DAYS),
    )
)
@_pit_settings
def test_get_fundamentals_asof_is_monotone(repo, offsets):
    a, b = sorted(offsets)
    asof_early = _ANALYSIS_START + timedelta(days=a)
    asof_late = _ANALYSIS_START + timedelta(days=b)
    df_early = repo.get_fundamentals(["600519.SH"], _ANALYSIS_START, _ANALYSIS_END, asof=asof_early)
    df_late = repo.get_fundamentals(["600519.SH"], _ANALYSIS_START, _ANALYSIS_END, asof=asof_late)
    # Every report_date present at the early asof must also be present later,
    # since publications are additive in time (strict supersetness of the
    # "visible report_date" set).
    early_reports = set(df_early["report_date"])
    late_reports = set(df_late["report_date"])
    assert early_reports.issubset(late_reports)
