"""Regression tests for the seven points reported on 2026-11-06."""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QPushButton

from app.models import Notebook
from app.reminders import Reminders
from app.storage import StorageError, Store
from app.ui.icons import PATHS
from app.ui.tasks import Tasks


def test_completed_stays_until_cleanup_and_survives_restart(qtbot, tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    parent = book.add("Parent")
    child = book.add("Child", parent["id"])
    other = book.add("Open sibling")
    widget = Tasks(book, {})
    qtbot.addWidget(widget)
    widget.changed.connect(lambda: store.save(book.data))
    widget.completion_requested.connect(lambda ident, done: (book.complete(ident, done), widget.show_completed(ident)))
    widget.show()
    widget.rows[parent["id"]].setCheckState(0, Qt.Checked)
    qtbot.waitUntil(lambda: parent["done"])
    assert parent["done"] and child["done"]
    assert widget.rows[parent["id"]].font(0).strikeOut()
    assert child["id"] in widget.rows
    widget.expire_undo(parent["id"])
    widget.rebuild()
    assert parent["id"] in widget.rows
    qtbot.mouseClick(widget.cleanup_button, Qt.LeftButton)
    assert set(widget.rows) == {other["id"]}
    assert len(book.items) == 3
    reopened = Tasks(Notebook(Store(tmp_path).load()), {})
    qtbot.addWidget(reopened)
    assert set(reopened.rows) == {other["id"]}
    reopened.status.setCurrentIndex(1)
    assert set(reopened.rows) == {parent["id"], child["id"]}
    book.complete(child["id"], False)
    widget.rebuild()
    assert parent["id"] in widget.rows and child["id"] in widget.rows
    book.complete(child["id"], True)
    widget.rebuild()
    assert child["id"] in widget.rows  # A newly completed task isn't hidden by an old cleanup.


def test_collapsed_defaults_full_width_plus_and_distinct_row_buttons(qtbot):
    book = Notebook()
    parent = book.add("Parent https://example.org/full/url")
    child = book.add("Child\ncontinued", parent["id"])
    grandchild = book.add("Grandchild", child["id"])
    book.add("Sibling", parent["id"])
    book.add("Unrelated")
    book.complete(grandchild["id"], True)
    widget = Tasks(book, {})
    qtbot.addWidget(widget)
    widget.resize(1200, 650)
    widget.show()
    row = widget.rows[parent["id"]]
    assert all(not r.isExpanded() for r in widget.rows.values())
    add_row = row.child(row.childCount() - 1)
    assert widget.tree.visualItemRect(add_row).isEmpty()
    row.setExpanded(True)
    QApplication.processEvents()
    plus = widget.tree.itemWidget(add_row, 0).findChild(QPushButton)
    assert plus.icon().isNull() is False
    assert plus.width() > widget.tree.viewport().width() - 100
    actions = []
    widget.action_requested.connect(lambda *args: actions.append(args))
    qtbot.mouseClick(plus, Qt.LeftButton, pos=QPoint(plus.width() - 3, plus.height() // 2))
    assert actions == [(parent["id"], "child")]
    rect = widget.tree.visualItemRect(add_row)
    qtbot.mouseClick(widget.tree.viewport(), Qt.LeftButton, pos=QPoint(3, rect.center().y()))
    assert actions == [(parent["id"], "child")] * 2
    controls = {b.accessibleName(): b for b in widget.tree.itemWidget(row, 4).findChildren(QPushButton)}
    qtbot.mouseClick(controls["Copy item text"], Qt.LeftButton)
    assert QApplication.clipboard().text() == parent["text"]
    qtbot.mouseClick(controls["Copy item and all subtasks"], Qt.LeftButton)
    assert QApplication.clipboard().text() == (
        "- Parent https://example.org/full/url\n  - Child\n    continued\n    - Grandchild\n  - Sibling"
    )
    assert PATHS["copy"] != PATHS["copy-tree"]
    qtbot.mouseClick(controls["Delete item"], Qt.LeftButton)
    assert actions[-1] == (parent["id"], "delete")
    assert controls["Delete item"].geometry().right() > controls["Copy item text"].geometry().right()


@pytest.mark.parametrize("target_name", ["notebook.json", "notebook.backup.json", "notebook.backup.2.json"])
def test_windows_transient_locks_retry_without_data_loss(tmp_path, monkeypatch, target_name):
    import app.storage as storage

    store = Store(tmp_path)
    book = Notebook(store.load())
    book.add("First")
    store.save(book.data)
    original = store.path.read_bytes()
    book.add("Second")
    replace = storage.os.replace
    calls, sleeps = [], []

    def locked(source, target):
        if target.name == target_name:
            calls.append(target)
            if len(calls) <= 3:
                error = PermissionError("Access is denied")
                error.winerror = 5
                raise error
        return replace(source, target)

    monkeypatch.setattr(storage.os, "replace", locked)
    monkeypatch.setattr(storage.time, "sleep", sleeps.append)
    store.save(book.data)
    assert len(calls) == 4 and sleeps == [0.025, 0.05, 0.1]
    assert len(Store(tmp_path).load()["items"]) == 2
    assert store.backup.read_bytes() == original
    assert not list(tmp_path.glob(".notebook-*.tmp"))


def test_permanent_windows_lock_stops_safely_and_can_retry(tmp_path, monkeypatch):
    import app.storage as storage

    store = Store(tmp_path)
    book = Notebook(store.load())
    book.add("Saved")
    store.save(book.data)
    original = store.path.read_bytes()
    book.add("Unsaved")
    replace = storage.os.replace
    calls = []

    def locked(source, target):
        if target == store.backup:
            calls.append(target)
            error = PermissionError("persistent lock")
            error.winerror = 32
            raise error
        return replace(source, target)

    monkeypatch.setattr(storage.os, "replace", locked)
    monkeypatch.setattr(storage.time, "sleep", lambda _: None)
    with pytest.raises(StorageError, match="persistent lock"):
        store.save(book.data)
    assert len(calls) == 6
    assert store.path.read_bytes() == original and len(book.items) == 2
    monkeypatch.undo()
    store.save(book.data)
    assert len(Store(tmp_path).load()["items"]) == 2


def test_external_edit_during_lock_retry_is_not_overwritten(tmp_path, monkeypatch):
    import app.storage as storage

    store = Store(tmp_path)
    book = Notebook(store.load())
    book.add("Saved")
    store.save(book.data)
    book.add("Local edit")
    replace = storage.os.replace

    def locked(source, target):
        if target == store.path:
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        return replace(source, target)

    monkeypatch.setattr(storage.os, "replace", locked)
    monkeypatch.setattr(storage.time, "sleep", lambda _: store.path.write_bytes(b"external work"))
    with pytest.raises(StorageError, match="changed while saving"):
        store.save(book.data)
    assert store.path.read_bytes() == b"external work"


@pytest.mark.skipif(sys.platform != "win32", reason="Uses real Windows file-sharing semantics")
def test_real_windows_backup_file_lock_is_retried(tmp_path):
    import ctypes
    from ctypes import wintypes

    store = Store(tmp_path)
    book = Notebook(store.load())
    book.add("Saved")
    store.save(book.data)
    original = store.path.read_bytes()
    book.add("After transient lock")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(store.backup), 0x80000000, 1, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()

    def release():
        time.sleep(0.12)
        kernel.CloseHandle(handle)

    thread = threading.Thread(target=release)
    thread.start()
    try:
        store.save(book.data)
    finally:
        thread.join()
    assert store.backup.read_bytes() == original
    assert len(Store(tmp_path).load()["items"]) == 2


def test_missing_windows_setting_still_submits_and_other_errors_propagate(monkeypatch):
    from app.notifications.windows import WindowsNotifications

    class Settings:
        error = -2147023728

        @property
        def setting(self):
            error = OSError("Element not found")
            error.winerror = self.error
            raise error

    shown = []
    settings = Settings()
    notifications = WindowsNotifications.__new__(WindowsNotifications)
    notifications.toaster = SimpleNamespace(toastNotifier=settings, show_toast=shown.append)
    monkeypatch.setitem(sys.modules, "windows_toasts", SimpleNamespace(Toast=SimpleNamespace))
    monkeypatch.setitem(sys.modules, "winrt.windows.ui.notifications",
                        SimpleNamespace(NotificationSetting=SimpleNamespace(ENABLED=0)))
    notifications.send({"id": "task", "text": "Reminder"}, lambda _: None, lambda *args: None)
    assert len(shown) == 1
    settings.error = -2147024891
    with pytest.raises(OSError):
        notifications.send({"id": "task", "text": "Reminder"}, lambda _: None, lambda *args: None)
    assert len(shown) == 1


def test_failed_reminder_retries_later_and_rescheduled_reminder_is_not_changed():
    start = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    book = Notebook()
    task = book.add("Reminder")
    at = (start + timedelta(seconds=1)).isoformat()
    task["reminder"] = {"at": at}
    reminders = Reminders(book, started=start)
    now = start + timedelta(seconds=2)
    assert reminders.due(now) == [task]
    assert reminders.failed(task["id"], at, now)
    assert not task["reminder"]["notified_at"]
    assert reminders.due(now + timedelta(seconds=59)) == []
    assert reminders.due(now + timedelta(minutes=1)) == [task]
    task["reminder"] = {"at": (now + timedelta(hours=1)).isoformat()}
    assert not reminders.failed(task["id"], at, now)
    assert "notified_at" not in task["reminder"]


@pytest.mark.skipif(sys.platform != "win32" or os.environ.get("GETITDONE_NATIVE_NOTIFICATIONS") != "1",
                    reason="Opt-in test submits a real native Windows notification")
def test_real_windows_toast_reaches_notification_center():
    # Isolate WinRT from mocked modules and Qt threads created by the rest of the suite.
    script = '''
import json
from uuid import uuid4
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication([])
from app.notifications.windows import WindowsNotifications, APP_ID
from winrt.windows.ui.notifications import ToastNotificationManager
notifications = WindowsNotifications()
text = "GetItDone notification integration test " + uuid4().hex
notifications.send({"id": "native-test", "text": text}, lambda _: None, lambda *args: None)
history = ToastNotificationManager.history.get_history_with_id(APP_ID)
matches = [t for t in history if t.data and dict(t.data.values).get("text2") == text]
assert len(matches) == 1
print(json.dumps({"native_toasts_verified": len(matches)}))
notifications.close()
for toast in matches:
    ToastNotificationManager.history.remove_grouped_tag_with_id(toast.tag, toast.group, APP_ID)
del toast, matches, history, notifications
import gc
gc.collect()  # Release history COM wrappers while the Qt/WinRT runtime is still alive.
QTimer.singleShot(300, app.quit)
app.exec()  # Drain WinRT callbacks after removing the test toast before Python shuts down.
'''
    result = subprocess.run([sys.executable, "-u", "-X", "faulthandler", "-c", script],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["native_toasts_verified"] == 1
