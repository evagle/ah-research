"""``ah init`` — bootstrap cache dir, profile.yaml, confirm API key presence."""

from __future__ import annotations

from pathlib import Path

import typer

from ah_research.config import get_settings
from ah_research.logging import configure_logging, get_logger

log = get_logger(__name__)

DEFAULT_PROFILE = """\
# ah-research user profile — edit to taste
# Loaded into the AI system prompt so the chat knows your style.

investor_style: value           # value | growth | generic
horizon: long_term              # long_term (>60d) | medium (20-60d)
default_universe: CSI300        # or HSI / CSI500 / "CSI300+HSI"
default_rebalance: M            # D | W | M | Q
default_metrics:
  - cagr
  - sharpe
  - max_drawdown
  - dividend_yield_avg
preferred_visualizations:
  - valuation_bands
  - dossier
cn_color_convention: cn         # "cn" (red=up) | "west" (green=up)
api_budget_usd_per_session: 5.0
"""


def create_cache_dir(root: Path) -> None:
    """Create ~/.ah-research and required subdirs. Idempotent."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "sessions").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)


def write_default_profile(path: Path) -> None:
    """Write DEFAULT_PROFILE to path if the file does not already exist."""
    if path.exists():
        log.info("profile_exists_skipping", path=str(path))
        return
    path.write_text(DEFAULT_PROFILE)
    log.info("profile_written", path=str(path))


def run(interactive: bool = True) -> None:
    """Main entrypoint called from ``ah init``."""
    configure_logging()
    settings = get_settings()
    root = settings.cache_dir
    typer.echo(f"Setting up ah-research at {root}")
    create_cache_dir(root)
    write_default_profile(root / "profile.yaml")

    if interactive and settings.anthropic_api_key is None:
        typer.echo(
            "\n⚠  ANTHROPIC_API_KEY not set in environment.\n"
            "   The chat UI and ah.ask() will be unavailable until you set it.\n"
            "   Add to your shell rc: export ANTHROPIC_API_KEY=sk-...\n"
        )

    typer.echo("\n✓ Done. Next: `ah doctor` to verify everything works.\n")
