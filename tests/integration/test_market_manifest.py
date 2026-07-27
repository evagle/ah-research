from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_market_manifest


def _valid_bodies() -> dict[str, bytes]:
    return {
        "https://www.szse.cn/market/price": (
            b'{"data":{"close":12.5,"date":"2026-04-30",'
            b'"issuer_code":"000001"},"meta":{'
            b'"latest_observation_date":"2026-04-30"}}'
        ),
        "https://www.chinamoney.com.cn/rates": (
            b'{"data":{"yield":1.85,"date":"2026-04-30","tenor":"10Y"},'
            b'"meta":{"latest_observation_date":"2026-04-30"}}'
        ),
    }


def _binding_pressure_bodies() -> dict[str, bytes]:
    return {
        "https://www.szse.cn/market/price": json.dumps(
            {
                "data": {
                    "close": 12.5,
                    "date": "2026-04-30",
                    "other_date": "2026-04-29",
                    "issuer_code": "000001",
                    "other_issuer_code": "000002",
                },
                "meta": {
                    "latest_observation_date": "2026-04-30",
                    "other_latest_observation_date": "2026-04-29",
                },
            }
        ).encode(),
        "https://www.chinamoney.com.cn/rates": json.dumps(
            {
                "data": {
                    "yield": 1.85,
                    "date": "2026-04-30",
                    "other_date": "2026-04-29",
                    "tenor": "10Y",
                    "other_tenor": "1Y",
                },
                "meta": {
                    "latest_observation_date": "2026-04-30",
                    "other_latest_observation_date": "2026-04-29",
                },
            }
        ).encode(),
    }


