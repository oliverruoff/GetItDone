import json
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from app.agents.replies import native_snapshot, text_content
from app.models import Notebook
from app.storage import Store
from app.ui.common import SafeBrowser
from app.ui.window import Window


def test_codex_exact_history_and_final_text(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    folder = tmp_path / "sessions"
    folder.mkdir()
    session = dict(agent="codex", native_session_id="exact", workdir=str(tmp_path))
    path = folder / "history.jsonl"
    entries = [
        dict(type="session_meta", payload=dict(id="exact", cwd=str(tmp_path))),
        dict(type="event_msg", payload=dict(type="task_started")),
        dict(type="event_msg", timestamp="one", payload=dict(type="agent_message", message="Answer ä")),
        dict(type="event_msg", timestamp="two", payload=dict(type="task_complete")),
    ]
    path.write_text("\n".join(map(json.dumps, entries)))
    result = native_snapshot(session)
    assert result["output"] == "Answer ä"
    assert not result["busy"]
    assert native_snapshot(dict(session, native_session_id="other")) is None


def test_history_utf8_metadata_and_reply(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    folder = tmp_path / "sessions"
    folder.mkdir()
    workdir = tmp_path / "Änderungen für Öl"
    workdir.mkdir()
    text = "## Rückmeldung\n\n**äöü ÄÖÜ ß**"
    entries = [
        dict(type="session_meta", payload=dict(id="unicode", cwd=str(workdir))),
        dict(type="event_msg", payload=dict(type="task_complete", last_agent_message=text)),
    ]
    (folder / "history.jsonl").write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries), encoding="utf-8"
    )
    session = dict(agent="codex", native_session_id="unicode", workdir=str(workdir))
    assert native_snapshot(session)["output"] == text


def test_opencode_reply_decodes_utf8(monkeypatch):
    from app.agents import status

    text = "## Rückmeldung\n\n**äöü ÄÖÜ ß**"
    run = subprocess.run

    def api(command, **kwargs):
        data = [] if command[2] == "session.active" else [
            dict(type="assistant", id="reply", time=dict(completed=1), content=[dict(type="text", text=text)])
        ]
        payload = json.dumps(dict(data=data), ensure_ascii=False).encode("utf-8")
        assert kwargs.get("encoding") == "utf-8"
        return run([sys.executable, "-c", f"import os; os.write(1, {payload!r})"], **kwargs)

    monkeypatch.setattr(status, "executable_path", lambda _: "opencode")
    monkeypatch.setattr(status.subprocess, "run", api)
    assert status.opencode_snapshot(["session"])["session"]["output"] == text


def test_text_excludes_tools_and_thinking():
    assert (
        text_content(
            [
                dict(type="thinking", text="private"),
                dict(type="tool_result", text="tool"),
                dict(type="text", text="Visible"),
            ]
        )
        == "Visible"
    )


def test_persist_reply_read_offline_and_do_not_notify_twice(qtbot, tmp_path, monkeypatch):
    store = Store(tmp_path)
    book = Notebook(store.load())
    item = book.add("Task")
    session = dict(
        id="session",
        item_id=item["id"],
        agent="codex",
        native_session_id="exact",
        title="Task",
        workdir=str(tmp_path),
        created_at=item["created_at"],
    )
    book.data["sessions"].append(session)
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.timer.stop()
    sent = []
    monkeypatch.setattr(window.notifier, "send", sent.append)
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    first = dict(busy=False, failed=False, message="one", output="First answer")
    window.apply_agent_snapshot("session", first)
    assert not sent  # Historical first import is quiet.
    markdown = "## Rückmeldung\n\n**äöü ÄÖÜ ß**\n\n- Prüfung\n\n```python\nprint('für')\n```"
    second = dict(first, message="two", output=markdown)
    window.apply_agent_snapshot("session", second)
    window.apply_agent_snapshot("session", second)
    window.apply_agent_snapshot("session", None)
    assert len(sent) == 1
    assert window.flush()
    saved = Store(tmp_path).load()["sessions"][0]
    assert saved["last_reply"]["text"] == markdown
    assert saved["reply_unread"]

    def inspect_and_close():
        dialog = window.findChild(QDialog)
        browser = dialog.findChild(SafeBrowser)
        rendered = browser.toPlainText()
        assert "Rückmeldung" in rendered
        assert "äöü ÄÖÜ ß" in rendered
        assert "print('für')" in rendered
        assert "##" not in rendered and "**" not in rendered and "```" not in rendered
        assert "<h2" in browser.toHtml()
        assert "font-weight:700" in browser.toHtml()
        assert browser.isReadOnly()
        assert not browser.openLinks() and not browser.openExternalLinks()
        dialog.reject()

    window.show_last_reply("session")
    inspect_and_close()
    assert not session["reply_unread"]
    assert not window.terminals
    window.quitting = True
    window.tray.hide()


