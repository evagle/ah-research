from pathlib import Path

from ah_research.scripts.ah_doctor import (
    CheckResult,
    check_cache_dir_writable,
    check_python_version,
)


def test_check_python_version_passes_on_311_plus():
    result = check_python_version()
    assert result.ok is True
    assert "3.1" in result.detail or "3.2" in result.detail


def test_check_cache_dir_writable_passes_when_writable(tmp_path):
    result = check_cache_dir_writable(tmp_path)
    assert result.ok is True


def test_check_cache_dir_writable_fails_for_nonexistent():
    result = check_cache_dir_writable(Path("/nonexistent/ah-cache"))
    assert result.ok is False
    assert "not exist" in result.detail.lower() or "cannot write" in result.detail.lower()


def test_check_result_is_dataclass_like():
    r = CheckResult(name="foo", ok=True, detail="ok")
    assert r.name == "foo"
    assert r.ok is True
    assert r.detail == "ok"
