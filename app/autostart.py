"""Per-user login startup; never requires administrator privileges."""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "de.getitdone.notebook"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command():
    if getattr(sys, "frozen", False):
        return [sys.executable]
    executable = Path(sys.executable)
    if sys.platform == "win32" and executable.with_name("pythonw.exe").exists():
        executable = executable.with_name("pythonw.exe")
    return [str(executable), "-m", "app"]


def enabled():
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return bool(winreg.QueryValueEx(key, "GetItDone")[0])
        except FileNotFoundError:
            return False
    if sys.platform == "darwin":
        return (Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")).exists()
    return (Path.home() / ".config/autostart/getitdone.desktop").exists()


def set_enabled(value):
    command = launch_command()
    if sys.platform == "win32":
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if value:
                winreg.SetValueEx(key, "GetItDone", 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try:
                    winreg.DeleteValue(key, "GetItDone")
                except FileNotFoundError:
                    pass
        return
    if sys.platform == "darwin":
        path = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
        content = plistlib.dumps(
            {
                "Label": LABEL,
                "ProgramArguments": command,
                "RunAtLoad": True,
                "WorkingDirectory": str(Path(__file__).resolve().parents[1]),
            }
        )
    else:
        path = Path.home() / ".config/autostart/getitdone.desktop"
        # Desktop Exec has its own quoting, not shell quoting.
        quoted = [
            '"'
            + arg.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("`", "\\`")
            .replace("$", "\\$")
            .replace("%", "%%")
            + '"'
            for arg in command
        ]
        content = (
            "[Desktop Entry]\nType=Application\nName=GetItDone\nExec="
            + " ".join(quoted)
            + "\nPath="
            + str(Path(__file__).resolve().parents[1])
            + "\n"
        ).encode()
    if value:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_bytes(content)
        os.replace(temp, path)
    else:
        path.unlink(missing_ok=True)
