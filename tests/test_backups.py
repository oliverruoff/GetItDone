import copy
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.backups import (
    BackupScheduler,
    backup_defaults,
    check_destination,
    configure_backup,
    create_backup,
    default_backup_folder,
)
from app.models import Notebook
from app.storage import StorageError, Store, validate
from app.ui.backup_settings import BackupSettings


@pytest.fixture(autouse=True)
def deterministic_zone(monkeypatch):
    monkeypatch.setattr("app.backups.local_zone", lambda: timezone.utc)


def configured(tmp_path, now=None):
    now = now or datetime(2026, 11, 6, 18, tzinfo=timezone.utc)
    book = Notebook()
    book.data["settings"]["backups"] = configure_backup(
        {}, enabled=True, time="18:00", every=1, unit="days", folder=str(tmp_path / "backups"), now=now,
    )
    return book, now


def test_first_time_interval_changes_and_disabled_schedule(tmp_path):
    now = datetime(2026, 11, 6, 19, tzinfo=timezone.utc)
    book, _ = configured(tmp_path, now)
    config = book.data["settings"]["backups"]
    assert config["next_at"] == "2026-11-07T18:00:00+00:00"
    config["next_at"] = "2026-11-01T18:00:00+00:00"
    unchanged = configure_backup(config, **{k: config[k] for k in
                                           ("enabled", "time", "every", "unit", "folder")}, now=now)
    assert unchanged == config  # Do not discard a missed occurrence when saving other settings.
    disabled = configure_backup(config, enabled=False, time="18:00", every=1,
                                unit="days", folder=config["folder"], now=now)
    assert disabled["next_at"] is None


@pytest.mark.parametrize("key,value", [("enabled", 1), ("time", "24:00"), ("time", "1:00"),
                                     ("every", 0), ("every", True), ("unit", "hours"),
                                     ("next_at", "2026-11-06T18:00:00"), ("last_at", 1), ("folder", None)])
def test_invalid_backup_settings_are_rejected(tmp_path, key, value):
    book, _ = configured(tmp_path)
    book.data["settings"]["backups"][key] = value
    with pytest.raises(StorageError):
        validate(book.data)


def test_old_notebook_without_backup_settings_remains_valid():
    assert validate(Notebook().data)


def test_complete_zip_roundtrip_and_unique_names(tmp_path):
    book, now = configured(tmp_path)
    parent = book.add("Todo ä")
    child = book.add("Completed child", parent["id"])
    book.update(child["id"], notes="All notes", done=True)
    category = {"id": "category", "name": "Important", "color": "#ffccaa"}
    book.data["categories"].append(category)
    book.update(parent["id"], category_id=category["id"], reminder={"at": now.isoformat()})
    book.data["sessions"].append(dict(
        id="session", item_id=parent["id"], agent="codex", native_session_id="native-id",
        workdir=str(tmp_path), title="Saved session", created_at=now.isoformat(),
        last_reply={"text": "Saved reply", "saved_at": now.isoformat()}, reply_unread=True,
        process_runs=[dict(id="process", started_at=now.isoformat(), finished_at=now.isoformat(),
                           status="completed", last_reply={"text": "Execution reply"})],
    ))
    book.data["scheduled_jobs"] = [dict(
        id="job", title="Recurring job", prompt="Do work", agent="codex", workdir=str(tmp_path),
        enabled=True, every=1, unit="days", next_at=now.isoformat(), runs=[],
    )]
    book.data["settings"]["custom_setting"] = {"nested": [1, 2, 3]}
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "nested").mkdir()
    (knowledge / "empty").mkdir()
    (knowledge / "nested" / "document.bin").write_bytes(b"\x00\xff")
    (knowledge / "Note ä.md").write_text("# Knowledge", encoding="utf-8")
    book.data["settings"]["knowledge_folder"] = str(knowledge)
    original = copy.deepcopy(book.data)
    data_folder = tmp_path / "data"
    store = Store(data_folder)
    store.load()
    store.save(book.data)
    first = create_backup(book.data, data_folder, now)
    second = create_backup(book.data, data_folder, now)
    assert first != second
    assert book.data == original
    with zipfile.ZipFile(first) as archive:
        assert json.loads(archive.read("notebook.json")) == book.data
        assert archive.read("knowledge/nested/document.bin") == b"\x00\xff"
        assert archive.read("knowledge/Note ä.md").decode() == "# Knowledge"
        assert "knowledge/empty/" in archive.namelist()
        assert "RESTORE.txt" in archive.namelist()
        restored_folder = tmp_path / "restored"
        restored_folder.mkdir()
        archive.extract("notebook.json", restored_folder)
    assert Store(restored_folder).load() == original
    assert not list((tmp_path / "backups").glob("*.tmp"))


