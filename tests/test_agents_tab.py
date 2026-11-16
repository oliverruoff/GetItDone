import sys
from string import Template

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolButton

from app.executions import execution_records
from app.models import now_iso, uid
from app.storage import Store
from app.ui.dialogs import SessionDialog
from app.ui.theme import LIGHT, STYLESHEET
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
    assert panel.session_rows[session["id"]].text(0) == f"{session['title']} · {session['agent']}"
    assert "Ended" in panel.session_rows[session["id"]].toolTip(0)
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


def test_ad_hoc_session_starts_without_todo_and_preserves_clipboard(window, qtbot, monkeypatch):
    window.notebook.data["settings"].update(default_agent="codex", default_workdir=str(window.store.folder))
    monkeypatch.setattr(SessionDialog, "probe", lambda self: None)
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: sys.executable)

    def accept(dialog):
        dialog.check()
        return dialog.result()

    monkeypatch.setattr(SessionDialog, "exec", accept)
    real_launch = window.launch
    monkeypatch.setattr(window, "launch", lambda session, command, **kwargs: real_launch(
        session, [sys.executable, "-u", "-c", "import time; time.sleep(5)"], **kwargs))
    QApplication.clipboard().setText("Keep my clipboard")
    panel = open_agents(window, qtbot)
    qtbot.mouseClick(panel.new_session, Qt.LeftButton)
    session = window.notebook.data["sessions"][0]
    assert session["item_id"] is None
    assert not window.notebook.items
    assert panel.selected_session == session["id"]
    assert window.workspace.currentWidget() is panel
    assert window.terminals[session["id"]].seen
    assert QApplication.clipboard().text() == "Keep my clipboard"
    assert window.save_all()
    assert window.store.load()["sessions"][0]["item_id"] is None
    assert execution_records(window.notebook, window.terminals)[0]["origin"] == "Ad-hoc"


def test_ad_hoc_pin_persists_and_trash_only_hides_running_session(window, qtbot):
    _, session = attach(window, "Pinned ad-hoc session")
    session["item_id"] = None
    session["last_reply"] = {"text": "Keep this reply", "saved_at": now_iso()}
    assert window.launch(session, [sys.executable, "-u", "-c", "import time; time.sleep(5)"])
    terminal = window.terminals[session["id"]]
    panel = open_agents(window, qtbot)
    assert session["id"] in panel.session_rows
    assert "Pinned ad-hoc session" in panel.session_rows[session["id"]].text(0)
    assert window.save_all()
    assert not window.store.load()["sessions"][0].get("agents_hidden")
    button = panel.tree.itemWidget(panel.session_rows[session["id"]], 1)
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: session["id"] not in panel.session_rows)
    assert terminal.running
    assert window.session(session["id"]) is session
    assert session["last_reply"]["text"] == "Keep this reply"
    assert window.save_all()
    assert window.store.load()["sessions"][0]["agents_hidden"] is True
    assert execution_records(window.notebook, window.terminals)[0]["session_id"] == session["id"]
    window.open_session(session["id"])
    assert session["id"] in panel.session_rows
    assert panel.selected_session == session["id"]
    assert terminal.running and terminal.seen


def test_ended_ad_hoc_session_stays_pinned_after_terminal_close(window, qtbot):
    _, session = attach(window, "Quick question")
    session["item_id"] = None
    assert window.launch(session, [sys.executable, "-u", "-c", "print('AD_HOC_DONE')"])
    terminal = window.terminals[session["id"]]
    panel = open_agents(window, qtbot)
    qtbot.waitUntil(lambda: not terminal.running and not terminal.reader.is_alive(), timeout=10000)
    window.close_terminal(window.tabs.indexOf(terminal))
    assert session["id"] in panel.session_rows
    assert panel.saved.isVisible()
    assert panel.resume.isVisible()


@pytest.mark.parametrize("accepted", [False, True])
def test_cancelled_or_failed_ad_hoc_start_does_not_create_links(window, qtbot, monkeypatch, accepted):
    item = window.notebook.add("Selected todo must not be used")
    window.tasks.rebuild(select=item["id"])
    monkeypatch.setattr(SessionDialog, "probe", lambda self: None)
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: sys.executable)
    window.notebook.data["settings"]["default_workdir"] = str(window.store.folder)

    def accept(dialog):
        if accepted:
            dialog.check()
        return dialog.result()

    monkeypatch.setattr(SessionDialog, "exec", accept)
    calls = []

    def fail(session, command, **kwargs):
        calls.append(session)
        return False

    monkeypatch.setattr(window, "launch", fail)
    panel = open_agents(window, qtbot)
    qtbot.mouseClick(panel.new_session, Qt.LeftButton)
    assert not window.notebook.data["sessions"]
    assert window.notebook.items == [item]
    assert not panel.session_rows
    assert len(calls) == int(accepted)
    if accepted:
        assert calls[0]["item_id"] is None


def test_ad_hoc_sidebar_state_restored_from_disk_and_label_refreshes(window, qtbot):
    _, visible = attach(window, "Saved pin")
    _, hidden = attach(window, "Removed pin")
    visible["item_id"] = hidden["item_id"] = None
    hidden["agents_hidden"] = True
    assert window.save_all()
    window.notebook.data = window.store.load()
    panel = open_agents(window, qtbot)
    assert set(panel.session_rows) == {visible["id"]}
    saved = window.session(visible["id"])
    saved["title"] = "Renamed ad-hoc chat"
    window.session_changed(saved["id"])
    assert "Renamed ad-hoc chat" in panel.session_rows[saved["id"]].text(0)
    assert "Renamed ad-hoc chat" in panel.title.text()


