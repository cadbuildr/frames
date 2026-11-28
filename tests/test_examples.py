"""The examples run (``show`` is stubbed) and build DAGs."""

import runpy
from pathlib import Path

import pytest
from cadbuildr.foundation.dag_utils import show_dag

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.py"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_runs(path, monkeypatch, capsys):
    import cadbuildr.foundation as foundation

    shown = []
    monkeypatch.setattr(foundation, "show", lambda x, *a, **k: shown.append(x))
    runpy.run_path(str(path), run_name="__main__")
    assert len(shown) == 1
    show_dag(shown[0])
    assert "Item" in capsys.readouterr().out  # a cut list was printed
