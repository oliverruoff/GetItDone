import json
import zipfile

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget

from app.backups import backup_defaults, create_backup
from app.canvas import prepare_canvas
from app.models import Notebook
from app.ui.canvas import Canvas


def test_canvas_initialization_preserves_user_files(tmp_path):
    folder = prepare_canvas(tmp_path)
    assert (folder / "canvas.html").is_file()
    guide = (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert "OUTSIDE" in guide and "ENTIRE" in guide
    (folder / "canvas.html").write_text("My dashboard", encoding="utf-8")
    (folder / "AGENTS.md").write_text("My instructions", encoding="utf-8")
    prepare_canvas(tmp_path)
    assert (folder / "canvas.html").read_text() == "My dashboard"
    assert (folder / "AGENTS.md").read_text() == "My instructions"


def test_canvas_backup_includes_all_files_and_restore_instructions(tmp_path):
    data = tmp_path / "data"
    folder = prepare_canvas(data)
    (folder / "assets").mkdir()
    (folder / "assets" / "picture.bin").write_bytes(b"\x00\xff")
    (folder / "empty").mkdir()
    (data / "outside.txt").write_text("not included")
    book = Notebook()
    book.data["settings"]["backups"] = backup_defaults() | {"folder": str(tmp_path / "backups")}
    with zipfile.ZipFile(create_backup(book.data, data)) as archive:
        assert archive.read("canvas/assets/picture.bin") == b"\x00\xff"
        assert "canvas/AGENTS.md" in archive.namelist()
        assert "canvas/empty/" in archive.namelist()
        assert "outside.txt" not in archive.namelist()
        assert "Restore canvas/" in archive.read("RESTORE.txt").decode()
        assert json.loads(archive.read("manifest.json"))["canvas_folder"] == str(folder.resolve())


def test_canvas_reloads_atomic_html_and_nested_asset_changes(qtbot, tmp_path, monkeypatch):
    canvas = Canvas(tmp_path, {})
    qtbot.addWidget(canvas)
    calls = []
    monkeypatch.setattr(canvas, "reload", lambda: calls.append(True))
    replacement = canvas.folder / "replacement.html"
    replacement.write_text("<h1>Changed</h1>")
    replacement.replace(canvas.folder / "canvas.html")
    canvas.check_changes()
    assert len(calls) == 1
    assets = canvas.folder / "assets"
    assets.mkdir()
    (assets / "style.css").write_text("body {color:red}")
    canvas.check_changes()
    assert len(calls) == 2
    canvas.check_changes()
    assert len(calls) == 2


def test_canvas_displays_local_html(qtbot, tmp_path):
    folder = prepare_canvas(tmp_path)
    (folder / "canvas.html").write_text("<html><title>My dashboard</title><h1>Hello</h1></html>")
    canvas = Canvas(tmp_path, {})
    qtbot.addWidget(canvas)
    canvas.show()
    qtbot.waitUntil(lambda: canvas.view.title() == "My dashboard", timeout=10000)
    assert canvas.view.url() == QUrl.fromLocalFile(str((folder / "canvas.html").resolve()))


def test_canvas_agent_uses_fixed_folder(qtbot, tmp_path, monkeypatch):
    from app.ui import canvas as module

    calls = []

    class Dialog:
        def __init__(self, settings, parent, *, fixed_directory):
            calls.append(fixed_directory)
            self.command = ["fake-agent"]
            self.agent = self

        def setWindowTitle(self, title):
            pass

        def exec(self):
            return True

        def currentText(self):
            return "Test agent"

    class FakeTerminal(QWidget):
        running = False

        def start(self, command, directory):
            calls.append((command, directory))

    monkeypatch.setattr(module, "SessionDialog", Dialog)
    monkeypatch.setattr(module, "Terminal", FakeTerminal)
    canvas = Canvas(tmp_path, {})
    qtbot.addWidget(canvas)
    canvas.open_agent()
    assert calls == [canvas.folder.resolve(), (["fake-agent"], str(canvas.folder.resolve()))]
    assert canvas.tabs.count() == 1 and len(canvas.terminals) == 1
    canvas.close_terminal(0)
    assert canvas.tabs.count() == 0 and not canvas.terminals
