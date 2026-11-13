import sys
from uuid import UUID, uuid4

import pytest
from PySide6.QtWidgets import QDialog

from app.agents.base import Agent
from app.executions import execution_records
from app.storage import Store
from app.ui.dialogs import SessionDialog
from app.ui.window import Window


@pytest.fixture
def dialog_factory(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(SessionDialog, "probe", lambda self: None)
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: "/bin/" + name)

    def create(agent="codex", **settings):
        dialog = SessionDialog({"default_agent": agent, "default_workdir": str(tmp_path), **settings})
        qtbot.addWidget(dialog)
        return dialog

    return create


@pytest.mark.parametrize("agent, flag", [
    ("opencode", "--session"), ("codex", "resume"), ("claude", "--resume"), ("pi", "--session"),
])
def test_existing_session_uses_exact_resume_command(dialog_factory, agent, flag, tmp_path):
    dialog = dialog_factory(agent)
    # Even OpenCode v2 must use the provided ID instead of generating one.
    dialog.supports_status = agent == "opencode"
    native = "ses_exact123" if agent == "opencode" else str(uuid4())
    dialog.existing_session.setText("  " + native + "  ")
    assert dialog.start_button.text() == "Link existing session"
    dialog.check()
    assert dialog.result() == QDialog.Accepted
    assert dialog.linking_existing
    assert dialog.native_session_id == native
    assert dialog.command == ["/bin/" + dialog.registry[agent].executable, flag, native]
    assert dialog.directory == str(tmp_path.resolve())


@pytest.mark.parametrize("agent", ["opencode", "codex", "claude", "pi"])
def test_empty_session_id_keeps_new_session_behavior(dialog_factory, agent):
    dialog = dialog_factory(agent)
    dialog.supports_status = agent == "opencode"
    dialog.existing_session.setText("   ")
    assert dialog.start_button.text() == "New session"
    dialog.check()
    assert dialog.result() == QDialog.Accepted
    assert not dialog.linking_existing
    if agent in ("claude", "pi"):
        assert str(UUID(dialog.native_session_id)) == dialog.native_session_id
        assert dialog.command[-2:] == ["--session-id", dialog.native_session_id]
    elif agent == "opencode":
        assert dialog.native_session_id.startswith("ses_")
        assert dialog.command[-2:] == ["--session", dialog.native_session_id]
    else:
        assert dialog.native_session_id is None
        assert dialog.command == ["/bin/codex"]


@pytest.mark.parametrize("agent, invalid", [
    ("opencode", "partial-id"), ("codex", "--last"), ("claude", "partial-id"), ("pi", "partial-id"),
])
def test_invalid_id_does_not_start_or_create_folder(dialog_factory, monkeypatch, tmp_path, agent, invalid):
    dialog = dialog_factory(agent)
    errors = []
    monkeypatch.setattr("app.ui.dialogs.error", lambda parent, exc: errors.append(str(exc)))
    target = tmp_path / "must-not-be-created"
    dialog.workdir.setText(str(target))
    dialog.existing_session.setText(invalid)
    dialog.check()
    assert dialog.result() != QDialog.Accepted
    assert errors
    assert not hasattr(dialog, "command")
    assert not target.exists()


def test_pi_accepts_absolute_session_file_path(dialog_factory, tmp_path):
    path = tmp_path / "session with spaces.jsonl"
    path.write_text('{}\n', encoding="utf-8")
    dialog = dialog_factory("pi")
    dialog.existing_session.setText(str(path))
    dialog.check()
    assert dialog.result() == QDialog.Accepted
    assert dialog.native_session_id == str(path)
    assert dialog.command == ["/bin/pi", "--session", str(path)]


def test_agent_selection_updates_id_help_and_custom_profile_disables_linking(dialog_factory):
    dialog = dialog_factory(profiles=[dict(id="custom", name="Custom", executable="custom", args=[])])
    for agent, hint in [("opencode", "Copy session ID"), ("codex", "/status"),
                        ("claude", ".jsonl"), ("pi", "/session")]:
        dialog.agent.setCurrentIndex(dialog.agent.findData(agent))
        assert dialog.existing_session.isEnabled()
        assert hint in dialog.session_hint.text()
    dialog.existing_session.setText(str(uuid4()))
    dialog.agent.setCurrentIndex(dialog.agent.findData("custom"))
    assert not dialog.existing_session.isEnabled()
    assert "does not support" in dialog.session_hint.text()
    assert dialog.start_button.text() == "New session"
    dialog.check()
    assert dialog.command == ["/bin/custom"]
    assert not dialog.linking_existing
    assert dialog.native_session_id is None


def test_installation_probe_does_not_overwrite_link_mode(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, "probe", lambda self: "opencode v2.0.0")
    dialog = SessionDialog({"default_agent": "opencode", "default_workdir": str(tmp_path)})
    qtbot.addWidget(dialog)
    dialog.existing_session.setText("ses_existing123")
    qtbot.waitUntil(lambda: dialog.start_button.isEnabled())
    assert dialog.supports_status
    assert dialog.start_button.text() == "Link existing session"
    assert "Copy session ID" in dialog.session_hint.text()


@pytest.mark.parametrize("link_existing", [False, True])
def test_todo_session_link_persists_and_run_is_marked_resumed(qtbot, tmp_path, monkeypatch, link_existing):
    monkeypatch.setattr(SessionDialog, "probe", lambda self: None)
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: "/bin/" + name)
    native = str(uuid4())
    store = Store(tmp_path)
    window = Window(store, store.load())
    qtbot.addWidget(window)
    window.timer.stop()
    window.notebook.data["settings"].update(default_agent="codex", default_workdir=str(tmp_path))
    item = window.notebook.add("Continue my existing work")
    window.tasks.rebuild(select=item["id"])
    window.show()

    def accept(dialog):
        if link_existing:
            dialog.existing_session.setText(native)
        dialog.check()
        return dialog.result()

    monkeypatch.setattr(SessionDialog, "exec", accept)
    real_launch = window.launch
    commands = []

    def launch(session, command, *, resumed=False):
        commands.append(command)
        # Exercise the real terminal and persistence without touching a user's agent history.
        return real_launch(session, [sys.executable, "-u", "-c",
                                     "import time; print('LINK_TEST', flush=True); time.sleep(.3)"], resumed=resumed)

    monkeypatch.setattr(window, "launch", launch)
    try:
        window.start_session()
        saved = window.notebook.data["sessions"][0]
        terminal = window.terminals[saved["id"]]
        assert saved["item_id"] == item["id"]
        assert saved["agent"] == "codex"
        assert saved["native_session_id"] == (native if link_existing else None)
        assert commands == [["/bin/codex", "resume", native] if link_existing else ["/bin/codex"]]
        assert saved["process_runs"][0]["resumed"] is link_existing
        assert terminal.agent_baselined is not link_existing
        assert saved["id"] in window.tasks.session_rows
        assert execution_records(window.notebook, window.terminals)[0]["origin"] == (
            "Resumed" if link_existing else "Todo"
        )
        qtbot.waitUntil(lambda: not terminal.running, timeout=10000)
        qtbot.waitUntil(lambda: not terminal.reader.is_alive(), timeout=10000)
        assert window.flush()
        persisted = Store(tmp_path).load()["sessions"][0]
        assert persisted["native_session_id"] == saved["native_session_id"]
        assert persisted["process_runs"][0]["resumed"] is link_existing
    finally:
        for terminal in window.all_terminals():
            terminal.stop()
        window.scheduler.shutdown()
        window.notifier.close()
        window.tray.hide()
        window.quitting = True
        window.close()