def test_unavailable_knowledge_fails_without_partial_backup(tmp_path):
    book, now = configured(tmp_path)
    book.data["settings"]["knowledge_folder"] = str(tmp_path / "missing")
    with pytest.raises(OSError, match="knowledge folder is unavailable"):
        create_backup(book.data, tmp_path / "data", now)
    assert not list((tmp_path / "backups").iterdir())


@pytest.mark.parametrize("source", ["data", "knowledge"])
def test_destination_must_not_be_inside_sources(tmp_path, source):
    with pytest.raises(ValueError, match="outside"):
        check_destination(str(tmp_path / source / "backups"), tmp_path / "data", str(tmp_path / "knowledge"))


def test_write_failure_preserves_older_archive(tmp_path, monkeypatch):
    book, now = configured(tmp_path)
    first = create_backup(book.data, tmp_path / "data", now)

    def fail(*args, **kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr(zipfile.ZipFile, "writestr", fail)
    with pytest.raises(OSError, match="Disk full"):
        create_backup(book.data, tmp_path / "data", now)
    assert [str(p) for p in (tmp_path / "backups").iterdir()] == [first]


def scheduler_for(book, tmp_path, prepare=lambda: True):
    workers = []
    persisted = []
    scheduler = BackupScheduler(book, tmp_path / "data", prepare,
                                lambda: persisted.append(copy.deepcopy(book.data)) or True,
                                lambda function, callback: workers.append((function, callback)))
    return scheduler, workers, persisted


def test_scheduler_exact_time_catchup_restart_and_disabled(tmp_path):
    book, now = configured(tmp_path)
    scheduler, workers, persisted = scheduler_for(book, tmp_path)
    scheduler.tick(now - timedelta(seconds=1))
    assert not workers
    scheduler.tick(now)
    assert scheduler.active and len(workers) == 1
    scheduler.tick(now + timedelta(days=3))
    assert len(workers) == 1  # No parallel runs.
    function, callback = workers.pop()
    path = function()
    callback(path, None)
    assert not scheduler.active
    assert persisted[-1]["settings"]["backups"]["next_at"] == (now + timedelta(days=1)).isoformat()
    restarted, workers, _ = scheduler_for(Notebook(copy.deepcopy(book.data)), tmp_path)
    restarted.tick(now + timedelta(minutes=1))
    assert not workers
    restarted.tick(now + timedelta(days=4, minutes=1))
    function, callback = workers.pop()
    callback(function(), None)
    assert restarted.notebook.data["settings"]["backups"]["next_at"] == (now + timedelta(days=5)).isoformat()
    restarted.notebook.data["settings"]["backups"]["enabled"] = False
    restarted.tick(now + timedelta(days=10))
    assert not workers


def test_failure_retries_and_does_not_advance_schedule(tmp_path):
    book, now = configured(tmp_path)
    scheduler, workers, _ = scheduler_for(book, tmp_path)
    completed = []
    scheduler.completed.connect(completed.append)
    scheduler.tick(now)
    _, callback = workers.pop()
    callback(None, OSError("Network drive unavailable"))
    assert completed == []
    config = book.data["settings"]["backups"]
    assert config["next_at"] == now.isoformat()
    assert "Network drive" in config["last_error"]
    assert config["last_at"] is None
    scheduler.tick(now + timedelta(minutes=4))
    assert not workers
    scheduler.tick(now + timedelta(minutes=5))
    assert len(workers) == 1


def test_unsaved_edits_prevent_backup(tmp_path):
    book, now = configured(tmp_path)
    scheduler, workers, _ = scheduler_for(book, tmp_path, prepare=lambda: False)
    scheduler.tick(now)
    assert not workers
    assert "could not be saved" in book.data["settings"]["backups"]["last_error"]
    assert book.data["settings"]["backups"]["next_at"] == now.isoformat()


def test_changed_settings_during_worker_are_not_overwritten(tmp_path):
    book, now = configured(tmp_path)
    scheduler, workers, _ = scheduler_for(book, tmp_path)
    scheduler.tick(now)
    config = book.data["settings"]["backups"]
    config.update(enabled=False, next_at=None)
    function, callback = workers.pop()
    callback(function(), None)
    assert config["enabled"] is False and config["next_at"] is None
    assert config["last_file"]


@pytest.mark.parametrize("every,unit,start,expected", [
    (2, "days", "2026-03-28T18:00:00", "2026-03-30T18:00:00+02:00"),
    (1, "weeks", "2026-03-28T18:00:00", "2026-04-04T18:00:00+02:00"),
    (1, "months", "2026-01-31T18:00:00", "2026-02-28T18:00:00+01:00"),
])
def test_calendar_intervals_and_dst(tmp_path, monkeypatch, every, unit, start, expected):
    zone = ZoneInfo("Europe/Berlin")
    monkeypatch.setattr("app.backups.local_zone", lambda: zone)
    now = datetime.fromisoformat(start).replace(tzinfo=zone)
    book, _ = configured(tmp_path, now)
    book.data["settings"]["backups"].update(every=every, unit=unit)
    scheduler, workers, _ = scheduler_for(book, tmp_path)
    scheduler.tick(now)
    function, callback = workers.pop()
    callback(function(), None)
    assert book.data["settings"]["backups"]["next_at"] == expected


def test_nonexistent_dst_time_does_not_shift_future_backups(tmp_path, monkeypatch):
    zone = ZoneInfo("Europe/Berlin")
    monkeypatch.setattr("app.backups.local_zone", lambda: zone)
    book, _ = configured(tmp_path)
    config = book.data["settings"]["backups"]
    config.update(time="02:30", next_at="2026-03-29T02:30:00+01:00")
    scheduler, workers, _ = scheduler_for(book, tmp_path)
    scheduler.tick(datetime(2026, 3, 29, 3, 15, tzinfo=zone))
    assert not workers
    scheduler.tick(datetime(2026, 3, 29, 3, 30, tzinfo=zone))
    function, callback = workers.pop()
    callback(function(), None)
    assert config["next_at"] == "2026-03-30T02:30:00+02:00"


def test_repeated_dst_time_runs_once(tmp_path, monkeypatch):
    zone = ZoneInfo("Europe/Berlin")
    monkeypatch.setattr("app.backups.local_zone", lambda: zone)
    book, _ = configured(tmp_path)
    config = book.data["settings"]["backups"]
    config.update(time="02:30", next_at="2026-10-25T02:30:00+02:00")
    scheduler, workers, _ = scheduler_for(book, tmp_path)
    scheduler.tick(datetime(2026, 10, 25, 2, 30, tzinfo=zone))
    function, callback = workers.pop()
    callback(function(), None)
    scheduler.tick(datetime(2026, 10, 25, 2, 30, tzinfo=zone, fold=1))
    assert not workers
    assert config["next_at"] == "2026-10-26T02:30:00+01:00"


def test_backup_settings_ui_and_runtime_status_are_preserved(qtbot, tmp_path):
    settings = {}
    widget = BackupSettings(settings, tmp_path / "data")
    qtbot.addWidget(widget)
    assert not widget.enabled.isChecked()
    assert not widget.time.isEnabled()
    assert widget.value() == backup_defaults()
    widget.enabled.setChecked(True)
    widget.folder.setText(str(tmp_path / "backups"))
    widget.every.setValue(2)
    widget.unit.setCurrentIndex(widget.unit.findData("weeks"))
    value = widget.value()
    assert value["enabled"] and value["every"] == 2 and value["unit"] == "weeks"
    settings["backups"] = value
    settings["backups"].update(last_file="new-backup.zip", last_at="2026-11-06T18:00:00+00:00")
    assert widget.value()["last_file"] == "new-backup.zip"
    widget.refresh_status()
    assert "new-backup.zip" in widget.status.text()


def test_settings_dialog_saves_backups_and_preserves_unrelated_settings(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from app.ui.dialogs import SettingsDialog

    monkeypatch.setattr("app.autostart.enabled", lambda: False)
    book = Notebook()
    book.data["settings"].update(default_workdir=str(tmp_path), custom_setting="Keep this")
    dialog = SettingsDialog(book.data, tmp_path / "data" / "notebook.json", "Test status")
    qtbot.addWidget(dialog)
    dialog.backups.enabled.setChecked(True)
    dialog.backups.folder.setText(str(tmp_path / "backups"))
    dialog.backups.every.setValue(3)
    dialog.check()
    assert dialog.result() == QDialog.DialogCode.Accepted
    config = dialog.settings["backups"]
    assert config["enabled"] and config["every"] == 3 and config["next_at"]
    assert dialog.settings["custom_setting"] == "Keep this"
    assert "backups" not in book.data["settings"]  # Changes apply only after the owner accepts.


def test_window_runs_real_background_backup_of_current_notes(qtbot, tmp_path, monkeypatch):
    from app.ui.window import Window

    store = Store(tmp_path / "data")
    data = store.load()
    book, now = configured(tmp_path, datetime.now(timezone.utc) - timedelta(days=1))
    data["settings"]["backups"] = book.data["settings"]["backups"]
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "Note.txt").write_text("Old text")
    data["settings"]["knowledge_folder"] = str(knowledge)
    window = Window(store, data)
    qtbot.addWidget(window)
    notifications = []
    monkeypatch.setattr(window.notifier, "send", notifications.append)
    window.timer.stop()
    window.show()
    qtbot.waitUntil(lambda: window.knowledge.files.count() > 0)
    window.knowledge.files.setCurrentRow(0)
    qtbot.waitUntil(lambda: window.knowledge.document is not None)
    window.knowledge.editor.setPlainText("Latest unsaved text ä")
    window.notebook.add("Newest task")
    window.backups.tick()
    qtbot.waitUntil(lambda: not window.backups.active, timeout=10000)
    config = data["settings"]["backups"]
    assert config["last_file"], config["last_error"]
    with zipfile.ZipFile(config["last_file"]) as archive:
        assert archive.read("knowledge/Note.txt").decode() == "Latest unsaved text ä"
        assert json.loads(archive.read("notebook.json"))["items"][0]["text"] == "Newest task"
    assert Store(store.folder).load()["settings"]["backups"]["last_file"] == config["last_file"]
    assert len(notifications) == 1
    assert notifications[0]["notification_title"] == "GetItDone · Backup"
    assert notifications[0]["text"] == "Backup created successfully."
    window.tray.hide()
    window.quitting = True


def test_default_folder_is_in_documents_and_created_on_first_backup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backups.QStandardPaths.writableLocation", lambda location: str(tmp_path / "Documents"))
    expected = tmp_path / "Documents" / "GetItDone" / "Backups"
    assert default_backup_folder() == expected
    assert backup_defaults()["folder"] == str(expected)
    assert not expected.exists()
    book = Notebook()
    scheduler, workers, _ = scheduler_for(book, tmp_path)
    assert scheduler.backup_now(str(expected))
    function, callback = workers.pop()
    callback(function(), None)
    assert expected.is_dir()
    assert len(list(expected.glob("*.zip"))) == 1
    assert book.data["settings"]["backups"]["enabled"] is False


@pytest.mark.parametrize("manual", [True, False])
def test_successful_backup_notifies_while_window_is_hidden(qtbot, tmp_path, monkeypatch, manual):
    from app.ui.window import Window

    store = Store(tmp_path / "data")
    store.load()
    book, now = configured(tmp_path)
    book.data["settings"]["backups"]["enabled"] = not manual
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.timer.stop()
    notifications = []
    monkeypatch.setattr(window.notifier, "send", notifications.append)
    try:
        assert not window.isVisible()
        if manual:
            window.backups.backup_now(str(tmp_path / "backups"), now)
        else:
            window.backups.tick(now)
        assert notifications == []
        qtbot.waitUntil(lambda: not window.backups.active, timeout=10000)
        assert Path(book.data["settings"]["backups"]["last_file"]).is_file()
        assert notifications == [{
            "id": "", "text": "Backup created successfully.", "notification_title": "GetItDone · Backup",
        }]
        assert not window.isVisible()
    finally:
        window.timer.stop()
        window.tray.hide()
        window.quitting = True


@pytest.mark.parametrize("folder", ["", "custom"])
def test_backup_folder_defaults_only_for_empty_destinations(qtbot, tmp_path, monkeypatch, folder):
    default = tmp_path / "Documents" / "GetItDone" / "Backups"
    monkeypatch.setattr("app.backups.default_backup_folder", lambda: default)
    custom = str(tmp_path / "custom") if folder else ""
    widget = BackupSettings({"backups": {"folder": custom}}, tmp_path / "data")
    qtbot.addWidget(widget)
    assert widget.folder.text() == (custom or str(default))
    assert not default.exists()


@pytest.mark.parametrize("enabled", [True, False])
def test_manual_backup_uses_selected_folder_without_changing_schedule(tmp_path, enabled):
    book, now = configured(tmp_path)
    config = book.data["settings"]["backups"]
    config["enabled"] = enabled
    original_schedule = {k: config[k] for k in ("enabled", "time", "every", "unit", "folder", "next_at")}
    scheduler, workers, persisted = scheduler_for(book, tmp_path)
    completed = []
    scheduler.completed.connect(completed.append)
    selected = tmp_path / "manually selected"
    assert scheduler.backup_now(str(selected), now)
    assert completed == []
    assert not scheduler.backup_now(str(selected), now)  # Double clicks cannot create parallel backups.
    function, callback = workers.pop()
    file = function()
    callback(file, None)
    assert completed == [file]
    assert {k: config[k] for k in original_schedule} == original_schedule
    assert config["last_file"] == file
    assert persisted[-1]["settings"]["backups"]["last_at"] == now.isoformat()
    assert Path(file).parent == selected
    with zipfile.ZipFile(file) as archive:
        snapshot = json.loads(archive.read("notebook.json"))["settings"]["backups"]
        assert snapshot["folder"] == str(selected.resolve())
        assert snapshot["next_at"] == original_schedule["next_at"]
        assert snapshot["enabled"] is enabled


def test_manual_backup_failure_does_not_enable_or_retry_automatic_backups(tmp_path):
    book = Notebook()
    scheduler, workers, _ = scheduler_for(book, tmp_path)
    messages = []
    scheduler.status.connect(messages.append)
    assert scheduler.backup_now(str(tmp_path / "backups"))
    _, callback = workers.pop()
    callback(None, OSError("Disk full"))
    config = book.data["settings"]["backups"]
    assert not config["enabled"] and config["next_at"] is None
    assert config["last_file"] == "" and config["last_error"] == "Disk full"
    assert scheduler.retry_at is None
    assert messages[-1] == "Backup failed: Disk full"
    scheduler.tick(datetime.now(timezone.utc) + timedelta(minutes=10))
    assert not workers


def test_manual_backup_blocks_unsaved_edits_and_invalid_destination(tmp_path):
    book = Notebook()
    scheduler, workers, _ = scheduler_for(book, tmp_path, prepare=lambda: False)
    assert not scheduler.backup_now(str(tmp_path / "backups"))
    assert not workers and not scheduler.active
    with pytest.raises(ValueError, match="outside"):
        scheduler.backup_now(str(tmp_path / "data" / "backups"))
    assert not workers


def test_backup_now_button_uses_unsaved_folder_with_automatic_backups_disabled(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QTabWidget

    from app.ui.dialogs import SettingsDialog
    from app.ui.window import Window

    monkeypatch.setattr("app.autostart.enabled", lambda: False)
    monkeypatch.setattr("app.backups.default_backup_folder", lambda: tmp_path / "Documents" / "GetItDone" / "Backups")
    store = Store(tmp_path / "data")
    window = Window(store, store.load())
    qtbot.addWidget(window)
    window.timer.stop()
    window.notebook.add("Task in manual backup")
    dialog = SettingsDialog(window.notebook.data, store.path, "Test", window)
    qtbot.addWidget(dialog)
    dialog.findChild(QTabWidget).setCurrentIndex(1)
    dialog.show()
    widget = dialog.backups
    assert not widget.enabled.isChecked()
    assert widget.folder.text() == backup_defaults()["folder"]
    assert widget.folder.isEnabled() and widget.choose.isEnabled()
    assert widget.backup_now_button.isEnabled()
    selected = tmp_path / "unsaved destination"
    widget.folder.setText(str(selected))
    widget.backup_now_button.click()
    assert not widget.backup_now_button.isEnabled()
    qtbot.waitUntil(lambda: not window.backups.active, timeout=10000)
    assert widget.backup_now_button.isEnabled()
    assert len(list(selected.glob("*.zip"))) == 1
    config = window.notebook.data["settings"]["backups"]
    assert not config["enabled"] and config["folder"] == backup_defaults()["folder"]
    assert config["last_file"] in widget.status.text()
    dialog.reject()  # Cancel does not undo the explicitly requested backup or apply other settings.
    assert Store(store.folder).load()["settings"]["backups"]["last_file"] == config["last_file"]
    with zipfile.ZipFile(config["last_file"]) as archive:
        assert json.loads(archive.read("notebook.json"))["items"][0]["text"] == "Task in manual backup"
    window.tray.hide()
    window.quitting = True
