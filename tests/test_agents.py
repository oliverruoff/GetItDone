from uuid import uuid4

import pytest

from app.agents import agents
from app.agents.base import Agent
from app.agents.context import discover
from app.terminal.bridge import Activity
from app.ui.window import Window


def test_commands_are_literal_argument_lists(monkeypatch):
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: "/bin/" + name)
    registry = agents({})
    ident = str(uuid4())
    assert registry["codex"].command(ident) == ["/bin/codex", "resume", ident]
    assert registry["claude"].command(ident) == ["/bin/claude", "--resume", ident]
    assert registry["pi"].command(ident) == ["/bin/pi", "--session", ident]
    assert registry["opencode"].command("ses_exact") == ["/bin/opencode", "--session", "ses_exact"]
    assert registry["codex"].command() == ["/bin/codex"]
    assert Agent("custom", "Custom", "binary", ("literal; $(no)",)).command() == [
        "/bin/binary",
        "literal; $(no)",
    ]
    with pytest.raises(ValueError):
        registry["codex"].command("--last")


def test_missing_agent_and_strict_resume_ids(monkeypatch):
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: None)
    with pytest.raises(ValueError):
        agents({})["codex"].command()
    for agent in ("codex", "claude", "pi"):
        with pytest.raises(ValueError):
            Window.validate_native_id(agent, "partial-id")
        Window.validate_native_id(agent, str(uuid4()))
    Window.validate_native_id("opencode", "ses_abcd123")


def test_context_only_reports_names_never_secrets(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    home = tmp_path / "home"
    base = home / ".codex"
    base.mkdir(parents=True)
    secret = "super-secret-token"
    (base / "config.toml").write_text(
        f'[mcp_servers.safe]\ncommand="server"\n[mcp_servers.safe.env]\nTOKEN="{secret}"'
    )
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text(secret)
    skill = project / ".agents/skills/skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(secret)
    stamp, findings = discover("codex", project, home)
    assert any(f.kind == "MCP" and f.name == "safe" and f.state == "Configured" for f in findings)
    assert any(f.kind == "Skill" for f in findings)
    assert secret not in repr(findings)
    assert all(f.state != "Aktiv" for f in findings)


def test_activity_ignores_split_control_sequences():
    activity = Activity()
    assert not activity.feed("\x1b[3")
    assert not activity.feed("1m\x1b]0;title")
    assert not activity.feed("\x07\r\n")
    assert activity.feed("Hello 世界")


@pytest.mark.parametrize("agent", ["codex", "claude", "pi"])
def test_native_discovery_with_foreign_path_or_invalid_timestamp(tmp_path, agent):
    from app.agents.sessions import native_sessions

    assert native_sessions(agent, str(tmp_path / "missing"), "2026-10-26T10:00:00Z") == set()
    assert native_sessions(agent, str(tmp_path), "invalid timestamp") == set()


@pytest.mark.parametrize("agent", ["codex", "claude", "pi"])
def test_malformed_local_histories_are_optional(tmp_path, monkeypatch, agent):
    from app.agents.sessions import native_sessions

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    root = tmp_path / ("projects" if agent == "claude" else "sessions") / "project"
    root.mkdir(parents=True)
    for index, content in enumerate(['[]', '{"payload":[]}', '{broken', '{"cwd":42}']):
        (root / f"bad-{index}.jsonl").write_text(content + "\n")
    assert native_sessions(agent, str(tmp_path), "2026-10-26T10:00:00Z") == set()
