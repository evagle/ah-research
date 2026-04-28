import dataclasses
from datetime import date

import pytest

from ah_research.exceptions import UserInputError
from ah_research.model.types import (
    AHPair,
    CorporateAction,
    Currency,
    Exchange,
    Freq,
    IndexConstituent,
    parse_symbol,
)


def test_symbol_roundtrips_string():
    s = parse_symbol("600519.SH")
    assert s.code == "600519"
    assert s.exchange == Exchange.SH
    assert s.currency == Currency.CNY
    assert str(s) == "600519.SH"


def test_parse_symbol_hk():
    s = parse_symbol("0700.HK")
    assert s.exchange == Exchange.HK
    assert s.currency == Currency.HKD


def test_parse_symbol_sz():
    s = parse_symbol("000001.SZ")
    assert s.exchange == Exchange.SZ
    assert s.currency == Currency.CNY


def test_parse_symbol_invalid_raises():
    with pytest.raises(UserInputError):
        parse_symbol("NVDA")
    with pytest.raises(UserInputError):
        parse_symbol("600519.US")
    with pytest.raises(UserInputError):
        parse_symbol("")
    with pytest.raises(UserInputError):
        parse_symbol("600519")


def test_parse_symbol_error_message_includes_input():
    with pytest.raises(UserInputError, match="NVDA"):
        parse_symbol("NVDA")


def test_symbol_frozen():
    s = parse_symbol("600519.SH")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.code = "000001"  # type: ignore[misc]


def test_symbol_equality_and_hashable():
    a = parse_symbol("600519.SH")
    b = parse_symbol("600519.SH")
    assert a == b
    assert hash(a) == hash(b)
    # Usable as dict key / set element
    assert {a, b} == {a}


def test_ah_pair_construction():
    a = parse_symbol("601318.SH")
    h = parse_symbol("2318.HK")
    pair = AHPair(a_symbol=a, h_symbol=h, name_en="Ping An", name_zh="中国平安")
    assert pair.a_symbol.exchange == Exchange.SH
    assert pair.h_symbol.exchange == Exchange.HK


def test_ah_pair_rejects_non_a_and_non_h():
    a = parse_symbol("0700.HK")  # HK symbol in a_symbol slot — invalid
    h = parse_symbol("2318.HK")
    with pytest.raises(UserInputError):
        AHPair(a_symbol=a, h_symbol=h, name_en="x", name_zh="y")


def test_index_constituent_effective_to_none_means_current():
    c = IndexConstituent(
        index="CSI300",
        symbol=parse_symbol("600519.SH"),
        weight=0.048,
        effective_from=date(2015, 1, 1),
        effective_to=None,
    )
    assert c.effective_to is None


def test_index_constituent_rejects_backwards_dates():
    with pytest.raises(UserInputError):
        IndexConstituent(
            index="CSI300",
            symbol=parse_symbol("600519.SH"),
            weight=0.048,
            effective_from=date(2020, 6, 1),
            effective_to=date(2020, 1, 1),
        )


def test_corporate_action_dividend():
    ca = CorporateAction(
        symbol=parse_symbol("600519.SH"),
        ex_date=date(2024, 6, 15),
        kind="cash_dividend",
        params={"amount_per_share": 30.88, "currency": "CNY"},
    )
    assert ca.kind == "cash_dividend"
    assert ca.params["amount_per_share"] == 30.88


def test_corporate_action_rejects_unknown_kind():
    with pytest.raises(UserInputError):
        CorporateAction(
            symbol=parse_symbol("600519.SH"),
            ex_date=date(2024, 6, 15),
            kind="not_a_kind",  # type: ignore[arg-type]
            params={},
        )


def test_freq_enum_values():
    assert Freq.D.value == "D"
    assert Freq.W.value == "W"
    assert Freq.M.value == "M"
    assert Freq.Q.value == "Q"
