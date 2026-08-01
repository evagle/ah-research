from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "source-discovery"
    / "scripts"
    / "probe_source_reachability.py"
)
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "source-discovery" / "probes"
PROFILE_FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "source-discovery" / "profiles"


def load_probe_module():
    assert SCRIPT_PATH.is_file(), f"missing script: {SCRIPT_PATH}"
    spec = importlib.util.spec_from_file_location("probe_source_reachability", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_probe_fixture(name: str) -> str:
    path = FIXTURES_ROOT / name
    assert path.is_file(), f"missing fixture: {path}"
    return path.read_text(encoding="utf-8")


def load_profile_fixture(name: str) -> dict[str, Any]:
    path = PROFILE_FIXTURES_ROOT / name
    assert path.is_file(), f"missing fixture: {path}"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


@contextmanager
def serve_routes(routes: dict[str, tuple[int, dict[str, str], bytes]]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            status, headers, body = routes[self.path]
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def observation(
    module: Any,
    *,
    status_code: int | None = 200,
    final_url: str = "",
    redirect_chain=None,
    content_type: str = "text/html",
    title: str | None = None,
    body_excerpt: str = "",
    error_kind: str | None = None,
    error_message: str | None = None,
):
    if redirect_chain is None:
        redirect_chain = []
    return module.ProbeObservation(
        status_code=status_code,
        final_url=final_url,
        redirect_chain=redirect_chain,
        content_type=content_type,
        title=title,
        body_excerpt=body_excerpt,
        error_kind=error_kind,
        error_message=error_message,
    )


def test_classify_reachable_first_party_content() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://www.sse.com.cn/home/search/",
            title="Shanghai Stock Exchange Search",
            body_excerpt=load_probe_fixture("reachable.html"),
        ),
        expected_fingerprints=["sse.com.cn", "Shanghai Stock Exchange"],
    )

    assert result.status == "reachable"


def test_classify_error_page_served_with_200_as_broken_link() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://www.example.com/stale-path",
            title="Page Not Found",
            body_excerpt=load_probe_fixture("error-200.html"),
        ),
        expected_fingerprints=["example.com"],
    )

    assert result.status == "broken-link"


def test_classify_login_prompt_as_login_required() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://secure.example.com",
            title="Please Sign In",
            body_excerpt=load_probe_fixture("login.html"),
        ),
        expected_fingerprints=["secure.example.com"],
    )

    assert result.status == "login-required"


def test_classify_subscription_prompt_as_paywalled() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://reports.example.com",
            title="Subscriber Access",
            body_excerpt=load_probe_fixture("paywall.html"),
        ),
        expected_fingerprints=["reports.example.com"],
    )

    assert result.status == "paywalled"


def test_classify_waf_or_challenge_page_as_anti_bot() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            status_code=403,
            final_url="https://blocked.example.com",
            title="Security Check",
            body_excerpt=load_probe_fixture("waf.html"),
        ),
        expected_fingerprints=["blocked.example.com"],
    )

    assert result.status == "anti-bot"


@pytest.mark.parametrize("error_kind", ["timeout", "dns", "connection-reset"])
def test_classify_transient_probe_errors_as_temporarily_unreachable(error_kind: str) -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            status_code=None,
            error_kind=error_kind,
            error_message=f"simulated {error_kind}",
        ),
        expected_fingerprints=["example.com"],
    )

    assert result.status == "temporarily-unreachable"


@pytest.mark.parametrize("status_code", [404, 410])
def test_classify_404_and_410_as_broken_link(status_code: int) -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            status_code=status_code,
            final_url="https://www.example.com/missing",
            title="Page Not Found",
            body_excerpt=load_probe_fixture("error-200.html"),
        ),
        expected_fingerprints=["example.com"],
    )

    assert result.status == "broken-link"


def test_classify_redirect_to_matching_fingerprint_as_moved() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://www.sse.com.cn/home/search/",
            redirect_chain=[
                "https://www.sse.com.cn/old/search -> https://www.sse.com.cn/home/search/"
            ],
            title="Shanghai Stock Exchange Search",
            body_excerpt=load_probe_fixture("reachable.html"),
        ),
        expected_fingerprints=["sse.com.cn", "Shanghai Stock Exchange"],
    )

    assert result.status == "moved"


