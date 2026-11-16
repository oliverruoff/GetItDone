import subprocess
import sys

import pytest
from PySide6.QtWidgets import QDialog

from app import autostart
from app.models import empty_data, now_iso, uid
from app.storage import StorageError, validate
from app.ui.dialogs import SettingsDialog


def test_source_startup_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    command = autostart.launch_command()
    assert command[1] == "-c"
    result = subprocess.run([*command, "--version"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_frozen_startup_uses_current_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert autostart.launch_command() == [sys.executable]


@pytest.mark.parametrize("initial", [False, True])
def test_startup_settings_save_and_cancel(qtbot, tmp_path, monkeypatch, initial):
    monkeypatch.setattr(autostart, "enabled", lambda: initial)
    calls = []
    monkeypatch.setattr(autostart, "set_enabled", calls.append)
    data = empty_data()
    data["settings"]["default_workdir"] = str(tmp_path)
    dialog = SettingsDialog(data, tmp_path / "notebook.json", "Test")
    qtbot.addWidget(dialog)
    assert dialog.autostart.isChecked() is initial
    dialog.autostart.setChecked(not initial)
    dialog.reject()
    assert calls == []
    dialog.check()
    assert dialog.result() == QDialog.Accepted
    assert calls == [not initial]


def test_startup_registration_failure_keeps_settings_open(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "enabled", lambda: False)

    def fail(value):
        raise OSError("Startup access denied")

    monkeypatch.setattr(autostart, "set_enabled", fail)
    errors = []
    monkeypatch.setattr("app.ui.dialogs.error", lambda parent, exc: errors.append(str(exc)))
    data = empty_data()
    data["settings"]["default_workdir"] = str(tmp_path)
    dialog = SettingsDialog(data, tmp_path / "notebook.json", "Test")
    qtbot.addWidget(dialog)
    dialog.autostart.setChecked(True)
    dialog.check()
    assert dialog.result() != QDialog.Accepted
    assert errors == ["Startup access denied"]


def test_standalone_validation_still_rejects_broken_task_links():
    data = empty_data()
    session = dict(id=uid(), item_id=None, agent="codex", title="Ad-hoc",
                   workdir="", native_session_id=None, created_at=now_iso())
    data["sessions"].append(session)
    assert validate(data) is data
    session["item_id"] = "missing-task"
    with pytest.raises(StorageError, match="Invalid session link"):
        validate(data)
    del session["item_id"]
    with pytest.raises(StorageError, match="Invalid session link"):
        validate(data)
    session["item_id"] = None
    session["agents_hidden"] = "yes"
    with pytest.raises(StorageError, match="sidebar state"):
        validate(data)
