"""Regression coverage for the Windows feedback, runnable on either platform."""

import json
import os
import plistlib
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox

from app import autostart
from app.agents.context import discover
from app.knowledge import ConflictError, DocumentError, create_note, list_documents
from app.models import Notebook
from app.storage import Store
from app.ui.knowledge import Knowledge
from app.ui.tasks import TaskLineEdit, Tasks, TaskTextEdit


def test_modified_sort_and_safe_rename(tmp_path):
    first = create_note(tmp_path, "Alpha", "first")
    second = create_note(tmp_path, "Zulu", "second", ".md")
    os.utime(first.path, (100, 100))
    os.utime(second.path, (200, 200))
    assert list_documents(tmp_path) == [first.path, second.path]
    assert list_documents(tmp_path, "modified") == [second.path, first.path]
    old = second.path
    second.rename("Renamed")
    assert not old.exists()
    assert second.path.name == "Renamed.md" and second.path.read_text() == "second"
    with pytest.raises(DocumentError):
        second.rename("../escape")
    with pytest.raises(DocumentError):
        first.rename("Alpha ")
    second.path.write_text("external")
    with pytest.raises(ConflictError):
        second.rename("Other")
    assert second.path.read_text() == "external"


def test_rename_collision_preserves_both(tmp_path):
    first = create_note(tmp_path, "First", "one")
    create_note(tmp_path, "Second", "two")
    with pytest.raises(DocumentError):
        first.rename("SECOND")
    assert first.path.read_text() == "one"
    assert (tmp_path / "Second.txt").read_text() == "two"


def test_knowledge_edit_title_content_sort_and_confirm_delete(qtbot, tmp_path, monkeypatch):
    path = create_note(tmp_path, "Note", "original", ".md").path
    settings = {"knowledge_folder": str(tmp_path)}
    widget = Knowledge(settings)
    qtbot.addWidget(widget)
    widget.files.setCurrentRow(0)
    qtbot.waitUntil(lambda: widget.document is not None)
    assert not widget.title.isReadOnly()
    widget.editor.setPlainText("# Changed")
    widget.title.setText("Edited")
    widget.rename_note()
    renamed = path.with_name("Edited.md")
    assert renamed.read_text() == "# Changed" and not path.exists()
    qtbot.waitUntil(lambda: widget.document is not None)
    widget.sort.setCurrentIndex(1)
    assert settings["knowledge_sort"] == "modified"
    qtbot.waitUntil(lambda: widget.document is not None)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Cancel)
    widget.delete_file()
    assert renamed.exists()
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Yes)
    widget.delete_file()
    assert not renamed.exists() and widget.current_path is None
    assert settings["knowledge_last_file"] == ""


@pytest.mark.parametrize("expanded", [False, True])
def test_multiline_clipboard_creates_siblings(qtbot, tmp_path, expanded):
    book = Notebook(Store(tmp_path).load())
    parent = book.add("Parent")
    target = book.add("", parent["id"])
    last = book.add("Last", parent["id"])
    tasks = Tasks(book, {})
    qtbot.addWidget(tasks)
    tasks.show()
    row = tasks.rows[target["id"]]
    if expanded:
        tasks.toggle_title(row)
    tasks.tree.setCurrentItem(row)
    tasks.tree.editItem(row, 0)
    editor = tasks.tree.findChild(TaskTextEdit if expanded else TaskLineEdit)
    assert editor is not None
    QApplication.clipboard().setText("One\r\nTwo\n\nThree")
    qtbot.keySequence(editor, QKeySequence.Paste)
    qtbot.waitUntil(lambda: len(book.children(parent["id"])) == 4)
    assert [i["text"] for i in book.children(parent["id"])] == ["One", "Two", "Three", "Last"]
    assert book.get(last["id"])["text"] == "Last"
    assert not any(tasks.rows[i["id"]].font(0).bold() for i in book.items)


def test_paste_existing_preserves_title_and_text_editor_regular_paste(qtbot, tmp_path):
    book = Notebook(Store(tmp_path).load())
    item = book.add("Existing")
    tasks = Tasks(book, {})
    qtbot.addWidget(tasks)
    tasks.paste_lines(item["id"], "A\nB")
    assert [i["text"] for i in book.children(None)] == ["Existing", "A", "B"]
    editor = TaskTextEdit()
    qtbot.addWidget(editor)
    source = QMimeData()
    source.setText("single line")
    editor.insertFromMimeData(source)
    assert editor.toPlainText() == "single line"


