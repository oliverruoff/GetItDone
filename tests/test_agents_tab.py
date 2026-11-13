import sys

import pytest
from PySide6.QtCore import Qt

from app.models import now_iso, uid
from app.storage import Store
from app.ui.window import Window


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    def unexpected_error(parent, message):
        raise AssertionError(str(message))

    monkeypatch.setattr("app.ui.window.error", unexpected_error)
    store = Store(tmp_path)
    window = Window(store, store.load())
    window.timer.stop()
    window.show()
    yield window
    for terminal in window.all_terminals():
        terminal.stop()
        qtbot.waitUntil(lambda t=terminal: not t.running, timeout=10000)
        if hasattr(terminal, "reader"):
            qtbot.waitUntil(lambda t=terminal: not t.reader.is_alive(), timeout=10000)
    window.scheduler.shutdown()
    window.notifier.close()
    window.tray.hide()
    window.quitting = True
    window.close()
    window.deleteLater()


def attach(window, text, parent=None):
    item = window.notebook.add(text, parent)
    session = dict(id=uid(), item_id=item["id"], agent="opencode", title=text,
                   workdir=str(window.store.folder), native_session_id="ses_test" + uid().replace("-", ""),
                   created_at=now_iso())
    window.notebook.data["sessions"].append(session)
    return item, session


def open_agents(window, qtbot):
    page = window.optional_pages["agents"]
    window.workspace.setCurrentIndex(page["index"])
    qtbot.waitUntil(lambda: page["widget"] is not None)
    return page["widget"]


def test_agents_empty_page_loads_lazily(window, qtbot):
    assert window.optional_pages["agents"]["widget"] is None
    panel = open_agents(window, qtbot)
    assert panel.tree.topLevelItemCount() == 0
    assert panel.sidebar_empty.isVisible()
    assert panel.saved.isVisible()
    assert not panel.resume.isVisible()
    assert not window.terminal_panel.isVisible()
    assert all(page["widget"] is None for name, page in window.optional_pages.items() if name != "agents")


def test_agents_hierarchy_only_open_linked_tasks_and_grouping(window, qtbot):
    book = window.notebook
    parent = book.add("Parent without session")
    middle = book.add("Middle without session", parent["id"])
    child, session = attach(window, "Grandchild with saved session", middle["id"])
    other, other_session = attach(window, "Other saved session")
    done, done_session = attach(window, "Completed session")
    book.complete(done["id"], True)
    book.add("Unlinked open todo")
    session["last_reply"] = {"text": "**Saved agent response**", "saved_at": now_iso()}
    panel = open_agents(window, qtbot)
    assert set(panel.rows) == {parent["id"], middle["id"], child["id"], other["id"]}
    assert set(panel.session_rows) == {session["id"], other_session["id"]}
    assert panel.rows[child["id"]].parent() is panel.rows[middle["id"]]
    assert panel.rows[middle["id"]].parent() is panel.rows[parent["id"]]
    assert not panel.rows[parent["id"]].flags() & Qt.ItemIsSelectable
    assert panel.selected_session == session["id"]
    assert "Saved agent response" in panel.reply.toPlainText()
    assert panel.resume.isVisible()
    assert not window.terminals
    panel.tree.setCurrentItem(panel.session_rows[other_session["id"]])
    assert panel.selected_session == other_session["id"]
    book.update(other["id"], text="Renamed todo")
    window.schedule_save()
    assert "Renamed todo" in panel.rows[other["id"]].text(0)
    assert panel.selected_session == other_session["id"]
    book.complete(child["id"], True)
    window.schedule_save()
    assert set(panel.rows) == {other["id"]}
    assert done_session["id"] not in panel.session_rows


def test_agents_multiple_sessions_per_todo_and_collapsed_groups(window, qtbot):
    parent = window.notebook.add("Group")
    item, session = attach(window, "Task", parent["id"])
    second = dict(session, id=uid(), title="Second attached session")
    window.notebook.data["sessions"].append(second)
    panel = open_agents(window, qtbot)
    row = panel.rows[item["id"]]
    assert not row.flags() & Qt.ItemIsSelectable
    assert panel.session_rows[session["id"]].parent() is row
    assert panel.session_rows[second["id"]].parent() is row
    panel.rows[parent["id"]].setExpanded(False)
    window.notebook.update(item["id"], text="Updated task")
    window.schedule_save()
    assert not panel.rows[parent["id"]].isExpanded()