def _plan(tmp_path: Path) -> Path:
    path = tmp_path / "market-plan.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ticker": "000001.SZ",
                "AS_OF": "2026-04-30",
                "price": {
                    "source_id": "szse",
                    "source_url": "https://www.szse.cn/market/price",
                    "http_method": "GET",
                    "request_encoding": "query",
                    "query_params": {
                        "issuer_code": "000001",
                        "date": "2026-04-30",
                    },
                    "value_path": ["data", "close"],
                    "date_path": ["data", "date"],
                    "latest_observation_date_path": [
                        "meta",
                        "latest_observation_date",
                    ],
                    "max_observation_age_days": 3,
                    "identity_path": ["data", "issuer_code"],
                    "unit": "CNY",
                },
                "risk_free_rate": {
                    "source_id": "chinamoney",
                    "source_url": "https://www.chinamoney.com.cn/rates",
                    "http_method": "GET",
                    "request_encoding": "query",
                    "query_params": {"date": "2026-04-30", "tenor": "10Y"},
                    "value_path": ["data", "yield"],
                    "date_path": ["data", "date"],
                    "latest_observation_date_path": [
                        "meta",
                        "latest_observation_date",
                    ],
                    "max_observation_age_days": 3,
                    "tenor_path": ["data", "tenor"],
                    "unit": "percent",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_market_manifest_builds_and_live_revalidates(tmp_path: Path) -> None:
    bodies = {
        "https://www.szse.cn/market/price": json.dumps(
            {
                "data": {
                    "close": 12.5,
                    "date": "2026-04-30",
                    "issuer_code": "000001",
                },
                "meta": {"latest_observation_date": "2026-04-30"},
            }
        ).encode(),
        "https://www.chinamoney.com.cn/rates": json.dumps(
            {
                "data": {
                    "yield": 1.85,
                    "date": "2026-04-30",
                    "tenor": "10Y",
                },
                "meta": {"latest_observation_date": "2026-04-30"},
            }
        ).encode(),
    }

    manifest_path = build_market_manifest.build_manifest(
        _plan(tmp_path),
        tmp_path / "market-data.json",
        tmp_path / "evidence",
        fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["price"]["value"] == 12.5
    assert manifest["risk_free_rate"]["value"] == 1.85
    for field in ("price", "risk_free_rate"):
        row = manifest[field]
        assert Path(row["raw_response_path"]).is_file()
        assert row["response_sha256"] == hashlib.sha256(bodies[row["source_url"]]).hexdigest()
    assert (
        build_market_manifest.revalidate_manifest(
            manifest_path,
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )
        == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )


def test_market_manifest_rejects_live_drift(tmp_path: Path) -> None:
    initial = _valid_bodies()
    manifest_path = build_market_manifest.build_manifest(
        _plan(tmp_path),
        tmp_path / "market-data.json",
        tmp_path / "evidence",
        fetcher=lambda url, _method, _encoding, _params, _headers: initial[url],
    )
    changed = dict(initial)
    changed["https://www.szse.cn/market/price"] = (
        b'{"data":{"close":13.0,"date":"2026-04-30",'
        b'"issuer_code":"000001"},"meta":{'
        b'"latest_observation_date":"2026-04-30"}}'
    )

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="live response",
    ):
        build_market_manifest.revalidate_manifest(
            manifest_path,
            fetcher=lambda url, _method, _encoding, _params, _headers: changed[url],
        )


def test_market_manifest_revalidation_rejects_tampered_derived_value(
    tmp_path: Path,
) -> None:
    bodies = _valid_bodies()
    manifest_path = build_market_manifest.build_manifest(
        _plan(tmp_path),
        tmp_path / "market-data.json",
        tmp_path / "evidence",
        fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["price"]["value"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="derived value",
    ):
        build_market_manifest.revalidate_manifest(
            manifest_path,
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


def test_market_manifest_revalidation_wraps_invalid_stored_value(
    tmp_path: Path,
) -> None:
    bodies = _valid_bodies()
    manifest_path = build_market_manifest.build_manifest(
        _plan(tmp_path),
        tmp_path / "market-data.json",
        tmp_path / "evidence",
        fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["price"]["value"] = "not-a-number"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="stored value",
    ):
        build_market_manifest.revalidate_manifest(
            manifest_path,
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


@pytest.mark.parametrize(
    ("label", "container", "field", "value", "message"),
    (
        ("price", "query_params", "issuer_code", "000002", "identity"),
        (
            "price",
            None,
            "identity_path",
            ["data", "other_issuer_code"],
            "identity",
        ),
        ("price", "query_params", "date", "2026-04-29", "date"),
        (
            "price",
            None,
            "date_path",
            ["data", "other_date"],
            "latest observation date",
        ),
        (
            "price",
            None,
            "latest_observation_date_path",
            ["meta", "other_latest_observation_date"],
            "latest observation date",
        ),
        (
            "price",
            None,
            "latest_observation_date_path",
            ["data", "date"],
            "latest observation date path",
        ),
        (
            "price",
            None,
            "latest_observation_date",
            "2026-04-29",
            "latest observation date",
        ),
        ("risk_free_rate", "query_params", "tenor", "1Y", "tenor"),
        (
            "risk_free_rate",
            None,
            "tenor_path",
            ["data", "other_tenor"],
            "tenor",
        ),
        ("price", None, "unit", "HKD", "unit"),
        ("risk_free_rate", None, "unit", "decimal", "unit"),
    ),
)
def test_market_manifest_revalidation_rejects_tampered_bindings(
    tmp_path: Path,
    label: str,
    container: str | None,
    field: str,
    value: object,
    message: str,
) -> None:
    bodies = _binding_pressure_bodies()
    manifest_path = build_market_manifest.build_manifest(
        _plan(tmp_path),
        tmp_path / "market-data.json",
        tmp_path / "evidence",
        fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = manifest[label]
    if container is None:
        row[field] = value
        if field == "date_path":
            row["market_date"] = "2026-04-29"
    else:
        row[container][field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match=message,
    ):
        build_market_manifest.revalidate_manifest(
            manifest_path,
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


def test_market_manifest_rejects_noncanonical_ticker_and_unapproved_source(
    tmp_path: Path,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["ticker"] = "WRONG"
    plan["price"]["source_url"] = "https://example.com/price"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(build_market_manifest.MarketManifestError):
        build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda *_args: b'{"data":{"close":1,"date":"2026-04-30"}}',
        )


def test_market_manifest_rejects_wrong_issuer_stale_price_and_wrong_tenor(
    tmp_path: Path,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["price"]["query_params"]["issuer_code"] = "000002"
    plan["risk_free_rate"]["query_params"]["tenor"] = "1Y"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    bodies = {
        "https://www.szse.cn/market/price": (
            b'{"data":{"close":12.5,"date":"2000-01-04","issuer_code":"000002"}}'
        ),
        "https://www.chinamoney.com.cn/rates": (
            b'{"data":{"yield":1.85,"date":"2026-04-30","tenor":"1Y"}}'
        ),
    }

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match=r"identity|date|tenor",
    ):
        build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


@pytest.mark.parametrize(
    ("label", "binding_path"),
    (
        ("price", "identity_path"),
        ("price", "latest_observation_date_path"),
        ("risk_free_rate", "tenor_path"),
        ("risk_free_rate", "latest_observation_date_path"),
    ),
)
def test_market_manifest_requires_label_binding_paths(
    tmp_path: Path,
    label: str,
    binding_path: str,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    del plan[label][binding_path]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    bodies = _valid_bodies()

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match=f"{label} request is incomplete",
    ):
        build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


@pytest.mark.parametrize("label", ("price", "risk_free_rate"))
def test_market_manifest_requires_distinct_observation_date_paths(
    tmp_path: Path,
    label: str,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan[label]["latest_observation_date_path"] = plan[label]["date_path"]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    bodies = _valid_bodies()

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="latest observation date path",
    ):
        build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


@pytest.mark.parametrize("label", ("price", "risk_free_rate"))
def test_market_manifest_requires_source_observation_age(
    tmp_path: Path,
    label: str,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    del plan[label]["max_observation_age_days"]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    bodies = _valid_bodies()

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="incomplete",
    ):
        build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


@pytest.mark.parametrize(
    "value",
    (None, 0, -1, 1.5, True, "3"),
)
def test_market_manifest_rejects_invalid_source_observation_age(
    tmp_path: Path,
    value: object,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["price"]["max_observation_age_days"] = value
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    bodies = _valid_bodies()

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="max_observation_age_days",
    ):
        build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


def _bodies_with_observation_date(label: str, observed_date: str) -> dict[str, bytes]:
    bodies = _valid_bodies()
    if label == "price":
        bodies["https://www.szse.cn/market/price"] = json.dumps(
            {
                "data": {
                    "close": 12.5,
                    "date": observed_date,
                    "issuer_code": "000001",
                },
                "meta": {"latest_observation_date": observed_date},
            }
        ).encode()
    else:
        bodies["https://www.chinamoney.com.cn/rates"] = json.dumps(
            {
                "data": {
                    "yield": 1.85,
                    "date": observed_date,
                    "tenor": "10Y",
                },
                "meta": {"latest_observation_date": observed_date},
            }
        ).encode()
    return bodies


@pytest.mark.parametrize("label", ("price", "risk_free_rate"))
def test_market_manifest_accepts_source_age_boundary(
    tmp_path: Path,
    label: str,
) -> None:
    bodies = _bodies_with_observation_date(label, "2026-04-27")

    manifest_path = build_market_manifest.build_manifest(
        _plan(tmp_path),
        tmp_path / "market-data.json",
        tmp_path / "evidence",
        fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest[label]["max_observation_age_days"] == 3


@pytest.mark.parametrize("label", ("price", "risk_free_rate"))
def test_market_manifest_rejects_source_age_boundary_plus_one(
    tmp_path: Path,
    label: str,
) -> None:
    bodies = _bodies_with_observation_date(label, "2026-04-26")

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="max_observation_age_days",
    ):
        build_market_manifest.build_manifest(
            _plan(tmp_path),
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


def test_market_manifest_revalidation_enforces_tampered_source_age(
    tmp_path: Path,
) -> None:
    bodies = _bodies_with_observation_date("price", "2026-04-28")
    manifest_path = build_market_manifest.build_manifest(
        _plan(tmp_path),
        tmp_path / "market-data.json",
        tmp_path / "evidence",
        fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["price"]["max_observation_age_days"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="max_observation_age_days",
    ):
        build_market_manifest.revalidate_manifest(
            manifest_path,
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


@pytest.mark.parametrize(
    ("label", "parameter", "value", "message"),
    (
        ("price", "issuer_code", "000002", "identity"),
        ("price", "date", "2026-04-29", "date"),
        ("risk_free_rate", "date", "2026-04-29", "date"),
        ("risk_free_rate", "tenor", "1Y", "tenor"),
    ),
)
def test_market_manifest_binds_request_parameters(
    tmp_path: Path,
    label: str,
    parameter: str,
    value: str,
    message: str,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan[label]["query_params"][parameter] = value
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    bodies = _valid_bodies()

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match=message,
    ):
        build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


@pytest.mark.parametrize(
    ("label", "unit"),
    (("price", "HKD"), ("risk_free_rate", "decimal")),
)
def test_market_manifest_rejects_noncanonical_units(
    tmp_path: Path,
    label: str,
    unit: str,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan[label]["unit"] = unit
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    bodies = _valid_bodies()

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="unit",
    ):
        build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


@pytest.mark.parametrize(
    ("unit", "should_pass"),
    (("HKD", True), ("CNY", False)),
)
def test_market_manifest_requires_hkd_for_hk_price(
    tmp_path: Path,
    unit: str,
    should_pass: bool,
) -> None:
    plan_path = _plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["ticker"] = "00005.HK"
    plan["price"].update(
        {
            "source_id": "hkex",
            "source_url": "https://www.hkex.com.hk/market/price",
            "unit": unit,
        }
    )
    plan["price"]["query_params"]["issuer_code"] = "00005"
    plan["risk_free_rate"].update(
        {
            "source_id": "hkma",
            "source_url": "https://www.hkma.gov.hk/rates",
        }
    )
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    bodies = {
        "https://www.hkex.com.hk/market/price": (
            b'{"data":{"close":12.5,"date":"2026-04-30",'
            b'"issuer_code":"00005"},"meta":{'
            b'"latest_observation_date":"2026-04-30"}}'
        ),
        "https://www.hkma.gov.hk/rates": (
            b'{"data":{"yield":1.85,"date":"2026-04-30","tenor":"10Y"},'
            b'"meta":{"latest_observation_date":"2026-04-30"}}'
        ),
    }

    def build() -> Path:
        return build_market_manifest.build_manifest(
            plan_path,
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )

    if should_pass:
        assert build().is_file()
    else:
        with pytest.raises(
            build_market_manifest.MarketManifestError,
            match="unit",
        ):
            build()


@pytest.mark.parametrize(
    ("response_url", "response_body", "message"),
    (
        (
            "https://www.szse.cn/market/price",
            (
                b'{"data":{"close":12.5,"date":"2026-04-30",'
                b'"issuer_code":"000002"},"meta":{'
                b'"latest_observation_date":"2026-04-30"}}'
            ),
            "identity",
        ),
        (
            "https://www.chinamoney.com.cn/rates",
            (
                b'{"data":{"yield":1.85,"date":"2026-04-30","tenor":"1Y"},'
                b'"meta":{"latest_observation_date":"2026-04-30"}}'
            ),
            "tenor",
        ),
    ),
)
def test_market_manifest_binds_response_identity_and_tenor(
    tmp_path: Path,
    response_url: str,
    response_body: bytes,
    message: str,
) -> None:
    bodies = _valid_bodies()
    bodies[response_url] = response_body

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match=message,
    ):
        build_market_manifest.build_manifest(
            _plan(tmp_path),
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )


def test_market_manifest_accepts_official_latest_prior_observation(
    tmp_path: Path,
) -> None:
    bodies = {
        "https://www.szse.cn/market/price": json.dumps(
            {
                "data": {
                    "close": 12.5,
                    "date": "2026-04-29",
                    "issuer_code": "000001",
                },
                "meta": {"latest_observation_date": "2026-04-29"},
            }
        ).encode(),
        "https://www.chinamoney.com.cn/rates": (
            b'{"data":{"yield":1.85,"date":"2026-04-30","tenor":"10Y"},'
            b'"meta":{"latest_observation_date":"2026-04-30"}}'
        ),
    }

    manifest_path = build_market_manifest.build_manifest(
        _plan(tmp_path),
        tmp_path / "market-data.json",
        tmp_path / "evidence",
        fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["price"]["market_date"] == "2026-04-29"
    assert manifest["price"]["latest_observation_date"] == "2026-04-29"


def test_market_manifest_rejects_selected_date_before_official_latest(
    tmp_path: Path,
) -> None:
    bodies = {
        "https://www.szse.cn/market/price": (
            b'{"data":{"close":12.5,"date":"2026-04-28",'
            b'"issuer_code":"000001"},"meta":{'
            b'"latest_observation_date":"2026-04-29"}}'
        ),
        "https://www.chinamoney.com.cn/rates": _valid_bodies()[
            "https://www.chinamoney.com.cn/rates"
        ],
    }

    with pytest.raises(
        build_market_manifest.MarketManifestError,
        match="latest observation date",
    ):
        build_market_manifest.build_manifest(
            _plan(tmp_path),
            tmp_path / "market-data.json",
            tmp_path / "evidence",
            fetcher=lambda url, _method, _encoding, _params, _headers: bodies[url],
        )
