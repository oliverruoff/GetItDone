"""OpenCode v2 status from its API, never inferred from terminal repaint activity."""

import json
import os
import subprocess

from app.agents.base import executable_path


def opencode_snapshot(session_ids):
    executable = executable_path("opencode")
    if not executable:
        raise ValueError("OpenCode is unavailable.")

    def request(operation, *params):
        result = subprocess.run(
            [executable, "api", operation, *params],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if result.returncode:
            raise ValueError("OpenCode status is currently unavailable.")
        return json.loads(result.stdout)["data"]

    active = request("session.active")
    snapshots = {}
    for session_id in session_ids:
        try:
            messages = request(
                "session.message.list",
                "--param",
                f"sessionID={session_id}",
                "--param",
                "limit=20",
                "--param",
                "order=desc",
            )
            assistant = next(
                (m for m in messages if m.get("type") == "assistant" and m.get("time", {}).get("completed")),
                None,
            )
            idle = next((m for m in messages if m.get("type") == "idle"), None)
            snapshots[session_id] = {
                "busy": session_id in active,
                "message": assistant["id"] if assistant else None,
                "failed": bool(idle and idle.get("outcome") not in (None, "succeeded")),
            }
        except (ValueError, KeyError, TypeError, subprocess.SubprocessError):
            # A new TUI may not have created its session on the server yet.
            snapshots[session_id] = None
    return snapshots
