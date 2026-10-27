import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Notebook
from app.reminders import Reminders
from app.storage import StorageError, Store, validate


def test_hierarchy_completion_reactivation_and_movement():
    book = Notebook()
    a = book.add("Parent")
    b = book.add("Child", parent=a["id"])
    c = book.add("Grandchild", parent=b["id"])
    snapshot = book.complete(a["id"], True)
    assert all(item["done"] for item in (a, b, c))
    book.restore_completion(snapshot)
    assert all(not item["done"] for item in (a, b, c))
    book.complete(c["id"], True)
    assert not b["done"]
    book.complete(b["id"], True)
    book.complete(a["id"], True)
    book.complete(c["id"], False)
    assert not a["done"] and not b["done"]
    book.indent(c["id"], out=True)
    assert c["parent_id"] == a["id"]
    book.move(c["id"], -1)
    assert book.children(a["id"])[0] is c
    book.indent(b["id"])
    assert b["parent_id"] == c["id"]
    book.delete(c["id"])
    assert len(book.items) == 1


def test_filter_retains_ancestors_without_category_inheritance():
    book = Notebook()
    a = book.add("Parent")
    b = book.add("Child", parent=a["id"])
    book.update(b["id"], notes="needle", category_id="c")
    visible, direct = book.visible("needle", "open", "c")
    assert direct == {b["id"]}
    assert visible == {a["id"], b["id"]}
    assert a["category_id"] is None
    book.delete_category("c")
    assert b["category_id"] is None


def test_atomic_persistence_backup_and_corruption(tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    book.add("Unicode ä 漢字")
    store.save(book.data)
    original = store.path.read_bytes()
    book.add("Second")
    store.save(book.data)
    assert store.backup.read_bytes() == original
    assert len(Store(tmp_path).load()["items"]) == 2
    store.path.write_text("{broken")
    damaged = store.path.read_bytes()
    with pytest.raises(StorageError):
        Store(tmp_path).load()
    with pytest.raises(StorageError):
        store.save(book.data)
    assert store.path.read_bytes() == damaged
    assert store.backup.read_bytes() == original


def test_unknown_schema_is_never_overwritten(tmp_path):
    path = tmp_path / "notebook.json"
    path.write_text('{"schema_version":999}')
    store = Store(tmp_path)
    with pytest.raises(StorageError):
        store.load()
    with pytest.raises(StorageError):
        store.save(Notebook().data)
    assert json.loads(path.read_text())["schema_version"] == 999


def test_cycle_and_duplicate_ids_rejected():
    book = Notebook()
    a = book.add("a")
    b = book.add("b", parent=a["id"])
    a["parent_id"] = b["id"]
    with pytest.raises(StorageError):
        validate(book.data)
    a["parent_id"] = None
    b["id"] = a["id"]
    with pytest.raises(StorageError):
        validate(book.data)


def test_reminders_once_missed_done_and_edited():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    book = Notebook()
    old = book.add("Missed")
    future = book.add("Due")
    done = book.add("Done")
    for item, when in [
        (old, start - timedelta(minutes=1)),
        (future, start + timedelta(seconds=3)),
        (done, start + timedelta(seconds=3)),
    ]:
        item["reminder"] = {"at": when.isoformat(), "notified_at": None}
    done["done"] = True
    reminders = Reminders(book, start)
    assert reminders.due(start + timedelta(seconds=4)) == [future]
    assert reminders.due(start + timedelta(seconds=5)) == []
    future["reminder"]["notified_at"] = None
    reminders.changed(future["id"])
    assert reminders.due(start + timedelta(seconds=5)) == [future]
    assert old["reminder"]["notified_at"] is None


def test_single_instance_lock(tmp_path):
    from PySide6.QtCore import QLockFile

    path = str(tmp_path / "instance.lock")
    first = QLockFile(path)
    second = QLockFile(path)
    assert first.tryLock(0)
    assert not second.tryLock(0)
    first.unlock()
    assert second.tryLock(0)
    second.unlock()


def test_write_failure_preserves_original(tmp_path, monkeypatch):
    store = Store(tmp_path)
    book = Notebook(store.load())
    book.add("original")
    store.save(book.data)
    original = store.path.read_bytes()
    book.add("not saved")

    def denied(source, target):
        raise PermissionError("permission denied")

    monkeypatch.setattr("app.storage.os.replace", denied)
    with pytest.raises(StorageError):
        store.save(book.data)
    assert store.path.read_bytes() == original
    assert not list(tmp_path.glob(".notebook-*.tmp"))


def test_drag_relocation_preserves_subtree_rejects_cycles_and_roundtrips(tmp_path):
    book = Notebook()
    a = book.add("A")
    b = book.add("B")
    child = book.add("Child", parent=a["id"])
    grandchild = book.add("Grandchild", parent=child["id"])
    book.complete(b["id"], True)
    assert not book.relocate(a["id"], grandchild["id"])
    assert not book.relocate(a["id"], None, "missing")
    assert book.relocate(a["id"], b["id"])
    assert not b["done"]
    assert child["parent_id"] == a["id"]
    assert grandchild["parent_id"] == child["id"]
    assert book.relocate(child["id"], None, b["id"])
    assert book.children(None) == [child, b]
    assert [i["position"] for i in book.children(None)] == [0, 1]
    store = Store(tmp_path)
    store.load()
    store.save(book.data)
    restored = Notebook(store.load())
    assert [i["id"] for i in restored.children(None)] == [child["id"], b["id"]]
    assert restored.get(grandchild["id"])["parent_id"] == child["id"]
