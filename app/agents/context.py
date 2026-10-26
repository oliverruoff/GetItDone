"""Read local agent context without exposing MCP credentials or executing their commands."""

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Finding:
    kind: str
    name: str
    path: str
    scope: str
    state: str = "Available"
    content: str = field(default="", repr=False)


def jsonc(text):
    # Match strings first so https:// and comment characters inside strings survive.
    text = re.sub(
        r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/', lambda m: m[0] if m[0].startswith('"') else " ", text
    )
    text = re.sub(r'"(?:\\.|[^"\\])*"|,\s*(?=[}\]])', lambda m: m[0] if m[0].startswith('"') else "", text)
    return json.loads(text)


def discover(agent, workdir, home=None):
    home = Path(home) if home else Path.home()
    workdir = Path(workdir).resolve()
    roots = [workdir]
    for parent in workdir.parents:
        if agent == "codex" and (roots[-1] / ".git").exists():
            break
        roots.append(parent)
    if not any((p / ".git").exists() for p in roots) and agent == "codex":
        roots = [workdir]
    roots.reverse()
    findings, seen = [], set()

    def add(kind, path, scope, state="Available", name=None, content=None):
        path = Path(path)
        key = (kind, str(path), name)
        if key in seen or not path.is_file():
            return
        seen.add(key)
        if content is None:
            try:
                content = path.read_text(errors="replace") if kind != "MCP" else ""
                if len(content) > 65536:
                    content = content[:65536] + "\n\n[Preview truncated at 64 KiB]"
            except OSError:
                content = "This file cannot be read."
        findings.append(Finding(kind, name or path.name, str(path), scope, state, content))

    def instructions(root, names, scope, first=False):
        selected = False
        for name in names:
            path = root / name
            if path.is_file():
                add(
                    "Instructions",
                    path,
                    scope,
                    "Overridden" if first and selected else "Applies on next session start",
                )
                selected = selected or bool(path.stat().st_size)

    def skills(root, scope):
        if root.is_dir():
            for index, path in enumerate(root.rglob("SKILL.md")):
                if index >= 1000:
                    break
                add("Skill", path, scope, name=path.parent.name)

    def config(path, scope, key):
        if not path.is_file():
            return {}
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError()
            text = path.read_text()
            data = tomllib.loads(text) if path.suffix == ".toml" else jsonc(text)
            for name, value in data.get(key, {}).items():
                disabled = isinstance(value, dict) and (
                    value.get("enabled") is False or value.get("disabled") is True
                )
                add(
                    "MCP",
                    path,
                    scope,
                    "Disabled" if disabled else "Configured",
                    str(name),
                    "Connection and authentication have not been verified. Server commands, URLs and credentials are hidden.",
                )
            return data
        except (OSError, ValueError, TypeError, AttributeError):
            findings.append(Finding("Notice", "Configuration could not be read", str(path), scope, "Unknown"))
            return {}

    if agent == "codex":
        base = Path(os.environ.get("CODEX_HOME", str(home / ".codex")))
        instructions(base, ["AGENTS.override.md", "AGENTS.md"], "Global · Codex", True)
        settings = config(base / "config.toml", "Global · Codex", "mcp_servers")
        skills(home / ".agents/skills", "Global · Shared")
        skills(base / "skills", "Global · Codex")
        for root in roots:
            scope = "Project" if root == workdir else "Inherited"
            instructions(
                root,
                ["AGENTS.override.md", "AGENTS.md", *settings.get("project_doc_fallback_filenames", [])],
                scope,
                True,
            )
            skills(root / ".agents/skills", scope + " · Shared")
            config(root / ".codex/config.toml", scope + " · Requires project trust", "mcp_servers")
    elif agent == "claude":
        base = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
        instructions(base, ["CLAUDE.md"], "Global · Claude")
        config(home / ".claude.json", "Global · Claude", "mcpServers")
        skills(base / "skills", "Global · Claude")
        for root in roots:
            scope = "Project" if root == workdir else "Inherited"
            instructions(root, ["CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"], scope)
            for path in (root / ".claude/rules").glob("**/*.md"):
                add("Instructions", path, scope, "Conditional rule · depends on file paths")
            config(root / ".mcp.json", scope, "mcpServers")
            skills(root / ".claude/skills", scope)
    elif agent == "opencode":
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "opencode"
        instructions(base, ["AGENTS.md"], "Global · OpenCode")
        skills(base / "skills", "Global · OpenCode")
        for root, scope in [
            (base, "Global · OpenCode"),
            *[(p, "Project" if p == workdir else "Inherited") for p in roots],
        ]:
            if root != base:
                instructions(root, ["AGENTS.md"], scope + " · Shared")
                skills(root / ".opencode/skills", scope)
            for name in ["opencode.json", "opencode.jsonc"]:
                data = config(root / name, scope, "mcp")
                for pattern in data.get("instructions", []):
                    if isinstance(pattern, str) and not pattern.startswith(("https:", "http:")):
                        for path in (
                            root.glob(pattern) if not Path(pattern).is_absolute() else [Path(pattern)]
                        ):
                            add("Instructions", path, scope, "Configured instruction file")
    elif agent == "pi":
        base = Path(os.environ.get("PI_CODING_AGENT_DIR", str(home / ".pi/agent")))
        instructions(base, ["AGENTS.md", "AGENTS.MD", "CLAUDE.md", "CLAUDE.MD"], "Global · Pi", True)
        instructions(base, ["SYSTEM.md", "APPEND_SYSTEM.md"], "Global · Pi")
        skills(base / "skills", "Global · Pi")
        config(base / "mcp.json", "Global · Pi · version dependent", "mcpServers")
        for root in roots:
            scope = "Project" if root == workdir else "Inherited"
            instructions(root, ["AGENTS.md", "AGENTS.MD", "CLAUDE.md", "CLAUDE.MD"], scope, True)
            if root == workdir:
                instructions(
                    root, [".pi/SYSTEM.md", ".pi/APPEND_SYSTEM.md"], scope + " · Requires project trust"
                )
                skills(root / ".pi/skills", scope)
    else:
        findings.append(
            Finding("Notice", "Custom profile: context discovery is unavailable", "", "", "Unknown")
        )
    return datetime.now().astimezone().isoformat(timespec="seconds"), findings


