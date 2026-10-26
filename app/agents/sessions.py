"""Read native Codex IDs scoped to CLI sessions and an exact working directory."""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


def codex_sessions(workdir, started_at=None):
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    cwd = str(Path(workdir).resolve())
    start = datetime.fromisoformat(started_at).timestamp() if started_at else None
    result = set()

    def matches(created):
        return start is None or start - 2 <= created <= start + 120

    for database in root.glob("state_*.sqlite"):
        try:
            connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.1)
            try:
                for ident, created in connection.execute(
                    "SELECT id, created_at FROM threads WHERE cwd = ? AND source = 'cli'", (cwd,)
                ):
                    if matches(created):
                        result.add(ident)
            finally:
                connection.close()
        except sqlite3.Error:
            continue
    for path in (root / "sessions").glob("**/*.jsonl"):
        try:
            with path.open() as stream:
                meta = json.loads(stream.readline())
            payload = meta.get("payload", {})
            if (
                meta.get("type") == "session_meta"
                and str(Path(payload.get("cwd", "")).resolve()) == cwd
                and payload.get("source") == "cli"
                and matches(datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00")).timestamp())
            ):
                result.add(payload["id"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return result


def native_sessions(agent, workdir, started_at):
    if agent == "codex":
        return codex_sessions(workdir, started_at)
    start = datetime.fromisoformat(started_at).timestamp()
    cwd = Path(workdir).resolve()
    if agent == "claude":
        root = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "projects"
    elif agent == "pi":
        root = Path(os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi/agent"))) / "sessions"
    else:
        return set()
    result = set()
    for path in root.glob("*/*.jsonl"):
        try:
            with path.open() as stream:
                for _, line in zip(range(20), stream):
                    entry = json.loads(line)
                    if Path(entry.get("cwd", "")).resolve() != cwd or not entry.get("timestamp"):
                        continue
                    created = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).timestamp()
                    if start - 2 <= created <= start + 120:
                        ident = entry.get("sessionId") if agent == "claude" else entry.get("id")
                        if ident and (agent == "claude" or entry.get("type") == "session"):
                            result.add(ident)
                    break
        except (OSError, ValueError, TypeError):
            continue
    return result
