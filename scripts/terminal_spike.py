"""Read-only startup probe for installed CLIs; sends no prompts, persists no terminal output."""

import argparse
import json
import os
import threading
import time
from pathlib import Path

from app.agents import agents


def probe(agent, cwd, seconds):
    command = agent.command()
    if os.name == "nt":
        from app.terminal.windows import Process
    else:
        from app.terminal.macos import Process
    process = Process(command, cwd)
    counts = {"bytes": 0, "chunks": 0, "ansi": False, "unicode": False}

    def read():
        try:
            while chunk := process.read():
                counts["bytes"] += len(chunk)
                counts["chunks"] += 1
                counts["ansi"] |= b"\x1b[" in chunk
                counts["unicode"] |= any(c > 127 for c in chunk)
        except (OSError, EOFError):
            pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    time.sleep(seconds)
    running = process.alive()
    errors = []
    if running:
        for phase, action in [
            ("resize", lambda: process.resize(120, 35)),
            ("interrupt", lambda: process.write("\x03")),
        ]:
            try:
                action()
            except OSError as exc:
                errors.append(f"{phase}: {exc}")
        time.sleep(0.3)
    try:
        if process.alive():
            process.terminate()
            time.sleep(0.5)
        process.terminate(force=True)
    except OSError as exc:
        errors.append(f"terminate: {exc}")
    reader.join(3)
    code = process.wait()
    return dict(
        agent=agent.name,
        version=agent.probe(),
        active_after_start=running,
        output=counts,
        exit_code=code,
        resumed=False,
        errors=errors,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default=str(Path.cwd()))
    parser.add_argument("--seconds", type=float, default=2)
    parser.add_argument("--agent", action="append")
    args = parser.parse_args()
    registry = agents({})
    for ident in args.agent or list(registry):
        try:
            result = probe(registry[ident], args.workdir, args.seconds)
        except (ValueError, OSError) as exc:
            result = dict(agent=ident, error=str(exc))
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
