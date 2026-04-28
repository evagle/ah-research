"""Hypothesis property test: Symbol parsing / stringification round-trip."""

from hypothesis import given
from hypothesis import strategies as st

from ah_research.model.types import parse_symbol

_sh_sz_codes = st.from_regex(r"^[0-9]{6}$", fullmatch=True)
_hk_codes = st.from_regex(r"^[0-9]{4,5}$", fullmatch=True)


@given(code=_sh_sz_codes)
def test_sh_symbol_roundtrips(code: str) -> None:
    s = parse_symbol(f"{code}.SH")
    assert str(s) == f"{code}.SH"
    assert s.code == code
    assert s.exchange.value == "SH"
    assert s.currency.value == "CNY"


@given(code=_sh_sz_codes)
def test_sz_symbol_roundtrips(code: str) -> None:
    s = parse_symbol(f"{code}.SZ")
    assert str(s) == f"{code}.SZ"
    assert s.exchange.value == "SZ"


@given(code=_hk_codes)
def test_hk_symbol_roundtrips(code: str) -> None:
    s = parse_symbol(f"{code}.HK")
    assert str(s) == f"{code}.HK"
    assert s.exchange.value == "HK"
    assert s.currency.value == "HKD"
