from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError

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
        expected_fingerprints=["sse.com.cn"],
    )

    assert result.status == "reachable"


def test_classify_reachable_from_meaningful_body_fingerprint() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://publisher-cdn.example.net/report",
            title="Market disclosures",
            body_excerpt="Official Shanghai Stock Exchange announcements and disclosure search.",
        ),
        expected_fingerprints=["sse.com.cn", "Shanghai Stock Exchange"],
    )

    assert result.status == "reachable"


def test_classify_url_query_echo_without_page_identity_as_unverified() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://search.example.net/?next=https%3A%2F%2Fwww.sse.com.cn",
            title="Search results",
            body_excerpt="No matching publisher content was found.",
        ),
        expected_fingerprints=["sse.com.cn", "Shanghai Stock Exchange"],
    )

    assert result.status == "unverified"


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


def test_classify_waf_markers_before_generic_5xx_temporary_status() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            status_code=503,
            final_url="https://blocked.example.com",
            title="Security Check",
            body_excerpt=load_probe_fixture("waf.html"),
        ),
        expected_fingerprints=["blocked.example.com"],
    )

    assert result.status == "anti-bot"


def test_same_domain_shell_does_not_prove_a_function_route() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://www.sse.com.cn/",
            title="Shanghai Stock Exchange",
            body_excerpt="Shanghai Stock Exchange homepage",
        ),
        expected_fingerprints=["sse.com.cn", "Shanghai Stock Exchange"],
        function_fingerprints=["announcement ID", "issuer"],
    )

    assert result.status == "unverified"


def test_classify_36kr_chinese_security_check_as_anti_bot() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://36kr.com/",
            body_excerpt=load_probe_fixture("36kr-security-check.html"),
        ),
        expected_fingerprints=["36kr.com", "36Kr"],
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
        expected_fingerprints=["sse.com.cn"],
    )

    assert result.status == "moved"


def test_classify_redirect_to_meaningful_body_fingerprint_as_moved() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://publisher-cdn.example.net/new-search",
            redirect_chain=[
                "https://www.sse.com.cn/old/search -> https://publisher-cdn.example.net/new-search"
            ],
            title="Market disclosures",
            body_excerpt="Official Shanghai Stock Exchange announcements and disclosure search.",
        ),
        expected_fingerprints=["sse.com.cn", "Shanghai Stock Exchange"],
    )

    assert result.status == "moved"


def test_classify_redirect_old_url_echo_without_new_identity_as_unverified() -> None:
    module = load_probe_module()
    result = module.classify_observation(
        observation(
            module,
            final_url="https://search.example.net/new-search",
            redirect_chain=[
                "https://www.sse.com.cn/old/search -> https://search.example.net/new-search"
            ],
            title="Search results",
            body_excerpt="No matching publisher content was found.",
        ),
        expected_fingerprints=["sse.com.cn", "Shanghai Stock Exchange"],
    )

    assert result.status == "unverified"


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


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param(
            URLError(socket.gaierror(socket.EAI_NONAME, "resolver lookup failed")),
            id="nested-gaierror",
        ),
        pytest.param(
            OSError("nodename nor servname provided, or not known"),
            id="macos",
        ),
        pytest.param(OSError("Name or service not known"), id="linux"),
        pytest.param(
            OSError("Temporary failure in name resolution"),
            id="linux-temporary",
        ),
        pytest.param(OSError("getaddrinfo failed"), id="windows"),
    ],
)
def test_probe_url_maps_portable_dns_errors(
    reason: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_probe_module()

    class FailingOpener:
        def open(self, request, timeout: float):
            raise URLError(reason)

    monkeypatch.setattr(module, "build_opener", lambda redirect_handler: FailingOpener())

    observed = module.probe_url(
        "https://unresolvable.example",
        timeout=1.0,
        user_agent="task-3-test-agent/1.0",
    )

    assert observed.status_code is None
    assert observed.error_kind == "dns"
    assert observed.error_message


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


def test_load_cache_reads_legacy_source_observations(tmp_path: Path) -> None:
    module = load_probe_module()
    cache_path = tmp_path / "reachability.json"
    legacy_payload = {
        "sse": {
            "status": "reachable",
            "last_checked": "2026-08-01T10:00:00+00:00",
        }
    }
    cache_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    assert module.load_cache(cache_path) == legacy_payload


def test_cli_probes_selected_sources_and_updates_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_probe_module()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=False)
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
    assert cache["sse"]["review_state"] == "unreviewed"
    function_observation = cache["sse"]["functions"]["company-announcements"]
    assert function_observation["review_state"] == "unreviewed"
    assert function_observation["route_identity"]["function_id"] == "company-announcements"
    assert function_observation["route_identity"]["direct_url"] == f"{base_url}/reachable"


