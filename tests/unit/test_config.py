from pathlib import Path

from ah_research.config import Settings, get_settings


def test_default_cache_dir_is_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("AH_RESEARCH_CACHE_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    s = Settings()
    assert s.cache_dir == tmp_path / ".ah-research"


def test_cache_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path / "custom"))
    s = Settings()
    assert s.cache_dir == tmp_path / "custom"


def test_cache_duckdb_path_derived_from_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path))
    s = Settings()
    assert s.cache_duckdb_path == tmp_path / "cache.duckdb"


def test_anthropic_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    s = Settings()
    assert s.anthropic_api_key == "sk-test-123"


def test_get_settings_is_singleton_per_process(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path))
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