def test_agents_reuses_real_terminals_switches_visibility_and_preserves_processes(window, qtbot):
    first_item, first = attach(window, "First agent")
    _, second = attach(window, "Second agent")
    _, saved = attach(window, "Saved agent")
    command = [sys.executable, "-u", "-c", "import time; print('AGENTS_TAB_READY', flush=True); time.sleep(5)"]
    assert window.launch(first, command)
    assert window.launch(second, command)
    first_terminal = window.terminals[first["id"]]
    second_terminal = window.terminals[second["id"]]
    panel = open_agents(window, qtbot)
    assert window.tabs.currentWidget() is first_terminal
    assert first_terminal.seen and not second_terminal.seen
    assert not window.tabs.tabBar().isVisible()
    assert first_terminal.isVisible()
    assert not panel.saved.isVisible()
    assert panel.content.isAncestorOf(first_terminal)
    assert panel.content.width() > panel.splitter.widget(0).width()
    panel.tree.setCurrentItem(panel.session_rows[second["id"]])
    assert window.tabs.currentWidget() is second_terminal
    assert second_terminal.seen and not first_terminal.seen
    assert window.tabs.count() == 2
    panel.tree.setCurrentItem(panel.session_rows[saved["id"]])
    assert panel.saved.isVisible()
    assert not window.terminal_panel.isVisible()
    assert not first_terminal.seen and not second_terminal.seen
    panel.tree.setCurrentItem(panel.session_rows[second["id"]])
    assert second_terminal.seen and window.terminal_panel.isVisible()
    window.workspace.setCurrentIndex(0)
    assert window.vertical.indexOf(window.terminal_panel) == 1
    assert window.tabs.tabBar().isVisible()
    assert first_terminal.running and second_terminal.running
    window.workspace.setCurrentIndex(window.optional_pages["agents"]["index"])
    assert panel.selected_session == second["id"]
    assert window.tabs.currentWidget() is second_terminal
    window.complete(first_item["id"], True)
    assert first["id"] not in panel.session_rows
    assert first_terminal.running
    window.hide()
    window.visibility()
    assert not first_terminal.seen and not second_terminal.seen


def test_ended_session_stays_visible_and_close_retains_saved_reply(window, qtbot):
    _, session = attach(window, "Ended agent")
    session["last_reply"] = {"text": "The saved answer", "saved_at": now_iso()}
    assert window.launch(session, [sys.executable, "-u", "-c", "print('ENDED_AGENT')"])
    terminal = window.terminals[session["id"]]
    panel = open_agents(window, qtbot)
    qtbot.waitUntil(lambda: not terminal.running, timeout=10000)
    window.session_changed(session["id"])
    assert session["id"] in panel.session_rows
    assert "Ended" in panel.session_rows[session["id"]].text(0)
    assert panel.resume.isVisible()
    assert window.tabs.currentWidget() is terminal
    qtbot.waitUntil(lambda: not terminal.reader.is_alive(), timeout=10000)
    qtbot.mouseClick(panel.close_terminal, Qt.LeftButton)
    assert not window.terminals
    assert session["id"] in panel.session_rows
    assert panel.saved.isVisible()
    assert "The saved answer" in panel.reply.toPlainText()


def test_resume_saved_session_keeps_agents_tab(window, qtbot, monkeypatch):
    _, session = attach(window, "Resume agent")
    panel = open_agents(window, qtbot)
    real_launch = window.launch
    calls = []

    def launch(saved, command, **kwargs):
        calls.append(command)
        return real_launch(saved, [sys.executable, "-u", "-c", "import time; time.sleep(5)"], **kwargs)

    monkeypatch.setattr(window, "launch", launch)
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: sys.executable)
    qtbot.mouseClick(panel.resume, Qt.LeftButton)
    assert len(calls) == 1
    assert session["native_session_id"] in calls[0]
    assert window.workspace.currentWidget() is panel
    assert window.tabs.currentWidget() is window.terminals[session["id"]]
    assert window.terminals[session["id"]].seen
    assert not panel.saved.isVisible()


def test_agents_docks_popout_without_restarting_terminal(window, qtbot):
    _, session = attach(window, "Popout agent")
    assert window.launch(session, [sys.executable, "-u", "-c", "import time; time.sleep(5)"])
    terminal = window.terminals[session["id"]]
    window.toggle_terminal_popout()
    assert window.terminal_popout is not None
    panel = open_agents(window, qtbot)
    assert window.terminal_popout is None
    assert panel.content.isAncestorOf(terminal)
    assert terminal.running and terminal.seen
