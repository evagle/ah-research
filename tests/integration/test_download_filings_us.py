from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "download_filings.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("download_filings_us", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


df = _load_module()


def test_canonical_ticker_accepts_us_research_symbol() -> None:
    assert df.canonical_ticker("abnb.us") == "ABNB.US"


def test_us_cli_requires_latest(capsys: pytest.CaptureFixture[str]) -> None:
    result = df.main(["ABNB.US", "--as-of", "2026-09-02"])

    assert result == 2
    assert "--latest" in capsys.readouterr().out


def test_us_cli_dispatches_only_to_sec_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "filing-manifest-2026-09-02.json"
    manifest.write_text("{}")
    calls: list[tuple[object, ...]] = []

    class FakeClient:
        def __init__(self, user_agent: str) -> None:
            calls.append(("client", user_agent))

    def build(ticker: str, as_of: date, out_dir: Path, client: object) -> Path:
        calls.append((ticker, as_of, out_dir, client.__class__.__name__))
        return manifest

    monkeypatch.setattr(df.sec_filings, "SecClient", FakeClient)
    monkeypatch.setattr(df.sec_filings, "build_filing_manifest", build)
    monkeypatch.setattr(df, "resolve_org_id", lambda *_args, **_kwargs: pytest.fail("CNINFO used"))
    monkeypatch.setattr(
        df, "search_hkex_annual_reports", lambda *_args, **_kwargs: pytest.fail("HKEX used")
    )

    result = df.main(
        [
            "abnb.us",
            "--latest",
            "--as-of",
            "2026-09-02",
            "--out",
            str(tmp_path / "ABNB.US"),
        ]
    )

    assert result == 0
    assert calls[1][0:2] == ("ABNB.US", date(2026, 9, 2))
    assert str(manifest) in capsys.readouterr().out


@pytest.mark.parametrize(
    "flags",
    (["--include-prospectus"], ["--lang", "zh"], ["--end-year", "2025"]),
)
def test_us_cli_rejects_annual_only_flags(
    flags: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    result = df.main(["ABNB.US", "--latest", *flags])

    assert result == 2
    assert "incompatible with .US" in capsys.readouterr().out


def test_revalidate_dispatches_by_us_manifest_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "us-sec-filing-manifest/1.0"}))
    monkeypatch.setattr(
        df.sec_filings,
        "revalidate_filing_manifest",
        lambda path, client: f"US revalidated {path}",
    )
    monkeypatch.setattr(df.sec_filings, "SecClient", lambda _user_agent: object())
    monkeypatch.setattr(
        df,
        "revalidate_annual_manifest",
        lambda _path: pytest.fail("annual revalidator used for US manifest"),
    )

    result = df.main(["--revalidate", str(manifest)])

    assert result == 0
    assert "US revalidated" in capsys.readouterr().out
