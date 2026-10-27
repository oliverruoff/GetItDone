"""Read assistant text from exact local sessions, without launching an agent."""

import json
import os
import subprocess
import time
from pathlib import Path

_CACHE = {}


def text_content(content):
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return "\n\n".join(
        part["text"]
        for part in content
        if isinstance(part, dict)
        and part.get("type") in ("text", "output_text")
        and isinstance(part.get("text"), str)
    ).strip()


def history_path(session):
    agent, ident = session["agent"], session.get("native_session_id")
    if not ident:
        return None
    roots = {
        "codex": Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions",
        "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "projects",
        "pi": Path(os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi/agent"))) / "sessions",
    }
    if agent not in roots:
        return None
    key = (agent, ident, session["workdir"], str(roots[agent]))
    cached = _CACHE.get(key)
    if cached and time.monotonic() - cached[0] < 30:
        return cached[1]
    paths = [Path(ident)] if agent == "pi" and Path(ident).is_absolute() else roots[agent].glob("**/*.jsonl")
    matches = []
    for path in paths:
        try:
            with path.open() as stream:
                for _, line in zip(range(20), stream):
                    entry = json.loads(line)
                    meta = entry.get("payload", {}) if agent == "codex" else entry
                    native = meta.get("sessionId") if agent == "claude" else meta.get("id")
                    if agent == "pi" and str(path) == ident:
                        native = ident
                    if (
                        native == ident
                        and Path(meta.get("cwd", "")).resolve() == Path(session["workdir"]).resolve()
                    ):
                        matches.append(path)
                        break
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    result = matches[0] if len(matches) == 1 else None
    _CACHE[key] = (time.monotonic(), result)
    return result


def native_snapshot(session):
    path = history_path(session)
    if not path:
        return None
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(max(0, size - 2 * 1024 * 1024))
        if size > 2 * 1024 * 1024:
            stream.readline()
        lines = stream.read().decode("utf-8", errors="replace").splitlines()
    result = {
        "busy": False,
        "failed": False,
        "message": None,
        "output": "",
        "timestamp": "",
        "status_known": session["agent"] == "codex",
    }
    for line in lines:
        try:
            entry = json.loads(line)
            agent = session["agent"]
            content = ""
            if agent == "codex":
                payload = entry.get("payload", {})
                if entry.get("type") == "event_msg":
                    kind = payload.get("type")
                    if kind == "task_started":
                        result["busy"] = True
                    elif kind in ("task_complete", "turn_aborted", "error"):
                        result["busy"] = False
                        result["failed"] = kind == "error"
                        if kind == "task_complete":
                            content = payload.get("last_agent_message") or ""
                    elif kind == "agent_message" and payload.get("phase") != "commentary":
                        content = payload.get("message") or ""
                elif (
                    entry.get("type") == "response_item"
                    and payload.get("role") == "assistant"
                    and payload.get("phase") == "final_answer"
                ):
                    content = text_content(payload.get("content"))
            else:
                message = entry.get("message", {})
                if message.get("role") == "assistant":
                    content = text_content(message.get("content"))
                    result["failed"] = message.get("stopReason") == "error"
            if isinstance(content, str) and content.strip():
                result.update(
                    output=content.strip(),
                    message=entry.get("uuid") or entry.get("id") or entry.get("timestamp") or content,
                    timestamp=entry.get("timestamp") or "",
                )
        except (ValueError, TypeError, AttributeError):
            continue
    return result


def snapshots(sessions):
    from app.agents.status import opencode_snapshot

    results = {}
    opencode = [s["native_session_id"] for s in sessions if s["agent"] == "opencode"]
    if opencode:
        try:
            remote = opencode_snapshot(opencode)
            results.update(
                {s["id"]: remote.get(s["native_session_id"]) for s in sessions if s["agent"] == "opencode"}
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    for session in sessions:
        if session["agent"] != "opencode":
            try:
                results[session["id"]] = native_snapshot(session)
            except (OSError, ValueError, TypeError):
                results[session["id"]] = None
    return results
