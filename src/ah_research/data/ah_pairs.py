"""Loader for the curated AH pairs YAML.

The YAML is packaged alongside the module (``importlib.resources``) so this
works whether the library is installed or run from a source checkout.
"""

from __future__ import annotations

from importlib.resources import files

import yaml

from ah_research.model.types import AHPair, parse_symbol


def load_ah_pairs() -> list[AHPair]:
    """Return all entries with both A and H legs. A-only rows are dropped."""
    yaml_path = files("ah_research.data").joinpath("ah_pairs.yaml")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    pairs: list[AHPair] = []
    for entry in data["pairs"]:
        if entry.get("h") is None:
            continue
        pairs.append(
            AHPair(
                a_symbol=parse_symbol(entry["a"]),
                h_symbol=parse_symbol(entry["h"]),
                name_en=entry["name_en"],
                name_zh=entry["name_zh"],
            )
        )
    return pairs