def test_sidebar_uses_full_width_and_subtle_right_aligned_trash(window, qtbot):
    _, session = attach(window, "A comfortably long session title")
    session["item_id"] = None
    panel = open_agents(window, qtbot)
    panel.splitter.setSizes([320, 900])
    panel.tree.setStyleSheet(Template(STYLESHEET).substitute(LIGHT))
    qtbot.wait(50)
    tree = panel.tree
    assert panel.new_session.text() == "Session"
    assert not panel.new_session.icon().isNull()
    assert tree.font().pixelSize() == 15
    assert not tree.header().stretchLastSection()
    assert tree.columnWidth(1) == 30
    assert tree.columnWidth(0) >= tree.viewport().width() - 32
    button = tree.itemWidget(panel.session_rows[session["id"]], 1)
    assert isinstance(button, QToolButton) and button.autoRaise()
    assert button.iconSize().width() == 14
    assert button.geometry().right() >= tree.viewport().width() - 8
    before = tree.columnWidth(0)
    panel.splitter.setSizes([430, 790])
    qtbot.waitUntil(lambda: tree.columnWidth(0) > before)
    assert tree.columnWidth(0) >= tree.viewport().width() - 32


@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize("label", ["  My custom session  ", "   "])
def test_optional_session_title_is_used_and_persisted(window, qtbot, monkeypatch, standalone, label):
    item = window.notebook.add("Original todo title")
    window.tasks.rebuild(select=item["id"])
    window.notebook.data["settings"].update(default_agent="codex", default_workdir=str(window.store.folder))
    monkeypatch.setattr(SessionDialog, "probe", lambda self: None)
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: sys.executable)

    def accept(dialog):
        dialog.title.setText(label)
        dialog.check()
        return dialog.result()

    monkeypatch.setattr(SessionDialog, "exec", accept)
    real_launch = window.launch
    monkeypatch.setattr(window, "launch", lambda session, command, **kwargs: real_launch(
        session, [sys.executable, "-u", "-c", "print('TITLED_SESSION')"], **kwargs))
    panel = open_agents(window, qtbot)
    window.start_session(standalone=standalone)
    session = window.notebook.data["sessions"][0]
    expected = label.strip() or ("Ad-hoc session" if standalone else item["text"])
    assert session["title"] == expected
    assert session["title_custom"] == bool(label.strip())
    assert expected in panel.session_rows[session["id"]].text(0)
    if label.strip() and not standalone:
        window.notebook.update(item["id"], text="Renamed todo")
        window.schedule_save()
        assert expected in panel.session_rows[session["id"]].text(0)
        assert "Renamed todo" not in panel.session_rows[session["id"]].text(0)
    assert window.save_all()
    assert window.store.load()["sessions"][0]["title"] == expected


def test_unread_reply_dot_clears_only_when_session_is_viewed(window, qtbot, monkeypatch):
    _, first = attach(window, "Current session")
    _, unread = attach(window, "Session with new reply")
    first["item_id"] = unread["item_id"] = None
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    panel = open_agents(window, qtbot)
    snapshot = dict(output="A new assistant answer", message="reply-1", busy=False, failed=False)
    window.apply_agent_snapshot(unread["id"], snapshot)
    assert unread["reply_unread"]
    assert panel.session_rows[unread["id"]].text(0).startswith("● ")
    assert "Unread agent reply" in panel.session_rows[unread["id"]].toolTip(0)
    assert window.save_all()
    assert window.store.load()["sessions"][1]["reply_unread"]
    panel.tree.setCurrentItem(panel.session_rows[unread["id"]])
    assert "A new assistant answer" in panel.reply.toPlainText()
    assert not unread["reply_unread"]
    assert not panel.session_rows[unread["id"]].text(0).startswith("● ")
    assert not window.store.load()["sessions"][1]["reply_unread"]
    window.apply_agent_snapshot(unread["id"], snapshot)
    assert not unread["reply_unread"]
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window.apply_agent_snapshot(unread["id"], dict(snapshot, output="Another answer", message="reply-2"))
    assert unread["reply_unread"]
    assert panel.session_rows[unread["id"]].text(0).startswith("● ")
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    panel.refresh()
    assert not unread["reply_unread"]


def test_plain_terminal_output_is_not_an_unread_agent_reply(window, qtbot):
    _, first = attach(window, "Current")
    _, second = attach(window, "Terminal only")
    first["item_id"] = second["item_id"] = None
    panel = open_agents(window, qtbot)
    assert window.launch(second, [sys.executable, "-u", "-c", "print('OUTPUT_NOT_A_REPLY')"])
    terminal = window.terminals[second["id"]]
    qtbot.waitUntil(lambda: not terminal.running, timeout=10000)
    terminal.unread = True
    window.session_changed(second["id"])
    assert not panel.session_rows[second["id"]].text(0).startswith("● ")
    terminal.agent_message = True
    window.session_changed(second["id"])
    assert panel.session_rows[second["id"]].text(0).startswith("● ")


def test_sidebar_shows_only_title_and_agent_with_status_in_tooltip(window, qtbot):
    _, session = attach(window, "My session")
    session["item_id"] = None
    panel = open_agents(window, qtbot)
    row = panel.session_rows[session["id"]]
    assert row.text(0) == "My session · opencode"
    assert "Saved session" in row.toolTip(0)
    assert window.launch(session, [sys.executable, "-u", "-c", "import time; time.sleep(5)"])
    terminal = window.terminals[session["id"]]
    window.session_changed(session["id"])
    assert row.text(0) == "My session · opencode"
    assert "Terminal running" in row.toolTip(0)
    terminal.agent_state = "Agent running"
    window.session_changed(session["id"])
    assert row.text(0) == "My session · opencode"
    assert "Agent running" in row.toolTip(0)
