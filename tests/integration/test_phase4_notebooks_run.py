"""Phase 4.1 acceptance notebook — executes headless in CI via nbclient."""

from __future__ import annotations

import pathlib

import nbformat
import pytest
from nbclient import NotebookClient

NOTEBOOKS_DIR = pathlib.Path(__file__).parent.parent.parent / "notebooks"


def _run_notebook(nb_path: pathlib.Path) -> None:
    """Execute *nb_path* in-place; assert no cell raises an error."""
    nb = nbformat.read(str(nb_path), as_version=4)
    client = NotebookClient(
        nb,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(nb_path.parent.parent)}},
    )
    client.execute()

    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for output in cell.get("outputs", []):
            assert output.get("output_type") != "error", (
                f"Cell raised an error in {nb_path.name}:\n"
                f"Source: {cell.source[:200]}\n"
                f"Error: {output.get('ename')}: {output.get('evalue')}"
            )


@pytest.mark.slow
def test_phase4_1_optimizer_example_notebook():
    _run_notebook(NOTEBOOKS_DIR / "phase4_1_optimizer_example.ipynb")
