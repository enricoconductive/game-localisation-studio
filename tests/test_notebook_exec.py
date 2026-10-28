"""Execute the student notebook top to bottom, and test the setup cell's bundle fallback.

The notebook runs in a clean temporary working directory with ``STUDIO_REPO_ROOT``
pointing at this repository (so the setup cell does not clone anything) and
``STUDIO_MODE=replay``. Skipped when nbclient/ipykernel are not installed.
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "notebooks" / "Game_Localisation_Studio.ipynb"
sys.path.insert(0, str(ROOT / "tools"))


def _load_nb():
    nbformat = pytest.importorskip("nbformat")
    return nbformat.read(str(NOTEBOOK), as_version=4)


def test_notebook_executes_without_errors(tmp_path, monkeypatch):
    nbformat = pytest.importorskip("nbformat")
    nbclient = pytest.importorskip("nbclient")
    pytest.importorskip("ipykernel")
    pytest.importorskip("ipywidgets")
    nb = _load_nb()
    monkeypatch.setenv("STUDIO_REPO_ROOT", str(ROOT))
    monkeypatch.setenv("STUDIO_MODE", "replay")
    monkeypatch.delenv("STUDIO_SETUP_DEFINE_ONLY", raising=False)
    monkeypatch.delenv("STUDIO_STATE_PATH", raising=False)
    monkeypatch.delenv("STUDIO_EXPORT_DIR", raising=False)
    client = nbclient.NotebookClient(nb, timeout=180, kernel_name="python3",
                                     resources={"metadata": {"path": str(tmp_path)}})
    try:
        client.execute()
    except nbclient.exceptions.CellExecutionError as e:  # pragma: no cover - shown on failure
        pytest.fail(f"A notebook cell failed:\n{e}")
    except Exception as e:  # noqa: BLE001 - e.g. no kernel available
        if "No such kernel" in str(e) or "kernel" in type(e).__name__.lower():
            pytest.skip(f"no Jupyter kernel available: {e}")
        raise
    errors = [o for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", [])
              if o.get("output_type") == "error"]
    assert not errors, errors
    code = [c for c in nb.cells if c.cell_type == "code"]
    # setup shows the welcome box; every section cell displays a widget
    for c in code:
        mimes = {k for o in c.get("outputs", []) for k in (o.get("data") or {})}
        assert "application/vnd.jupyter.widget-view+json" in mimes, c.source[:80]
    assert nbformat.validate(nb) is None
    # nothing was saved without a student action, and no repo files were written
    assert not (tmp_path / "studio_state.json").exists()


def test_notebook_structure_and_wording():
    nb = _load_nb()
    code = [c for c in nb.cells if c.cell_type == "code"]
    md = "\n".join(c.source for c in nb.cells if c.cell_type == "markdown")
    setup = code[0].source
    assert setup.startswith("#@title") and 'REPO_URL = "https://github.com/enricoconductive/game-localisation-studio"' in setup
    assert "git" in setup and "clone" in setup and "--depth" in setup
    assert "from src.studio_ui import Studio" in setup and "Studio.boot(" in setup
    for c in code[1:]:
        lines = [x for x in c.source.splitlines() if x.strip()]
        assert lines[0].startswith("#@title") and len(lines) == 2, c.source   # one-line code cells
    assert [c.source.splitlines()[-1] for c in code[1:]] == [
        "studio.section(1)", "studio.section(2)", "studio.section(3)", "studio.section(4)",
        "studio.section(5)", "studio.section(6)", "studio.stuck()"]
    assert md.count("Swap roles now") >= 3
    for phrase in ("AI Director", "Quality Evaluator", "≈3 min", "≈5 min", "≈15 min", "≈20 min",
                   "≈25 min", "≈10 min", "35–40 min", "skip Section 1",
                   "Replay Mode", "Colab Secrets", "Import student JSON",
                   "Play my translation in the game", "collaborators, not authorities"):
        assert phrase in md, phrase


def _setup_namespace(monkeypatch):
    monkeypatch.setenv("STUDIO_SETUP_DEFINE_ONLY", "1")
    ns: dict = {"__name__": "__notebook_setup__"}
    exec(compile(_load_nb().cells[1].source, "setup_cell", "exec"), ns)  # noqa: S102 - our own cell
    return ns


def _zip(entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data, *attr in entries:
            info = zipfile.ZipInfo(name)
            if attr:
                info.external_attr = attr[0]
            zf.writestr(info, data)
    return buf.getvalue()


def test_bundle_builds_and_installs_with_setup_cell(tmp_path, monkeypatch):
    import make_bundle
    out = make_bundle.build_bundle(tmp_path / "studio_bundle.zip")
    names = zipfile.ZipFile(out).namelist()
    assert "game-localisation-studio/src/studio_ui.py" in names
    assert "game-localisation-studio/notebooks/Game_Localisation_Studio.ipynb" in names
    assert "game-localisation-studio/config/providers.json" in names
    assert any(n.startswith("game-localisation-studio/game/") for n in names)
    assert not any("/tests/" in n or "node_modules" in n or "/.git/" in n or "/dist/" in n
                   or "__pycache__" in n or "studio_state" in n for n in names)
    ns = _setup_namespace(monkeypatch)
    root = ns["_install_bundle"](out.read_bytes(), tmp_path / "installed")
    assert (root / "src" / "studio_ui.py").is_file() and (root / "challenges" / "introductory.json").is_file()


@pytest.mark.parametrize("entries", [
    [("../evil.txt", b"x")],
    [("/abs/evil.txt", b"x")],
    [("game-localisation-studio/../../evil.txt", b"x")],
    [("C:/windows/evil.txt", b"x")],
    [("game-localisation-studio\\..\\evil.txt", b"x")],
    [("link", b"/etc/passwd", (0o120777 << 16))],
])
def test_setup_cell_rejects_unsafe_zip_entries(tmp_path, monkeypatch, entries):
    ns = _setup_namespace(monkeypatch)
    with pytest.raises(ValueError):
        ns["_safe_extract"](_zip(entries), tmp_path / "dest")
    assert not (tmp_path / "evil.txt").exists()


def test_setup_cell_rejects_non_zip_and_oversize(tmp_path, monkeypatch):
    ns = _setup_namespace(monkeypatch)
    with pytest.raises(ValueError):
        ns["_safe_extract"](b"not a zip", tmp_path / "d")
    ns["MAX_UNPACKED_BYTES"] = 10
    with pytest.raises(ValueError):
        ns["_safe_extract"](_zip([("a.txt", b"x" * 100)]), tmp_path / "d")
    with pytest.raises(ValueError):
        ns["_install_bundle"](_zip([("readme.txt", b"hi")]), tmp_path / "t")   # no src/studio_ui.py


def test_setup_rerun_updates_the_copy_or_keeps_it(tmp_path, monkeypatch, capsys):
    """Rerunning Step 0 in Colab fetches the latest code and resets to it; a failure is harmless."""
    ns = _setup_namespace(monkeypatch)
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        raise ns["subprocess"].TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(ns["subprocess"], "run", fake_run)
    ns["_update_copy"](tmp_path)
    (cmd, kw), = calls
    assert cmd[:4] == ["git", "-C", str(tmp_path), "fetch"] and "main" in cmd
    assert kw["timeout"] <= 30 and kw["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert "Using the copy already downloaded" in capsys.readouterr().out
    monkeypatch.setattr(ns["subprocess"], "run", lambda cmd, **kw: None)
    ns["_update_copy"](tmp_path)
    assert "Updated the studio" in capsys.readouterr().out


def test_setup_uses_repo_root_env(tmp_path, monkeypatch):
    """With STUDIO_REPO_ROOT the setup boots the studio from that folder (no clone)."""
    pytest.importorskip("ipywidgets")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STUDIO_REPO_ROOT", str(ROOT))
    monkeypatch.setenv("STUDIO_MODE", "replay")
    ns = _setup_namespace(monkeypatch)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: calls.append(a))
    ns["_setup"]()
    assert not calls
    studio = ns["studio"]
    assert type(studio).__name__ == "Studio" and studio.provider is not None
    assert studio.state_path == tmp_path / "studio_state.json"
    assert json.loads((ROOT / "config" / "providers.json").read_text())["replay"]
    assert os.environ["STUDIO_REPO_ROOT"] == str(ROOT)


def test_setup_cell_upload_error_is_escaped(tmp_path, monkeypatch):
    """An error while installing an uploaded bundle is shown as text, never as HTML."""
    widgets = pytest.importorskip("ipywidgets")
    ipy_display = pytest.importorskip("IPython.display")
    shown = []
    monkeypatch.setattr(ipy_display, "display", lambda *objs: shown.extend(objs))
    ns = _setup_namespace(monkeypatch)

    def broken_install(data, target):
        raise ValueError('<img src=x onerror="alert(1)"> bad zip')

    ns["_install_bundle"] = broken_install
    ns["_ask_for_bundle"](tmp_path / "target")
    box = shown[-1]
    status, upload = box.children
    upload.value = ({"name": "studio_bundle.zip", "type": "application/zip", "size": 3,
                     "content": memoryview(b"zip"),
                     "last_modified": datetime.now(timezone.utc)},)
    assert "<img" not in status.value
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; bad zip" in status.value
    assert isinstance(status, widgets.HTML)


def _colab_setup(tmp_path, monkeypatch):
    """The setup cell as in Colab: /content is ``tmp_path``, and the git clone fails."""
    monkeypatch.delenv("STUDIO_REPO_ROOT", raising=False)
    ns = _setup_namespace(monkeypatch)
    target = tmp_path / "game-localisation-studio"
    ns["COLAB_TARGET"] = str(target)
    ns["_in_colab"] = lambda: True

    def failing_clone(cmd, **kw):
        raise ns["subprocess"].CalledProcessError(128, cmd)

    monkeypatch.setattr(ns["subprocess"], "run", failing_clone)
    booted, asked = [], []
    ns["_boot"] = lambda root: booted.append(Path(root)) or "STUDIO"
    ns["_ask_for_bundle"] = lambda t: asked.append(Path(t))
    return ns, target, booted, asked


def test_setup_uses_bundle_dragged_into_the_files_panel(tmp_path, monkeypatch, capsys):
    ns, target, booted, asked = _colab_setup(tmp_path, monkeypatch)
    (tmp_path / "studio_bundle.zip").write_bytes(_zip([
        ("game-localisation-studio/src/studio_ui.py", b"# studio\n"),
        ("game-localisation-studio/README.md", b"hi")]))
    ns["_setup"]()
    out = capsys.readouterr().out
    first, fallback = "Downloading the studio…", ("Could not download from GitHub — using "
                                                  "studio_bundle.zip from the Files panel.")
    assert first in out and fallback in out and out.index(first) < out.index(fallback)
    assert (target / "src" / "studio_ui.py").read_bytes() == b"# studio\n"
    assert booted == [target] and not asked and ns["studio"] == "STUDIO"


def test_setup_asks_for_the_bundle_when_clone_fails_and_none_was_dropped(tmp_path, monkeypatch, capsys):
    ns, target, booted, asked = _colab_setup(tmp_path, monkeypatch)
    ns["_setup"]()
    out = capsys.readouterr().out
    assert "Downloading the studio…" in out and "using studio_bundle.zip" not in out
    assert asked == [target] and not booted
    # a damaged dropped bundle is reported, then the upload box is shown
    (tmp_path / "studio_bundle.zip").write_bytes(b"not a zip")
    ns["_setup"]()
    out = capsys.readouterr().out
    assert "using studio_bundle.zip from the Files panel" in out and "Could not use studio_bundle.zip" in out
    assert asked == [target, target] and not booted