def test_classify_redirect_without_matching_fingerprint_as_unverified() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://elsewhere.example.net",
            redirect_chain=["https://www.example.com/start -> https://elsewhere.example.net"],
            title="Landing Page",
            body_excerpt="Generic landing page with no publisher markers.",
        ),
        expected_fingerprints=["expected-publisher.com", "Expected Publisher"],
    )

    assert result.status == "unverified"


def test_probe_url_records_redirects_and_extracts_title_and_excerpt() -> None:
    module = load_probe_module()
    reachable_html = load_probe_fixture("reachable.html").encode("utf-8")
    with serve_routes(
        {
            "/start": (302, {"Location": "/final"}, b""),
            "/final": (200, {"Content-Type": "text/html; charset=utf-8"}, reachable_html),
        }
    ) as base_url:
        observed = module.probe_url(
            f"{base_url}/start",
            timeout=1.0,
            user_agent="task-3-test-agent/1.0",
        )

    assert observed.status_code == 200
    assert observed.final_url == f"{base_url}/final"
    assert observed.redirect_chain == [f"{base_url}/start -> {base_url}/final"]
    assert observed.content_type == "text/html"
    assert observed.title == "Shanghai Stock Exchange Search"
    assert "Shanghai Stock Exchange" in observed.body_excerpt
    assert observed.error_kind is None
    assert observed.error_message is None


def test_cache_writes_atomically_and_round_trips_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_probe_module()
    cache_path = tmp_path / "tmp" / "source-discovery" / "reachability.json"
    payload = {
        "sse": {
            "status": "reachable",
            "last_checked": "2026-08-01T10:00:00+00:00",
        }
    }
    calls: list[tuple[Path, Path]] = []
    original_replace = module.os.replace

    def recording_replace(src: str | Path, dst: str | Path) -> None:
        calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(module.os, "replace", recording_replace)

    assert module.load_cache(cache_path) == {}
    module.write_cache(cache_path, payload)

    assert module.load_cache(cache_path) == payload
    assert calls == [(cache_path.with_name("reachability.json.tmp"), cache_path)]
    assert not list(cache_path.parent.glob("*.tmp"))


def test_cli_probes_selected_sources_and_updates_cache(tmp_path: Path) -> None:
    module = load_probe_module()
    reachable_html = load_probe_fixture("reachable.html").encode("utf-8")
    with serve_routes(
        {
            "/reachable": (200, {"Content-Type": "text/html; charset=utf-8"}, reachable_html),
        }
    ) as base_url:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        selected = deepcopy(load_profile_fixture("official-example.yaml"))
        selected["access"]["final_url"] = f"{base_url}/reachable"
        selected["functions"][0]["direct_urls"][0]["url"] = f"{base_url}/reachable"

        skipped = deepcopy(load_profile_fixture("aggregator-example.yaml"))
        skipped["access"]["final_url"] = f"{base_url}/reachable"
        skipped["functions"][0]["direct_urls"][0]["url"] = f"{base_url}/reachable"

        (profiles_dir / "official.yaml").write_text(
            yaml.safe_dump(selected, sort_keys=False),
            encoding="utf-8",
        )
        (profiles_dir / "aggregator.yaml").write_text(
            yaml.safe_dump(skipped, sort_keys=False),
            encoding="utf-8",
        )

        cache_path = tmp_path / "tmp" / "source-discovery" / "reachability.json"
        exit_code = module.main(
            [
                "--profiles",
                str(profiles_dir),
                "--cache",
                str(cache_path),
                "--source",
                "sse",
            ]
        )

    assert exit_code == 0
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert set(cache) == {"sse"}
    assert cache["sse"]["status"] == "reachable"
    assert cache["sse"]["final_url"] == f"{base_url}/reachable"
    assert cache["sse"]["status_code"] == 200


def test_tmp_source_discovery_directory_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-v", "tmp/source-discovery/reachability.json"],
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert ".gitignore" in result.stdout
    assert "tmp/source-discovery/" in result.stdout
