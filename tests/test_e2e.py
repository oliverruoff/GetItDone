"""UI workflows; real OpenCode smoke test is explicitly opt-in (uses a model)."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLineEdit,
    QPushButton,
)

from app.agents.base import executable_path
from app.main import configure_style
from app.models import Notebook, uid
from app.session_paths import builtin_session_folder
from app.storage import Store
from app.ui.dialogs import SessionDialog, SettingsDialog
from app.ui.window import Window


@pytest.fixture
def workflow(qtbot, tmp_path):
    QApplication.instance().setQuitOnLastWindowClosed(False)
    configure_style(QApplication.instance())
    store = Store(tmp_path)
    book = Notebook(store.load())
    category = {"id": uid(), "name": "Project work", "color": "#3d9e50"}
    book.data["categories"].append(category)
    book.data["settings"]["default_workdir"] = str(tmp_path)
    window = Window(store, book.data)
    window.show()
    window.raise_()
    window.activateWindow()
    qtbot.waitExposed(window)
    QApplication.processEvents()
    yield window, category
    window.timer.stop()
    window.saver.stop()
    for terminal in list(window.terminals.values()):
        terminal.stop()
        qtbot.waitUntil(lambda t=terminal: not t.running, timeout=8000)
        qtbot.waitUntil(lambda t=terminal: not t.reader.is_alive(), timeout=8000)
        QApplication.processEvents()
        terminal.close()
    window.tray.hide()
    window.quitting = True
    window.close()
    window.deleteLater()
    QApplication.processEvents()


def create_and_categorize(qtbot, window, category):
    tasks = window.tasks
    qtbot.mouseClick(tasks.add_button, Qt.LeftButton)
    editor = tasks.tree.findChild(QLineEdit)
    editor.selectAll()
    qtbot.keyClicks(editor, "E2E Category und Agent")
    qtbot.keyClick(editor, Qt.Key_Tab)
    qtbot.waitUntil(lambda: window.notebook.items[0]["text"] == "E2E Category und Agent")
    assert len(window.notebook.items) == 1
    item = window.notebook.items[0]
    assert item["text"] == "E2E Category und Agent"

    qtbot.mouseClick(tasks.tree.itemWidget(tasks.rows[item["id"]], 1), Qt.LeftButton)
    palette = window.color_palette
    qtbot.mouseClick(
        next(b for b in palette.swatches if b.property("color") == category["color"]), Qt.LeftButton
    )
    assert item["category_id"] == category["id"]
    tasks.tree.clearSelection()
    tasks.tree.setCurrentItem(None)
    QApplication.processEvents()
    row = tasks.rows[item["id"]]
    rect = tasks.tree.visualItemRect(row)
    # Rendered title cell: proves actual coloring, rather than only checking model data.
    image = tasks.tree.viewport().grab().toImage()
    pixel = image.pixelColor(tasks.tree.columnWidth(0) - 12, rect.top() + 7)
    expected = QColor(category["color"])
    assert pixel == expected, (pixel.name(), expected.name())
    assert window.flush()
    assert Store(window.store.folder).load()["items"][0]["category_id"] == category["id"]
    return item


def test_create_categorize_render_save_and_complete(qtbot, workflow):
    window, category = workflow
    item = create_and_categorize(qtbot, window, category)
    row = window.tasks.rows[item["id"]]
    rect = window.tasks.tree.visualItemRect(row)
    # Actual checkbox click, followed by the completed filter.
    qtbot.mouseClick(
        window.tasks.tree.viewport(),
        Qt.LeftButton,
        pos=rect.topLeft() + QPoint(15, rect.height() // 2),
    )
    qtbot.waitUntil(lambda: item["done"])
    assert item["id"] not in window.tasks.rows
    window.tasks.status.setCurrentIndex(window.tasks.status.findData("done"))
    assert item["id"] in window.tasks.rows
    assert window.flush()
    assert Store(window.store.folder).load()["items"][0]["done"]


def test_default_workspace_is_prefilled_created_and_used_when_cleared(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    dialog = SessionDialog({})
    qtbot.addWidget(dialog)
    assert dialog.workdir.text() == str(builtin_session_folder())
    # Only executable resolution is replaced; the directory workflow is real.
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: "/bin/echo")
    dialog.workdir.clear()
    dialog.check()
    assert dialog.directory == str(builtin_session_folder())
    assert Path(dialog.directory).is_dir()
    settings = SettingsDialog({"settings": {}, "categories": []}, tmp_path / "data.json", "", None)
    qtbot.addWidget(settings)
    assert settings.workdir.text() == dialog.directory
    settings.workdir.clear()
    settings.check()
    assert settings.settings["default_workdir"] == dialog.directory


@pytest.mark.skipif(
    os.environ.get("GETITDONE_LIVE_OPENCODE") != "1", reason="Opt-in real OpenCode model call"
)
def test_live_opencode_prompt_busy_response_and_acknowledge(qtbot, workflow):
    window, category = workflow
    item = create_and_categorize(qtbot, window, category)
    artifacts = Path("build/e2e")
    artifacts.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(artifacts / "01-category.png"))
    handled = []
    dialog_errors = []

    def start_dialog():
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, SessionDialog):
            QTimer.singleShot(50, start_dialog)
            return
        if dialog.info.text() == "Checking installation …":
            QTimer.singleShot(50, start_dialog)
            return
        if not dialog.supports_status:
            dialog_errors.append(dialog.info.text())
            dialog.reject()
            return
        handled.append(dialog.workdir.text())
        dialog.workdir.clear()  # Must use the configured default, not the repo/current directory.
        qtbot.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)

    QTimer.singleShot(50, start_dialog)
    actions = window.tasks.tree.itemWidget(window.tasks.rows[item["id"]], 4)
    button = next(b for b in actions.findChildren(QPushButton) if b.accessibleName() == "New session")
    qtbot.mouseClick(button, Qt.LeftButton)
    assert not dialog_errors, dialog_errors
    assert handled == [window.notebook.data["settings"]["default_workdir"]]
    session = window.notebook.data["sessions"][0]
    assert session["workdir"] == handled[0]
    assert session["native_session_id"].startswith("ses_")
    terminal = window.terminals[session["id"]]
    qtbot.waitUntil(lambda: terminal.ready_state, timeout=15000)
    output = []
    terminal.output_ready.connect(output.append)
    qtbot.waitUntil(lambda: bool(output), timeout=20000)
    window.grab().save(str(artifacts / "02-ready.png"))

    prompt = (
        "Dies ist ein UI-End-to-End-Test. Erklaere in zwanzig kurzen nummerierten Saetzen, "
        "wie man gute Softwaretests schreibt. Keine Tools verwenden, keine Fileen aendern. "
        "Beende die Antwort exakt mit GETITDONE_E2E_OK."
    )
    # Same bridge used by xterm keyboard input.
    terminal.bridge.input(prompt)
    terminal.bridge.input("\r")
    try:
        qtbot.waitUntil(lambda: terminal.agent_state == "Agent running", timeout=30000)
    except Exception:
        window.grab().save(str(artifacts / "failure.png"))
        (artifacts / "failure-output.txt").write_text("".join(output))
        raise
    assert "Agent running" in window.tasks.rows[item["id"]].text(3)
    assert "Agent running" in window.tasks.session_rows[session["id"]].text(0)
    window.grab().save(str(artifacts / "03-agent-running.png"))
    qtbot.waitUntil(lambda: terminal.agent_state == "Ready" and terminal.agent_message, timeout=90000)
    assert terminal.running, "TUI must remain open even though the agent has finished"
    assert "New agent message" in window.tasks.rows[item["id"]].text(3)
    assert "New agent message" in window.tasks.session_rows[session["id"]].text(0)
    assert "GETITDONE_E2E_OK" in "".join(output)
    # Inspect the actual assistant response, not the prompt's echoed marker.
    result = subprocess.run(
        [
            executable_path("opencode"),
            "api",
            "session.message.list",
            "--param",
            "sessionID=" + session["native_session_id"],
            "--param",
            "limit=20",
            "--param",
            "order=desc",
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    messages = json.loads(result.stdout)["data"]
    assert any(
        message.get("type") == "assistant"
        and any("GETITDONE_E2E_OK" in part.get("text", "") for part in message.get("content", []))
        for message in messages
    )
    window.grab().save(str(artifacts / "04-new-message.png"))
    # A later idle poll must not clear or repeat the notification.
    window.poll_agent_status()
    qtbot.waitUntil(lambda: not window.status_polling)
    assert terminal.agent_message
    actions = window.tasks.tree.itemWidget(window.tasks.session_rows[session["id"]], 4)
    qtbot.mouseClick(
        next(b for b in actions.findChildren(QPushButton) if b.text() == "Resume"), Qt.LeftButton
    )
    assert not terminal.agent_message
    assert "New agent message" not in window.tasks.rows[item["id"]].text(3)
    window.poll_agent_status()
    qtbot.waitUntil(lambda: not window.status_polling)
    assert not terminal.agent_message
    assert window.flush()
    saved = Store(window.store.folder).load()
    assert saved["sessions"][0]["native_session_id"] == session["native_session_id"]
    assert "GETITDONE_E2E_OK" not in window.store.path.read_text()


def test_completion_animates_and_undo_restores_original_item(qtbot, workflow):
    window, category = workflow
    item = create_and_categorize(qtbot, window, category)
    window.notebook.update(item["id"], notes="Note bleibt erhalten")
    window.tasks.rebuild()
    row = window.tasks.rows[item["id"]]
    rect = window.tasks.tree.visualItemRect(row)
    qtbot.mouseClick(
        window.tasks.tree.viewport(),
        Qt.LeftButton,
        pos=rect.topLeft() + QPoint(15, rect.height() // 2),
    )
    qtbot.waitUntil(lambda: item["done"])
    assert item["id"] not in window.tasks.rows
    assert window.tasks.completion_overlay is not None
    overlay = window.tasks.completion_overlay
    qtbot.waitUntil(lambda: overlay.progress > 0)
    assert window.tasks.undo_notices[item["id"]].isVisible()
    qtbot.waitUntil(lambda: window.tasks.completion_overlay is None)
    notice = window.tasks.undo_notices[item["id"]]
    qtbot.mouseClick(notice.findChild(QPushButton), Qt.LeftButton)
    qtbot.waitUntil(lambda: not item["done"])
    assert item["id"] in window.tasks.rows
    assert not window.tasks.undo_notices
    assert item["category_id"] == category["id"]
    assert item["notes"] == "Note bleibt erhalten"
    assert window.flush()
    assert not Store(window.store.folder).load()["items"][0]["done"]


def test_multiple_completions_have_independent_undo_and_expire(qtbot, workflow):
    window, _ = workflow
    first = window.notebook.add("Erster")
    second = window.notebook.add("Zweiter")
    window.tasks.rebuild()
    window.complete(first["id"], True)
    window.complete(second["id"], True)
    assert set(window.tasks.undo_notices) == {first["id"], second["id"]}
    qtbot.mouseClick(window.tasks.undo_notices[first["id"]].findChild(QPushButton), Qt.LeftButton)
    qtbot.waitUntil(lambda: not first["done"])
    assert second["done"]
    assert set(window.tasks.undo_notices) == {second["id"]}
    qtbot.waitUntil(lambda: not window.tasks.undo_notices, timeout=6000)
    assert second["done"]
    assert not window.tasks.undo_area.isVisible()


def test_parent_completion_cascades_and_undo_restores_mixed_states(qtbot, workflow, monkeypatch):
    window, _ = workflow
    parent = window.notebook.add("Elternpunkt")
    child = window.notebook.add("Open child", parent=parent["id"])
    done_child = window.notebook.add("Previously done", parent=parent["id"])
    window.notebook.complete(done_child["id"], True)
    window.tasks.rebuild()
    errors = []
    monkeypatch.setattr("app.ui.window.error", lambda owner, message: errors.append(str(message)))
    window.complete(parent["id"], True)
    assert all(item["done"] for item in (parent, child, done_child))
    assert not errors
    assert parent["id"] in window.tasks.undo_notices
    qtbot.mouseClick(window.tasks.undo_notices[parent["id"]].findChild(QPushButton), Qt.LeftButton)
    assert not parent["done"] and not child["done"] and done_child["done"]
    saved = Store(window.store.folder).load()
    states = {item["id"]: item["done"] for item in saved["items"]}
    assert states[parent["id"]] is False and states[child["id"]] is False and states[done_child["id"]] is True
