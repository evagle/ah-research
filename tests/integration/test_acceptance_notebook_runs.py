"""Integration test: phase2_acceptance.ipynb runs end-to-end without errors.

Marked @pytest.mark.slow because it executes the full notebook (~30-90 s).
Run explicitly with: pytest tests/integration/test_acceptance_notebook_runs.py -m slow -v
"""

from __future__ import annotations

import pathlib

import nbformat
import pytest
from nbclient import NotebookClient

NOTEBOOK_PATH = (
    pathlib.Path(__file__).parent.parent.parent / "notebooks" / "phase2_acceptance.ipynb"
)


@pytest.mark.slow
def test_acceptance_notebook_runs() -> None:
    """Execute the acceptance notebook top-to-bottom; assert no cell raises."""
    nb = nbformat.read(str(NOTEBOOK_PATH), as_version=4)
    client = NotebookClient(
        nb,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK_PATH.parent.parent)}},
    )
    client.execute()

    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for output in cell.get("outputs", []):
            assert output.get("output_type") != "error", (
                f"Cell raised an error:\n"
                f"Source: {cell.source[:200]}\n"
                f"Error: {output.get('ename')}: {output.get('evalue')}"
            )
