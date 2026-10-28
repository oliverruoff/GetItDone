from types import SimpleNamespace

from PySide6.QtCore import Qt

from app.agents.context import Finding, discover, jsonc
from app.ui.agent_context import AgentContextPanel


def test_jsonc_preserves_strings_and_removes_comments():
    assert jsonc('{// comment\n"url":"https://host/a,}", /* x */ "mcp":{"safe":{},},}') == {
        "url": "https://host/a,}",
        "mcp": {"safe": {}},
    }


def test_codex_override_and_inherited_sources(tmp_path, monkeypatch):
    home = tmp_path / "home"
    base = home / ".codex"
    base.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(base))
    (base / "AGENTS.md").write_text("global old")
    (base / "AGENTS.override.md").write_text("global effective")
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    child = root / "child"
    child.mkdir()
    (root / "AGENTS.md").write_text("shared parent instructions")
    (child / "AGENTS.md").write_text("child old")
    (child / "AGENTS.override.md").write_text("child effective")
    _, findings = discover("codex", child, home)
    effective = [f.content for f in findings if f.kind == "Instructions" and f.state != "Overridden"]
    assert effective == ["global effective", "shared parent instructions", "child effective"]
    assert len([f for f in findings if f.state == "Overridden"]) == 2
    assert next(f for f in findings if f.content == "shared parent instructions").scope == "Inherited"


def test_config_values_never_displayed_and_nested_skills_found(tmp_path, monkeypatch):
    home = tmp_path / "home"
    base = home / ".config/opencode"
    base.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    (base / "opencode.jsonc").write_text('{"mcp":{"safe":{"enabled":false,"env":{"TOKEN":"secret"}},},}')
    skill = base / "skills/team/testing/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Read this skill")
    _, findings = discover("opencode", tmp_path, home)
    server = next(f for f in findings if f.kind == "MCP")
    assert server.name == "safe" and server.state == "Disabled"
    assert "secret" not in str([f.content for f in findings])
    assert any(f.name == "testing" and f.content == "Read this skill" for f in findings)


def test_panel_works_without_sessions_and_ignores_stale_results(qtbot, monkeypatch, tmp_path):
    import app.ui.agent_context as module

    callbacks = []
    adapter = SimpleNamespace(
        name="Test agent", executable="test", probe=lambda: "1.0", context=lambda p: None
    )
    monkeypatch.setattr(module, "agents", lambda settings: {"test": adapter})
    monkeypatch.setattr(module, "executable_path", lambda name: "/bin/test")
    monkeypatch.setattr(module, "Job", lambda fn, callback, parent: callbacks.append(callback))
    panel = AgentContextPanel({"default_workdir": str(tmp_path)})
    qtbot.addWidget(panel)
    qtbot.waitUntil(lambda: bool(callbacks))
    old = callbacks[-1]
    panel.load()
    old(("old", ("2026-01-01T12:00:00", [Finding("Skill", "stale", "", "")])), None)
    assert panel.lists["Skill"].count() == 0
    current = Finding(
        "Instructions", "AGENTS.md", str(tmp_path / "AGENTS.md"), "Project", content="Actual instructions"
    )
    callbacks[-1](("1.0", ("2026-01-01T12:00:00", [current])), None)
    panel.tabs.setCurrentIndex(2)
    assert panel.lists["Instructions"].item(0).data(Qt.UserRole).name == "AGENTS.md"
    assert "Actual instructions" in panel.preview.toPlainText()
    assert str(tmp_path) in panel.preview.toPlainText()
    assert panel.agent.currentData() == "test"


def test_background_job_delivers_on_gui_thread_and_survives_owner_deletion(qtbot):
    import threading

    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication, QWidget
    from shiboken6 import isValid

    from app.ui.common import Job

    owner = QWidget()
    qtbot.addWidget(owner)
    received = []
    Job(lambda: "ready", lambda result, exc: received.append((result, exc, QThread.currentThread())), owner)
    qtbot.waitUntil(lambda: bool(received))
    assert received == [("ready", None, QApplication.instance().thread())]

    release = threading.Event()
    started = threading.Event()

    def work():
        started.set()
        release.wait(5)
        return "late"

    job = Job(work, lambda *args: received.append(args), owner)
    qtbot.waitUntil(started.is_set)
    owner.deleteLater()
    qtbot.waitUntil(lambda: not isValid(owner))
    release.set()
    qtbot.waitUntil(job.future.done)
    QApplication.processEvents()
    assert len(received) == 1
