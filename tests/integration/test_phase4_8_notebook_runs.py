from __future__ import annotations

from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

NOTEBOOK = Path(__file__).parents[2] / "notebooks" / "phase4_8_constructor_optimize_example.ipynb"


def test_phase4_8_notebook_runs_headless() -> None:
    if not NOTEBOOK.exists():
        pytest.skip("notebook not present")
    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(nb, timeout=300)
    try:
        client.execute()
    except CellExecutionError as e:
        pytest.fail(f"notebook execution failed: {e}")
