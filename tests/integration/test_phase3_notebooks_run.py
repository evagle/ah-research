"""Integration tests: Phase 3 reference notebooks run end-to-end without errors.

Each test is marked @pytest.mark.slow because it executes a full notebook
(can take 20-60 s each). Run explicitly with:

    pytest tests/integration/test_phase3_notebooks_run.py -m slow -v
"""

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
def test_phase3_factor_study_value_notebook_runs() -> None:
    """Execute phase3_factor_study_value.ipynb top-to-bottom; assert no cell errors."""
    _run_notebook(NOTEBOOKS_DIR / "phase3_factor_study_value.ipynb")


@pytest.mark.slow
def test_phase3_screener_workflow_notebook_runs() -> None:
    """Execute phase3_screener_workflow.ipynb top-to-bottom; assert no cell errors."""
    _run_notebook(NOTEBOOKS_DIR / "phase3_screener_workflow.ipynb")


@pytest.mark.slow
def test_phase3_dossier_example_notebook_runs() -> None:
    """Execute phase3_dossier_example.ipynb top-to-bottom; assert no cell errors."""
    _run_notebook(NOTEBOOKS_DIR / "phase3_dossier_example.ipynb")


@pytest.mark.slow
def test_phase3_portfolio_construction_notebook_runs() -> None:
    """Execute phase3_portfolio_construction.ipynb top-to-bottom; assert no cell errors."""
    _run_notebook(NOTEBOOKS_DIR / "phase3_portfolio_construction.ipynb")
