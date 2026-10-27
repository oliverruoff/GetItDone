import json

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QPlainTextEdit

from app.agents.replies import native_snapshot, text_content
from app.models import Notebook
from app.storage import Store
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
    second = dict(first, message="two", output="Second answer")
    window.apply_agent_snapshot("session", second)
    window.apply_agent_snapshot("session", second)
    window.apply_agent_snapshot("session", None)
    assert len(sent) == 1
    assert window.flush()
    saved = Store(tmp_path).load()["sessions"][0]
    assert saved["last_reply"]["text"] == "Second answer"
    assert saved["reply_unread"]

    def inspect_and_close():
        dialog = window.findChild(QDialog)
        assert dialog.findChild(QPlainTextEdit).toPlainText() == "Second answer"
        dialog.reject()

    QTimer.singleShot(0, inspect_and_close)
    window.show_last_reply("session")
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
        assert dialog.findChild(QPlainTextEdit).toPlainText() == "Saved independently"
        dialog.reject()

    QTimer.singleShot(0, close)
    window.show_last_reply("offline")
    assert window.flush()
    assert not Store(tmp_path).load()["sessions"][0]["reply_unread"]
    window.quitting = True
    window.tray.hide()