def test_claude_and_pi_histories(tmp_path, monkeypatch):
    for agent, env, subdir in [
        ("claude", "CLAUDE_CONFIG_DIR", "projects"),
        ("pi", "PI_CODING_AGENT_DIR", "sessions"),
    ]:
        root = tmp_path / agent
        monkeypatch.setenv(env, str(root))
        folder = root / subdir / "project"
        folder.mkdir(parents=True)
        meta = dict(cwd=str(tmp_path), timestamp="2026-10-27T10:00:00Z")
        meta.update(sessionId="exact") if agent == "claude" else meta.update(type="session", id="exact")
        entries = [
            meta,
            dict(
                type="assistant" if agent == "claude" else "message",
                id="reply",
                message=dict(role="assistant", content=[dict(type="text", text="Final reply")]),
            ),
        ]
        (folder / "history.jsonl").write_text("\n".join(map(json.dumps, entries)))
        result = native_snapshot(dict(agent=agent, native_session_id="exact", workdir=str(tmp_path)))
        assert result["output"] == "Final reply"
        assert not result["status_known"]


def test_saved_reply_available_after_restart(qtbot, tmp_path, monkeypatch):
    store = Store(tmp_path)
    book = Notebook(store.load())
    item = book.add("Offline task")
    book.data["sessions"].append(
        dict(
            id="offline",
            item_id=item["id"],
            agent="codex",
            native_session_id="missing",
            title="Offline",
            workdir="/missing/folder",
            created_at=item["created_at"],
            reply_unread=True,
            last_reply=dict(text="Saved independently", saved_at=item["created_at"]),
        )
    )
    store.save(book.data)
    reopened = Store(tmp_path)
    window = Window(reopened, reopened.load())
    qtbot.addWidget(window)
    window.timer.stop()
    monkeypatch.setattr(window, "launch", lambda *_: (_ for _ in ()).throw(AssertionError("Must not launch")))

    def close():
        dialog = window.findChild(QDialog)
        assert dialog.findChild(SafeBrowser).toPlainText() == "Saved independently"
        dialog.reject()

    window.show_last_reply("offline")
    close()
    assert window.flush()
    assert not Store(tmp_path).load()["sessions"][0]["reply_unread"]
    window.quitting = True
    window.tray.hide()


def test_reply_does_not_block_main_window_and_is_deleted_on_close(qtbot, tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    item = book.add("Task")
    book.data["sessions"].append(dict(
        id="reply", item_id=item["id"], agent="codex", native_session_id=None,
        title="Task", workdir=str(tmp_path), created_at=item["created_at"],
        last_reply=dict(text="## Für äöü\n\n**Antwort**", saved_at=item["created_at"]),
    ))
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.timer.stop()
    window.show()
    window.show_last_reply("reply")
    dialog = window.findChild(QDialog, "lastReply:reply")
    assert dialog.isVisible()
    assert not dialog.isModal()
    assert dialog.windowType() != Qt.Popup
    assert QApplication.activeModalWidget() is None
    assert QApplication.activePopupWidget() is None
    assert QWidget.mouseGrabber() is None
    window.show_last_reply("reply")
    assert window.findChildren(QDialog, "lastReply:reply") == [dialog]

    ticks = []
    timer = QTimer(window)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(10)
    qtbot.waitUntil(lambda: len(ticks) >= 3)
    window.activateWindow()
    window.tasks.search.setFocus()
    qtbot.keyClicks(window.tasks.search, "responsive")
    assert window.tasks.search.text() == "responsive"
    dialog.close()
    qtbot.waitUntil(lambda: window.findChild(QDialog, "lastReply:reply") is None)
    window.show_last_reply("reply")
    assert window.findChild(QDialog, "lastReply:reply").isVisible()
    window.findChild(QDialog, "lastReply:reply").close()
    timer.stop()
    window.quitting = True
    window.tray.hide()
