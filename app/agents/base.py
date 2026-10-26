"""CLI commands are argument lists. We never guess which native session is newest."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def executable_path(name):
    found = shutil.which(os.path.expanduser(name))
    if found:
        return found
    # GUI apps started by Finder do not inherit interactive shell PATH.
    roots = [
        Path.home() / ".local/bin",
        Path.home() / ".npm-global/bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ]
    if name == "codex":
        bundled = Path(
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
        )
        if bundled.is_file() and os.access(bundled, os.X_OK):
            return str(bundled)
    if os.name == "nt":
        roots += [Path(os.environ.get("APPDATA", "")) / "npm"]
    for root in roots:
        for suffix in ("", ".exe", ".cmd") if os.name == "nt" else ("",):
            path = root / (name + suffix)
            if path.is_file() and (os.name == "nt" or os.access(path, os.X_OK)):
                return str(path)
    return None


@dataclass
class Agent:
    id: str
    name: str
    executable: str
    args: tuple = ()
    resume_args: tuple = ()

    def command(self, native_id=None):
        executable = executable_path(self.executable)
        if not executable:
            raise ValueError(
                f"{self.name} was not found. Install the CLI or specify its executable in a custom profile."
            )
        args = list(self.args)
        if native_id:
            if not self.resume_args:
                raise ValueError("This profile does not support automatic resume.")
            if native_id.startswith("-") or any(ord(c) < 32 for c in native_id):
                raise ValueError("Invalid native session ID.")
            args += [native_id if a == "{id}" else a for a in self.resume_args]
        return [executable, *args]

    def probe(self):
        executable = executable_path(self.executable)
        if not executable:
            return "Not installed / not on PATH"
        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=4,
                errors="replace",
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            return (result.stdout or result.stderr).strip()[:180] or "Unknown version"
        except (OSError, subprocess.TimeoutExpired):
            return "Installed · Unable to determine version"

    def context(self, workdir):
        from app.agents.context import runtime_context

        return runtime_context(self.id, Path(workdir))

    @property
    def capabilities(self):
        return (
            (
                "New sessions receive a fixed native ID; Resume reopens that conversation."
                if self.id in ("claude", "pi")
                else "Native IDs are read from local CLI session metadata for Resume."
                if self.id == "codex"
                else "Resume uses the saved native session ID."
            )
            if self.resume_args
            else "Custom profile: terminal and clipboard. Resume and context discovery are unavailable."
        )
