from ah_research.config import get_settings
from ah_research.scripts.ah_init import create_cache_dir, run, write_default_profile


def test_create_cache_dir_idempotent(tmp_path):
    target = tmp_path / ".ah-research"
    create_cache_dir(target)
    assert target.exists()
    create_cache_dir(target)
    assert target.exists()
    assert (target / "sessions").exists()
    assert (target / "logs").exists()


def test_write_default_profile_creates_yaml(tmp_path):
    path = tmp_path / "profile.yaml"
    write_default_profile(path)
    assert path.exists()
    content = path.read_text()
    assert "investor_style: value" in content
    assert "horizon: long_term" in content
    assert "default_rebalance: M" in content


def test_write_default_profile_does_not_overwrite(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("# user custom content\n")
    write_default_profile(path)
    assert path.read_text() == "# user custom content\n"


def test_run_creates_full_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path / "custom"))
    get_settings.cache_clear()

    run(interactive=False)

    root = tmp_path / "custom"
    assert root.exists()
    assert (root / "profile.yaml").exists()
    assert (root / "sessions").exists()
    assert (root / "logs").exists()
