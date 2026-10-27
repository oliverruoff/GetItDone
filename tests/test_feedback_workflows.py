from datetime import datetime

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from app.models import Notebook
from app.storage import Store
from app.ui.knowledge import NewNote
from app.ui.scheduled import ScheduleDialog
from app.ui.tasks import ROLE
from app.ui.window import Window


@pytest.fixture
def window(qtbot, tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    parent = book.add("Parent")
    child = book.add("Child", parent=parent["id"])
    book.add("Grandchild", parent=child["id"])
    book.data["settings"]["knowledge_folder"] = str(tmp_path)
    widget = Window(store, book.data)
    qtbot.addWidget(widget)
    widget.timer.stop()
    widget.show()
    widget.activateWindow()
    QApplication.processEvents()
    yield widget
    widget.timer.stop()
    widget.scheduler.shutdown()
    widget.saver.stop()
    widget.tray.hide()
    widget.quitting = True
    widget.close()


def test_expansion_saved_instantly_and_restored(window, qtbot):
    tasks = window.tasks
    ids = [i["id"] for i in window.notebook.items]
    tasks.rows[ids[1]].setExpanded(False)
    tasks.rows[ids[0]].setExpanded(False)
    state = Store(window.store.folder).load()["settings"]["task_view"]
    assert state["expanded"][ids[0]] is False and state["expanded"][ids[1]] is False
    tasks.rebuild()
    assert not tasks.rows[ids[0]].isExpanded()
    from app.ui.tasks import Tasks
    reopened = Tasks(Notebook(Store(window.store.folder).load()), {})
    qtbot.addWidget(reopened)
    assert not reopened.rows[ids[0]].isExpanded()
    reopened.rows[ids[0]].setExpanded(True)
    assert not reopened.rows[ids[1]].isExpanded()
    tasks.toggle_title(tasks.rows[ids[0]])
    assert ids[0] in Store(window.store.folder).load()["settings"]["task_view"]["titles"]


def test_icon_controls_and_plus_visibility(window, qtbot):
    tasks = window.tasks
    controls = {b.accessibleName(): b for b in tasks.findChildren(QPushButton)}
    assert controls["Expand all"].text() == controls["Collapse all"].text() == ""
    qtbot.mouseClick(controls["Collapse all"], Qt.LeftButton)
    assert all(not row.isExpanded() for row in tasks.rows.values())
    assert len([r for r in tasks.rows.values() if not tasks.tree.visualItemRect(r).isEmpty()]) == 1
    qtbot.mouseClick(controls["Expand all"], Qt.LeftButton)
    assert all(row.isExpanded() for row in tasks.rows.values())
    parent = window.notebook.items[0]["id"]
    row = tasks.rows[parent]
    add_row = row.child(row.childCount() - 1)
    assert add_row.data(0, ROLE + 1) == "add"
    plus = tasks.tree.itemWidget(add_row, 0).findChild(QPushButton)
    assert plus.text() == "" and plus.height() <= 20
    qtbot.mouseClick(plus, Qt.LeftButton)
    assert len(window.notebook.children(parent)) == 2
    assert tasks.tree.findChild(QLineEdit).hasFocus()
    assert not tasks.findChild(type(tasks.summary), "taskHint")


@pytest.mark.parametrize("tab", [0, 1, 2, 3])
def test_global_todo_shortcut_from_every_tab(window, qtbot, tab):
    window.workspace.setCurrentIndex(tab)
    window.tasks.search.setText("no match")
    target = window.knowledge.search if tab == 1 else window.workspace
    target.setFocus()
    qtbot.keyClick(target, Qt.Key_T, Qt.ControlModifier)
    qtbot.waitUntil(lambda: window.workspace.currentIndex() == 0)
    editor = window.tasks.tree.findChild(QLineEdit)
    assert editor is not None and editor.hasFocus()
    qtbot.keyClicks(editor, "Fast parent")
    item = window.notebook.items[-1]
    assert item["parent_id"] is None and item["text"] == "Fast parent"
    assert window.notebook.children()[-1] == item
    assert Store(window.store.folder).load()["items"][-1]["text"] == "Fast parent"


@pytest.mark.parametrize("tab", [0, 1, 2, 3])
def test_global_note_shortcut_content_focus_and_enter_save(window, qtbot, tab):
    window.workspace.setCurrentIndex(tab)
    window.knowledge.search.setText("not visible")
    checked = []

    def fill():
        dialog = QApplication.activeModalWidget()

        assert isinstance(dialog, NewNote)
        assert dialog.title.text() == datetime.now().strftime("Note_%Y-%m-%d_%H-%M")
        assert dialog.extension.currentText() == ".txt"
        assert dialog.content.hasFocus()
        qtbot.keyClicks(dialog.content, "Quick note")
        qtbot.keyClick(dialog.content, Qt.Key_Return, Qt.ShiftModifier)
        qtbot.keyClicks(dialog.content, "Second line")
        qtbot.keyClick(dialog.content, Qt.Key_Return)
        checked.append(True)

    QTimer.singleShot(50, fill)
    qtbot.keyClick(window.workspace, Qt.Key_N, Qt.ControlModifier)
    assert checked and window.workspace.currentIndex() == 1
    paths = list(window.store.folder.glob("Note_*.txt"))
    assert len(paths) == 1 and paths[0].read_text() == "Quick note\nSecond line"
    assert window.knowledge.search.text() == ""


def test_note_markdown_title_override_and_collision(window, qtbot):
    dialog = NewNote(window.knowledge)
    qtbot.addWidget(dialog)
    dialog.title.setText("My note")
    dialog.extension.setCurrentText(".md")
    dialog.content.setPlainText("# Markdown")
    dialog.save()
    assert (window.store.folder / "My note.md").read_text() == "# Markdown"
    duplicate = NewNote(window.knowledge)
    qtbot.addWidget(duplicate)
    duplicate.title.setText("My note")
    duplicate.extension.setCurrentText(".md")
    duplicate.save()
    assert duplicate.document is None and "already exists" in duplicate.problem.text()


def test_schedule_editor_inbox_and_session_links(window, qtbot):
    dialog = ScheduleDialog(window.notebook.data["settings"], window)
    qtbot.addWidget(dialog)
    dialog.directory.setText(str(window.store.folder))
    dialog.save()
    assert "prompt" in dialog.problem.text()
    dialog.prompt.setPlainText("Check status")
    dialog.repeat.setChecked(True)
    dialog.every.setValue(3)
    dialog.unit.setCurrentText("weeks")
    dialog.save()
    assert dialog.values["every"] == 3 and dialog.values["unit"] == "weeks"
    assert window.workspace.tabText(3) == "Scheduled tasks"
    assert any(a.text() == "Keyboard shortcuts" for menu in window.menuBar().actions()
               if menu.menu() for a in menu.menu().actions())


def test_todo_shortcut_from_popped_out_terminal(window, qtbot):
    window.toggle_terminal_popout()
    popout = window.terminal_popout
    popout.activateWindow()
    qtbot.wait(20)
    qtbot.keyClick(popout, Qt.Key_T, Qt.ControlModifier)
    assert window.notebook.items[-1]["parent_id"] is None
    qtbot.waitUntil(lambda: window.tasks.tree.findChild(QLineEdit).hasFocus())
    window.dock_terminals()


def test_schedule_crud_run_inbox_and_navigation(window, qtbot, monkeypatch):
    import sys

    from app.ui.scheduled import ScheduleDialog

    panel = window.scheduled
    window.notebook.data["settings"]["profiles"] = [dict(
        id="test", name="Test", executable=sys.executable, args=["-c", "print('INBOX_RESULT')"])]

    def fill_schedule():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ScheduleDialog)
        dialog.title.setText("Inbox test")
        dialog.prompt.setPlainText("Run prompt")
        dialog.directory.setText(str(window.store.folder))
        dialog.agent.setCurrentIndex(dialog.agent.findData("test"))
        dialog.save()

    QTimer.singleShot(20, fill_schedule)
    panel.create()
    assert len(window.scheduler.jobs) == 1
    panel.toggle()
    assert not Store(window.store.folder).load()["scheduled_jobs"][0]["enabled"]
    panel.run_now()
    qtbot.waitUntil(lambda: not window.scheduler.active)
    assert panel.runs.count() == 1
    assert "INBOX_RESULT" in panel.output.toPlainText()
    run = panel.current_run()
    assert run["session_id"] in {s["id"] for s in window.notebook.data["sessions"]}
    navigation = []
    panel.session_open.disconnect()
    panel.session_details.disconnect()
    panel.session_open.connect(lambda ident: navigation.append(("open", ident)))
    panel.session_details.connect(lambda ident: navigation.append(("details", ident)))
    qtbot.mouseClick(panel.open_button, Qt.LeftButton)
    qtbot.mouseClick(panel.details_button, Qt.LeftButton)
    assert navigation == [("open", run["session_id"]), ("details", run["session_id"])]

    QTimer.singleShot(20, fill_schedule)
    panel.edit()
    assert panel.current_job()["prompt"] == "Run prompt"
    monkeypatch.setattr("app.ui.scheduled.confirm", lambda *args: True)
    panel.delete()
    assert not window.scheduler.jobs and panel.runs.count() == 0
    assert Store(window.store.folder).load()["sessions"]  # Deleting a job preserves session links.


def test_foreign_sessions_do_not_block_tasks_or_saving(window, monkeypatch, tmp_path):
    from app.models import uid

    sessions = window.notebook.data["sessions"]
    for agent in ("codex", "claude", "pi", "missing-profile"):
        sessions.append(dict(id=uid(), item_id=window.notebook.items[0]["id"], agent=agent,
                             workdir=str(tmp_path / "other-computer"), title="Foreign session",
                             native_session_id=None, created_at="invalid old timestamp"))

    def unavailable(*args):
        raise OSError("Local agent history is unavailable")

    monkeypatch.setattr("app.ui.window.native_sessions", unavailable)
    window.discover_session_ids()
    window.tasks.rebuild()
    assert window.flush()
    assert Store(window.store.folder).load()["sessions"] == sessions
    messages = []
    monkeypatch.setattr("app.ui.window.error", lambda parent, message: messages.append(str(message)))
    window.resume_session(sessions[0]["id"])
    assert "unavailable" in messages[0]
    assert len(window.notebook.items) == 3
