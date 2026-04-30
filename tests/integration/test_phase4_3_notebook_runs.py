from __future__ import annotations

import pathlib

import nbformat
import pytest
from nbclient import NotebookClient

NOTEBOOKS_DIR = pathlib.Path(__file__).resolve().parents[2] / "notebooks"


def _run_notebook(nb_path: pathlib.Path) -> None:
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
            assert output.get("output_type") != "error", f"Cell errored: {output}"


@pytest.mark.slow
def test_phase4_3_dossier_notebook() -> None:
    _run_notebook(NOTEBOOKS_DIR / "phase4_3_dossier_qualitative_example.ipynb")