def codex_skills(workdir):
    """Ask Codex for its registered skill metadata, without starting a turn."""
    import queue
    import subprocess
    import threading

    from app.agents.base import executable_path

    process = subprocess.Popen(
        [executable_path("codex"), "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    responses = queue.Queue()

    def read():
        for line in process.stdout:
            try:
                responses.put(json.loads(line))
            except ValueError:
                pass
        responses.put({})

    threading.Thread(target=read, daemon=True).start()

    def request(ident, method, params):
        process.stdin.write(json.dumps(dict(id=ident, method=method, params=params)) + "\n")
        process.stdin.flush()
        import time

        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            response = responses.get(timeout=max(0.01, deadline - time.monotonic()))
            if response.get("id") == ident:
                if "error" in response:
                    raise ValueError()
                return response.get("result", {})
        raise ValueError()

    try:
        request(1, "initialize", {"clientInfo": {"name": "getitdone_context", "version": "0.1.0"}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        data = request(2, "skills/list", {"cwds": [str(workdir)], "forceReload": False})
        return [
            Finding(
                "Skill",
                skill["name"],
                skill["path"],
                "Codex · " + str(skill.get("scope", "Registered")),
                "Registered · loads on demand" if skill.get("enabled", True) else "Disabled",
                str(skill.get("description", ""))
                + "\n\n"
                + (
                    Path(skill["path"]).read_text(errors="replace")[:65536]
                    if Path(skill["path"]).is_file()
                    else "Source is unavailable."
                ),
            )
            for group in data.get("data", [])
            for skill in group.get("skills", [])
        ]
    except queue.Empty:
        raise ValueError("Codex context timed out") from None
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdout.close()


def runtime_context(agent, workdir):
    """Optional read-only OpenCode v2 API evidence; never starts an MCP command."""
    import subprocess

    from app.agents.base import executable_path

    stamp, findings = discover(agent, workdir)
    if agent == "codex":
        try:
            registered = codex_skills(workdir)
            # The agent registry includes bundled/plugin skills and its precedence rules.
            findings = [f for f in findings if f.kind != "Skill"] + registered
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            findings.append(
                Finding(
                    "Notice", "Codex skill registry unavailable; showing local sources", "", "", "Unknown"
                )
            )
        return stamp, findings
    if agent != "opencode":
        return stamp, findings
    executable = executable_path("opencode")
    try:
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=4)
        if not version.stdout.strip().startswith("2."):
            return stamp, findings
        for operation, kind in [("skill.list", "Skill"), ("mcp.list", "MCP")]:
            result = subprocess.run(
                [executable, "api", operation, "--param", f"location.directory={workdir}"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            if result.returncode:
                raise ValueError()
            entries = json.loads(result.stdout)["data"]
            if isinstance(entries, dict):
                entries = [
                    dict(value, name=name) for name, value in entries.items() if isinstance(value, dict)
                ]
            for entry in entries:
                name = entry.get("name") or entry.get("id")
                if not name:
                    continue
                status = entry.get("status", {})
                status = status.get("type", "Unknown") if isinstance(status, dict) else str(status)
                state = (
                    "Registered · loads on demand"
                    if kind == "Skill"
                    else str(status).replace("_", " ").capitalize()
                )
                match = next((f for f in findings if f.kind == kind and f.name == name), None)
                if match:
                    match.state = state
                else:
                    findings.append(
                        Finding(
                            kind,
                            str(name),
                            str(entry.get("path", "")),
                            "OpenCode runtime",
                            state,
                            str(entry.get("content") or entry.get("description") or "")
                            if kind == "Skill"
                            else "Status reported by the OpenCode API. Credentials are hidden.",
                        )
                    )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        findings.append(
            Finding("Notice", "Runtime status unavailable; showing local configuration", "", "", "Unknown")
        )
    return stamp, findings
