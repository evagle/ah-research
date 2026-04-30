"""Headless execution test for the Phase 5 acceptance notebook."""

from __future__ import annotations

from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

NOTEBOOK = Path(__file__).parents[2] / "notebooks" / "phase5_chat_example.ipynb"


def test_phase5_notebook_runs_headless() -> None:
    if not NOTEBOOK.exists():
        pytest.skip("notebook not present")
    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(nb, timeout=120)
    try:
        client.execute()
    except CellExecutionError as e:
        pytest.fail(f"notebook execution failed: {e}")