def test_opencode_shared_flat_configured_and_linked_skills(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    config = home / ".config/opencode"
    config.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    for source, name in [
        (home / ".agents/skills", "global"),
        (project / ".claude/skills", "shared"),
        (project / "extra", "configured"),
    ]:
        source.mkdir(parents=True)
        (source / (name + ".md")).write_text("skill instructions")
    nested = project / ".opencode/opencode.jsonc"
    nested.parent.mkdir()
    nested.write_text('{"skills":["./extra"],"mcp":{"servers":{"safe":{"enabled":false}}}}')
    hidden = config / "skills/.hidden/SKILL.md"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("not discoverable by V2")
    _, findings = discover("opencode", project, home)
    names = {f.name for f in findings if f.kind == "Skill"}
    assert names == {"global", "shared", "configured"}
    assert any(f.kind == "MCP" and f.name == "safe" and f.state == "Disabled" for f in findings)
    link = project / ".opencode/skills/linked"
    try:
        link.parent.mkdir(parents=True)
        link.symlink_to(project / "extra", target_is_directory=True)
    except OSError:
        return  # Windows symlinks can require Developer Mode.
    (project / "extra/SKILL.md").write_text("linked skill")
    _, findings = discover("opencode", project, home)
    assert any(f.kind == "Skill" and f.name == "linked" for f in findings)


def test_windows_uses_conpty_and_dimensions(monkeypatch):
    from app.terminal.windows import Process

    calls = []
    process = SimpleNamespace(pid=123)
    monkeypatch.setitem(
        sys.modules,
        "winpty",
        SimpleNamespace(PtyProcess=SimpleNamespace(spawn=lambda *a, **k: calls.append((a, k)) or process)),
    )
    monkeypatch.setitem(sys.modules, "winpty.enums", SimpleNamespace(Backend=SimpleNamespace(ConPTY=0)))
    Process(["opencode"], "C:/work", 132, 45)
    assert calls[0][1]["backend"] == 0
    assert calls[0][1]["dimensions"] == (45, 132)
    assert calls[0][1]["env"]["COLORTERM"] == "truecolor"


def test_macos_autostart_enable_disable(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    monkeypatch.setattr(autostart.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        autostart, "launch_command", lambda: ["/Applications/GetItDone.app/Contents/MacOS/GetItDone"]
    )
    assert not autostart.enabled()
    autostart.set_enabled(True)
    path = tmp_path / "Library/LaunchAgents/de.getitdone.notebook.plist"
    payload = plistlib.loads(path.read_bytes())
    assert payload["RunAtLoad"] is True
    assert payload["ProgramArguments"][0].startswith("/Applications/")
    assert autostart.enabled()
    autostart.set_enabled(False)
    assert not autostart.enabled()


def test_windows_toast_identity_delivery_blocked_and_click(monkeypatch):
    from app.notifications import windows

    registered, shown, clicked, failed = [], [], [], []
    setting = SimpleNamespace(setting="enabled")
    toaster = SimpleNamespace(toastNotifier=setting, show_toast=shown.append)
    monkeypatch.setattr(windows, "register", lambda: registered.append(True))
    monkeypatch.setitem(
        sys.modules,
        "windows_toasts",
        SimpleNamespace(
            InteractableWindowsToaster=lambda name, notifierAUMID: toaster, Toast=SimpleNamespace
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "winrt.windows.ui.notifications",
        SimpleNamespace(NotificationSetting=SimpleNamespace(ENABLED="enabled")),
    )
    notifications = windows.WindowsNotifications()
    assert registered == [True]
    item = {"id": "specific-task", "text": "Remember"}
    notifications.send(item, clicked.append, lambda *args: failed.append(args))
    assert shown[0].text_fields == ["GetItDone · Reminder", "Remember"]
    shown[0].on_activated(None)
    assert clicked == ["specific-task"]
    shown[0].on_failed(None)
    assert failed[0][0:2] == ("specific-task", False)
    setting.setting = "disabled"
    with pytest.raises(OSError, match="disabled"):
        notifications.send(item, clicked.append, lambda *args: None)
    assert len(shown) == 1


def test_windows_autostart_quotes_paths_and_preserves_other_entries(monkeypatch):
    values = {"Other app": "keep this"}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def query(key, name):
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 1

    def delete(key, name):
        if name not in values:
            raise FileNotFoundError(name)
        del values[name]

    monkeypatch.setitem(
        sys.modules,
        "winreg",
        SimpleNamespace(
            HKEY_CURRENT_USER=1,
            REG_SZ=1,
            CreateKey=lambda *args: Key(),
            OpenKey=lambda *args: Key(),
            QueryValueEx=query,
            SetValueEx=lambda key, name, reserved, kind, value: values.update({name: value}),
            DeleteValue=delete,
        ),
    )
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(autostart, "launch_command", lambda: [r"C:\Program Files\GetItDone\GetItDone.exe"])
    assert not autostart.enabled()
    autostart.set_enabled(True)
    assert autostart.enabled()
    assert values["GetItDone"] == r'"C:\Program Files\GetItDone\GetItDone.exe"'
    autostart.set_enabled(False)
    autostart.set_enabled(False)
    assert values == {"Other app": "keep this"}


def test_terminal_grid_fills_resized_area_and_scrolls(qtbot):
    from app.terminal.bridge import Terminal

    widget = Terminal()
    qtbot.addWidget(widget)
    widget.resize(600, 220)
    widget.show()
    qtbot.waitUntil(lambda: widget.ready_state, timeout=15000)
    qtbot.waitUntil(lambda: widget.dimensions[1] < 20)
    old_rows = widget.dimensions[1]
    widget.resize(1000, 640)
    qtbot.waitUntil(lambda: widget.dimensions[1] > old_rows * 2)
    values = []
    widget.page().runJavaScript(
        "JSON.stringify([document.querySelector('.xterm-screen').clientHeight, "
        "document.getElementById('terminal').clientHeight])",
        values.append,
    )
    qtbot.waitUntil(lambda: bool(values))
    height, available = json.loads(values[-1])
    assert available - 40 <= height <= available
    widget.page().runJavaScript("terminal.write('line\\r\\n'.repeat(150), () => terminal.scrollToTop())")
    qtbot.wait(100)
    values.clear()
    widget.page().runJavaScript(
        "JSON.stringify([terminal.buffer.active.baseY, terminal.buffer.active.viewportY])", values.append
    )
    qtbot.waitUntil(lambda: bool(values))
    base, view = json.loads(values[-1])
    assert base > 0 and view == 0