def test_cli_probes_function_direct_route_not_profile_shell_and_preserves_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_probe_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(module, "REPO_ROOT", repo_root, raising=False)
    shell_html = b"<html><title>Shanghai Stock Exchange</title><body>Homepage</body></html>"
    function_html = (
        b"<html><title>Shanghai Stock Exchange announcements</title>"
        b"<body>Issuer announcement ID and publication date</body></html>"
    )
    with serve_routes(
        {
            "/shell": (200, {"Content-Type": "text/html; charset=utf-8"}, shell_html),
            "/announcements": (
                200,
                {"Content-Type": "text/html; charset=utf-8"},
                function_html,
            ),
        }
    ) as base_url:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        selected = deepcopy(load_profile_fixture("official-example.yaml"))
        selected["access"]["final_url"] = f"{base_url}/shell"
        selected["functions"][0]["direct_urls"][0]["url"] = f"{base_url}/announcements"
        (profiles_dir / "official.yaml").write_text(
            yaml.safe_dump(selected, sort_keys=False),
            encoding="utf-8",
        )

        snapshot_path = (
            repo_root
            / ".claude"
            / "skills"
            / "source-discovery"
            / "references"
            / "reachability-snapshot.json"
        )
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text('{"sse": {"status": "reachable"}}\n', encoding="utf-8")
        snapshot_before = snapshot_path.read_text(encoding="utf-8")
        cache_path = repo_root / "tmp" / "source-discovery" / "reachability.json"

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
    assert cache["sse"]["final_url"] == f"{base_url}/announcements"
    function_observation = cache["sse"]["functions"]["company-announcements"]
    assert function_observation["status"] == "reachable"
    assert function_observation["route_identity"] == {
        "function_id": "company-announcements",
        "direct_url": f"{base_url}/announcements",
        "result_identity": "title, issuer, date, announcement ID",
    }
    assert snapshot_path.read_text(encoding="utf-8") == snapshot_before


def test_cli_rejects_combined_all_and_source_before_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_probe_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(module, "REPO_ROOT", repo_root, raising=False)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "official.yaml").write_text(
        yaml.safe_dump(load_profile_fixture("official-example.yaml"), sort_keys=False),
        encoding="utf-8",
    )
    probe_calls: list[str] = []

    def unexpected_probe(url: str, timeout: float, user_agent: str):
        probe_calls.append(url)
        raise AssertionError("network probe must not be called")

    monkeypatch.setattr(module, "probe_url", unexpected_probe)

    with pytest.raises(SystemExit) as exc_info:
        module.main(
            [
                "--profiles",
                str(profiles_dir),
                "--cache",
                str(repo_root / "tmp" / "source-discovery" / "reachability.json"),
                "--all",
                "--source",
                "sse",
            ]
        )

    assert exc_info.value.code == 2
    assert probe_calls == []


def test_cli_rejects_duplicate_profile_ids_before_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_probe_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(module, "REPO_ROOT", repo_root, raising=False)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profile = load_profile_fixture("official-example.yaml")
    (profiles_dir / "first.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False),
        encoding="utf-8",
    )
    (profiles_dir / "second.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False),
        encoding="utf-8",
    )
    probe_calls: list[str] = []

    def unexpected_probe(url: str, timeout: float, user_agent: str):
        probe_calls.append(url)
        raise AssertionError("network probe must not be called")

    monkeypatch.setattr(module, "probe_url", unexpected_probe)

    with pytest.raises(SystemExit) as exc_info:
        module.main(
            [
                "--profiles",
                str(profiles_dir),
                "--cache",
                str(repo_root / "tmp" / "source-discovery" / "reachability.json"),
                "--all",
            ]
        )

    assert exc_info.value.code == 2
    assert probe_calls == []


@pytest.mark.parametrize(
    "cache_path",
    [
        Path("outside") / "reachability.json",
        Path("repo") / "profiles" / "reviewed-reachability.json",
    ],
    ids=["outside-repository", "reviewed-repository-path"],
)
def test_cli_rejects_cache_outside_repository_tmp_source_discovery_before_write(
    cache_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_probe_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(module, "REPO_ROOT", repo_root, raising=False)
    target = tmp_path / cache_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"sentinel": true}\n', encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        module.main(
            [
                "--profiles",
                str(tmp_path / "missing-profiles"),
                "--cache",
                str(target),
                "--all",
            ]
        )

    assert exc_info.value.code == 2
    assert target.read_text(encoding="utf-8") == '{"sentinel": true}\n'


def test_cli_rejects_symlinked_tmp_source_discovery_outside_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_probe_module()
    repo_root = tmp_path / "repo"
    (repo_root / "tmp").mkdir(parents=True)
    outside_cache_root = tmp_path / "outside-cache"
    outside_cache_root.mkdir()
    (repo_root / "tmp" / "source-discovery").symlink_to(
        outside_cache_root,
        target_is_directory=True,
    )
    monkeypatch.setattr(module, "REPO_ROOT", repo_root)
    cache_path = repo_root / "tmp" / "source-discovery" / "reachability.json"

    with pytest.raises(SystemExit) as exc_info:
        module.main(
            [
                "--profiles",
                str(tmp_path / "missing-profiles"),
                "--cache",
                str(cache_path),
                "--all",
            ]
        )

    assert exc_info.value.code == 2
    assert not (outside_cache_root / "reachability.json").exists()


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
