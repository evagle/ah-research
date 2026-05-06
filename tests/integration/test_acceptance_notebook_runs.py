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
    """Execute the acceptance notebook top-to-bottom.

    Two-level assertion:
      1. No code cell raised (no ``output_type == "error"``).
      2. At least one cell actually produced non-empty output. Without (2)
         a silently-short-circuited notebook (e.g. ``if False: ...``) would
         pass the error check.
    """
    nb = nbformat.read(str(NOTEBOOK_PATH), as_version=4)
    client = NotebookClient(
        nb,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK_PATH.parent.parent)}},
    )
    client.execute()

    cells_with_output = 0
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for output in cell.get("outputs", []):
            assert output.get("output_type") != "error", (
                f"Cell raised an error:\n"
                f"Source: {cell.source[:200]}\n"
                f"Error: {output.get('ename')}: {output.get('evalue')}"
            )
            # Count cells that produced any real output (stream, display, or
            # execute_result). `error` already rejected above.
            if output.get("output_type") in {"stream", "display_data", "execute_result"}:
                cells_with_output += 1
                break

    assert cells_with_output >= 1, (
        "No code cell produced output. A silently-short-circuited notebook "
        "would pass the no-error check; require at least one real output."
    )
