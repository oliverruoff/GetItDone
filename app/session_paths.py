"""Stable session workspace, independent of Finder's working directory."""

from pathlib import Path


def builtin_session_folder():
    return Path.home() / "Documents" / "GetItDone" / "Sessions"


def session_folder(settings, value=None):
    configured = settings.get("default_workdir", "").strip()
    return Path(
        (value.strip() if value is not None else "") or configured or builtin_session_folder()
    ).expanduser()


def prepare_session_folder(settings, value=None):
    path = session_folder(settings, value)
    if path == builtin_session_folder():
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError("Please select an available working directory.")
    return str(path.resolve())
