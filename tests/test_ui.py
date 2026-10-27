import sys

import pytest
from PySide6.QtPdf import QPdfDocument

from app.models import Notebook
from app.storage import Store
from app.terminal.bridge import Terminal
from app.ui.knowledge import Knowledge
from app.ui.window import Window


def test_window_roundtrip_and_visible_hierarchy(qtbot, tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    a = book.add("Parent")
    b = book.add("Child", parent=a["id"])
    book.update(b["id"], notes="Notes with Unicode ä")
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.show()
    assert window.tasks.tree.topLevelItemCount() == 1
    window.tasks.search.setText("Unicode")
    assert set(window.tasks.rows) == {a["id"], b["id"]}
    assert window.flush()
    assert Store(tmp_path).load()["items"][1]["notes"] == "Notes with Unicode ä"
    window.timer.stop()
    window.tray.hide()
    window.quitting = True


def test_knowledge_opens_edits_and_saves_without_json_content(qtbot, tmp_path):
    (tmp_path / "Note.txt").write_text("Text")
    (tmp_path / "Readme.md").write_text("# Heading\n\n**Bold**")
    settings = {"knowledge_folder": str(tmp_path)}
    widget = Knowledge(settings)
    qtbot.addWidget(widget)
    widget.show()
    widget.files.setCurrentRow(0)
    qtbot.waitUntil(lambda: widget.document is not None)
    widget.editor.setPlainText("Changed\nSecond line")
    qtbot.waitUntil(lambda: not widget.dirty, timeout=3000)
    assert (tmp_path / "Note.txt").read_text() == "Changed\nSecond line"
    widget.files.setCurrentRow(1)
    qtbot.waitUntil(lambda: widget.stack.currentWidget() is widget.browser)
    assert "Heading" in widget.browser.toPlainText()
    assert set(settings) == {"knowledge_folder", "knowledge_last_file"}


def test_pdf_pages_render_in_app(qtbot, tmp_path):
    from PySide6.QtGui import QPainter, QPdfWriter

    path = tmp_path / "Pages.pdf"
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    painter.drawText(100, 300, "Page one")
    writer.newPage()
    painter.drawText(100, 300, "Page two")
    painter.end()
    del writer
    widget = Knowledge({"knowledge_folder": str(tmp_path)})
    qtbot.addWidget(widget)
    widget.show()
    widget.files.setCurrentRow(0)
    qtbot.waitUntil(lambda: widget.pdf_document.status() == QPdfDocument.Status.Ready)
    assert widget.pdf_document.pageCount() == 2
    assert widget.stack.currentWidget() is widget.pdf
    assert not widget.pdf_document.render(0, widget.size()).isNull()


def test_integrated_terminal_real_pty_input_resize_unread_and_exit(qtbot, tmp_path):
    terminal = Terminal()
    qtbot.addWidget(terminal)
    terminal.resize(800, 300)
    terminal.show()
    outputs = []
    terminal.output_ready.connect(outputs.append)
    qtbot.waitUntil(lambda: terminal.ready_state, timeout=15000)
    terminal.start(
        [
            sys.executable,
            "-u",
            "-c",
            "import os,sys; print('READY ä',os.isatty(0),flush=True); s=input(); print('ECHO:'+s,flush=True)",
        ],
        str(tmp_path),
    )
    qtbot.waitUntil(lambda: "READY ä True" in "".join(outputs), timeout=10000)
    assert terminal.unread
    terminal.mark_visible(True)
    assert not terminal.unread
    terminal.resize_terminal(120, 32)
    terminal.input("hello\r")
    qtbot.waitUntil(lambda: "ECHO:hello" in "".join(outputs), timeout=10000)
    qtbot.waitUntil(lambda: not terminal.running)
    assert not terminal.unread
    assert not list(tmp_path.iterdir())


def test_tray_visibility_keeps_process_and_marks_hidden_output(qtbot, tmp_path):
    store = Store(tmp_path)
    window = Window(store, store.load())
    qtbot.addWidget(window)
    window.show()
    session = {"id": "s", "agent": "test", "title": "Terminal", "workdir": str(tmp_path)}
    assert window.launch(
        session, [sys.executable, "-u", "-c", "import time; time.sleep(.5); print('hidden'); time.sleep(10)"]
    )
    terminal = window.terminals["s"]
    window.toggle_terminal_popout()
    assert terminal.running
    assert terminal.window() is window.terminal_popout
    window.terminal_popout.close()
    assert window.tabs.currentWidget() is terminal
    assert terminal.running
    window.hide()
    assert terminal.running
    assert not terminal.seen
    qtbot.waitUntil(lambda: terminal.unread, timeout=10000)
    window.restore()
    qtbot.waitUntil(lambda: not terminal.unread)
    terminal.stop()
    qtbot.waitUntil(lambda: not terminal.running, timeout=8000)
    window.timer.stop()
    window.tray.hide()
    window.quitting = True


def test_keyboard_enter_adds_sibling_and_tab_indents(qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLineEdit

    store = Store(tmp_path)
    window = Window(store, store.load())
    qtbot.addWidget(window)
    window.show()
    window.add_item()
    editor = window.tasks.tree.findChild(QLineEdit)
    assert editor is not None
    editor.selectAll()
    qtbot.keyClicks(editor, "First item")
    qtbot.keyClick(editor, Qt.Key_Return)
    qtbot.waitUntil(lambda: len(window.notebook.items) == 2)
    assert window.notebook.items[0]["text"] == "First item"
    editor = window.tasks.tree.findChild(QLineEdit)
    editor.selectAll()
    qtbot.keyClicks(editor, "Second item")
    qtbot.keyClick(editor, Qt.Key_Tab)
    qtbot.waitUntil(lambda: window.notebook.items[1]["parent_id"] is not None)
    assert window.notebook.items[1]["parent_id"] == window.notebook.items[0]["id"]
    assert window.notebook.items[1]["text"] == "Second item"
    window.timer.stop()
    window.saver.stop()
    window.tray.hide()
    window.quitting = True


def test_completion_confirmation_does_not_stop_agent(qtbot, tmp_path, monkeypatch):
    from app.models import now_iso, uid

    store = Store(tmp_path)
    book = Notebook(store.load())
    item = book.add("Task")
    session = dict(
        id=uid(),
        item_id=item["id"],
        agent="test",
        title="Agent",
        workdir=str(tmp_path),
        native_session_id=None,
        created_at=now_iso(),
    )
    book.data["sessions"].append(session)
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.show()
    window.launch(session, [sys.executable, "-u", "-c", "import time; time.sleep(20)"])
    terminal = window.terminals[session["id"]]
    monkeypatch.setattr("app.ui.window.confirm", lambda *args: False)
    window.complete(item["id"], True)
    assert not item["done"] and terminal.running
    monkeypatch.setattr("app.ui.window.confirm", lambda *args: True)
    window.complete(item["id"], True)
    assert item["done"] and terminal.running
    assert item["id"] not in window.tasks.rows
    # Deleting the persistent link also leaves the process in its tab.
    window.notebook.delete(item["id"])
    assert terminal.running and window.tabs.count() == 1
    terminal.stop()
    qtbot.waitUntil(lambda: not terminal.running, timeout=8000)
    window.timer.stop()
    window.saver.stop()
    window.tray.hide()
    window.quitting = True


def test_failed_session_start_does_not_leave_link_or_tab(qtbot, tmp_path, monkeypatch):
    from app.models import now_iso, uid

    store = Store(tmp_path)
    book = Notebook(store.load())
    item = book.add("Task")
    window = Window(store, book.data)
    qtbot.addWidget(window)
    monkeypatch.setattr("app.ui.window.error", lambda *args: None)
    session = dict(
        id=uid(),
        item_id=item["id"],
        agent="test",
        title="Fail",
        workdir=str(tmp_path / "missing"),
        native_session_id=None,
        created_at=now_iso(),
    )
    assert not window.launch(session, [sys.executable])
    assert not window.terminals and not book.data["sessions"] and window.tabs.count() == 0
    window.timer.stop()
    window.tray.hide()
    window.quitting = True


def test_external_txt_conflict_stays_in_editor(qtbot, tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("original")
    widget = Knowledge({"knowledge_folder": str(tmp_path)})
    qtbot.addWidget(widget)
    widget.files.setCurrentRow(0)
    qtbot.waitUntil(lambda: widget.document is not None)
    path.write_text("external changes")
    widget.editor.setPlainText("my changes")
    assert not widget.save()
    assert widget.dirty and widget.editor.toPlainText() == "my changes"
    assert path.read_text() == "external changes"
    assert "NOT SAVED" in widget.status.text()
    widget.autosave.stop()


def test_parallel_terminals_and_ctrl_c(qtbot, tmp_path):
    terminals = []
    for _ in range(2):
        terminal = Terminal()
        qtbot.addWidget(terminal)
        terminal.show()
        terminal.start(
            [sys.executable, "-u", "-c", "import time; print('READY', flush=True); time.sleep(30)"],
            str(tmp_path),
        )
        terminals.append(terminal)
    qtbot.waitUntil(lambda: all(t.ready_state and t.unread for t in terminals), timeout=15000)
    terminals[0].input("\x03")
    qtbot.waitUntil(lambda: not terminals[0].running, timeout=5000)
    assert terminals[1].running
    terminals[1].stop()
    qtbot.waitUntil(lambda: not terminals[1].running, timeout=8000)


def test_inline_actions_and_append_always_create_root_at_end(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt

    store = Store(tmp_path)
    book = Notebook(store.load())
    parent = book.add("Parent")
    child = book.add("Child", parent=parent["id"])
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.show()
    tasks = window.tasks
    tasks.tree.setCurrentItem(tasks.rows[child["id"]])
    called = []
    monkeypatch.setattr(window, "assign_category", lambda: called.append(tasks.current_id()))
    qtbot.mouseClick(tasks.tree.itemWidget(tasks.rows[parent["id"]], 1), Qt.LeftButton)
    assert called == [parent["id"]]
    tasks.tree.setCurrentItem(tasks.rows[child["id"]])
    qtbot.mouseClick(tasks.add_button, Qt.LeftButton)
    assert len(book.items) == 3
    assert window.notebook.items[-1]["parent_id"] is None
    assert tasks.add_button.parent() is tasks
    assert tasks.add_button.width() == tasks.tree.width()
    assert tasks.add_button.x() == tasks.tree.x()
    window.timer.stop()
    window.saver.stop()
    window.tray.hide()
    window.quitting = True


@pytest.mark.parametrize("agent_id", ["codex", "opencode"])
def test_resume_without_open_terminal_opens_exact_session_immediately(qtbot, tmp_path, monkeypatch, agent_id):
    from uuid import uuid4

    from app.agents.base import Agent
    from app.models import now_iso, uid

    store = Store(tmp_path)
    book = Notebook(store.load())
    item = book.add("Resume this session")
    native_id = str(uuid4())
    session = dict(
        id=uid(),
        item_id=item["id"],
        agent=agent_id,
        title="Saved session",
        workdir=str(tmp_path),
        native_session_id=native_id,
        created_at=now_iso(),
    )
    book.data["sessions"].append(session)
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.show()
    window.workspace.setCurrentIndex(1)
    window.terminal_panel.hide()
    # Use a local interactive process so this test needs no installed/authenticated CLI.
    adapter = Agent(
        agent_id,
        agent_id,
        sys.executable,
        args=("-u", "-c", "import sys; print('SESSION:'+sys.argv[1], flush=True); input()"),
        resume_args=("{id}",),
    )
    monkeypatch.setattr("app.ui.window.agents", lambda settings: {agent_id: adapter})
    monkeypatch.setattr(window, "refresh_context", lambda: None)

    def unexpected_dialog(*args):
        raise AssertionError("Resuming a known session must not request confirmation or details")

    monkeypatch.setattr("app.ui.window.confirm", unexpected_dialog)
    monkeypatch.setattr(window, "session_details", unexpected_dialog)
    from PySide6.QtCore import QTimer

    from app.ui.dialogs import ReminderDialog

    # A previously opened editor must not leave a global filter behind when
    # WebEngine creates/focuses its private Qt Quick widgets during Resume.
    reminder = ReminderDialog(item, window)
    QTimer.singleShot(0, reminder.reject)
    reminder.exec()
    window.resume_session(session["id"])
    terminal = window.terminals[session["id"]]
    output = []
    terminal.output_ready.connect(output.append)
    try:
        qtbot.waitUntil(lambda: "SESSION:" + native_id in "".join(output), timeout=15000)
        assert window.workspace.currentIndex() == 0
        assert window.tabs.currentWidget() is terminal
        assert window.terminal_panel.isVisible()
        assert window.tabs.count() == 1
        # A repeated resume focuses this process, instead of creating a second one.
        window.resume_session(session["id"])
        assert window.tabs.count() == 1
        assert window.terminals[session["id"]] is terminal
    finally:
        terminal.stop()
        qtbot.waitUntil(lambda: not terminal.running, timeout=8000)
        qtbot.waitUntil(lambda: not terminal.reader.is_alive(), timeout=8000)
        window.timer.stop()
        window.saver.stop()
        window.tray.hide()
        window.quitting = True


def test_task_drop_reorders_nests_and_emits_save(qtbot):
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QAbstractItemView

    from app.ui.tasks import Tasks

    book = Notebook()
    a = book.add("A")
    child = book.add("Child", parent=a["id"])
    b = book.add("B")
    tasks = Tasks(book, {})
    qtbot.addWidget(tasks)
    tasks.resize(1000, 500)
    tasks.show()
    changes = []
    tasks.changed.connect(lambda: changes.append(True))

    class Drop:
        accepted = False

        def source(self):
            return tasks.tree

        def position(self):
            return QPointF(tasks.tree.visualItemRect(tasks.rows[b["id"]]).center())

        def setDropAction(self, action):
            pass

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.accepted = False

    tasks.tree.setCurrentItem(tasks.rows[a["id"]])
    tasks.tree.dropIndicatorPosition = lambda: QAbstractItemView.AboveItem
    drop = Drop()
    tasks.tree.dropEvent(drop)
    assert drop.accepted and changes == [True]
    tasks.tree.setCurrentItem(tasks.rows[a["id"]])
    tasks.tree.dropIndicatorPosition = lambda: QAbstractItemView.OnItem
    tasks.tree.dropEvent(drop)
    assert a["parent_id"] == b["id"]
    assert child["parent_id"] == a["id"]
    assert len(changes) == 2
    tasks.tree.setCurrentItem(tasks.rows[b["id"]])
    tasks.drop_item(b["id"], child["id"], None)
    assert b["parent_id"] is None
    assert len(changes) == 2
