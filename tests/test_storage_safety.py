import json

import pytest

from app.models import Notebook
from app.storage import StorageError, Store


def saved_book(tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    book.add("Important ä 漢字")
    store.save(book.data)
    return store, book


def test_first_save_has_backup_and_unchanged_saves_keep_history(tmp_path):
    store, book = saved_book(tmp_path)
    assert store.backup.read_bytes() == store.path.read_bytes()
    book.add("second")
    store.save(book.data)
    previous = store.backup.read_bytes()
    for _ in range(5):
        store.save(book.data)
    assert store.backup.read_bytes() == previous


@pytest.mark.parametrize("damage", [b"{broken", b"", b"\xff\xfe", b'[]', b'{"schema_version":1}'])
def test_recovers_corruption_preserves_exact_original_and_can_save(tmp_path, damage):
    store, book = saved_book(tmp_path)
    store.path.write_bytes(damage)
    reopened = Store(tmp_path)
    assert reopened.load() == book.data
    assert next(tmp_path.glob("notebook.damaged-*.json")).read_bytes() == damage
    book.add("after recovery")
    reopened.save(book.data)
    assert len(Store(tmp_path).load()["items"]) == 2


def test_missing_primary_recovers_instead_of_opening_empty(tmp_path):
    store, book = saved_book(tmp_path)
    store.path.unlink()
    reopened = Store(tmp_path)
    assert reopened.load() == book.data
    assert reopened.recovery_notice


def test_fallback_skips_damaged_backup(tmp_path):
    store, book = saved_book(tmp_path)
    for n in range(3):
        book.add(str(n))
        store.save(book.data)
    expected = json.loads(store.backups[1].read_bytes())
    store.path.write_bytes(b"broken")
    store.backup.write_bytes(b"also broken")
    reopened = Store(tmp_path)
    assert reopened.load() == expected
    assert store.backup.read_bytes() == b"also broken"


@pytest.mark.parametrize("missing", [False, True])
def test_unrecoverable_notebook_never_becomes_empty(tmp_path, missing):
    store, _ = saved_book(tmp_path)
    if missing:
        store.path.unlink()
    else:
        store.path.write_bytes(b"broken")
    store.backup.write_bytes(b"broken backup")
    snapshot = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    reopened = Store(tmp_path)
    with pytest.raises(StorageError):
        reopened.load()
    with pytest.raises(StorageError):
        reopened.save(Notebook().data)
    assert snapshot == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_future_schema_not_replaced_by_valid_backup(tmp_path):
    store, _ = saved_book(tmp_path)
    raw = b'{"schema_version":999}'
    store.path.write_bytes(raw)
    with pytest.raises(StorageError, match="version"):
        Store(tmp_path).load()
    assert store.path.read_bytes() == raw


@pytest.mark.parametrize("external", [None, b"external version"])
def test_external_changes_block_save_without_touching_backups(tmp_path, external):
    store, book = saved_book(tmp_path)
    backup = store.backup.read_bytes()
    if external is None:
        store.path.unlink()
    else:
        store.path.write_bytes(external)
    book.add("unsaved local work")
    with pytest.raises(StorageError, match="outside"):
        store.save(book.data)
    assert store.current_bytes() == external
    assert store.backup.read_bytes() == backup
    assert len(book.items) == 2


@pytest.mark.parametrize("stage", ["backup", "primary", "fsync"])
def test_failed_writes_leave_valid_recoverable_state(tmp_path, monkeypatch, stage):
    import app.storage as storage

    store, book = saved_book(tmp_path)
    original = store.path.read_bytes()
    book.add("new work")
    replace = storage.os.replace

    def fail_replace(source, target):
        if target == (store.backup if stage == "backup" else store.path):
            raise OSError("simulated disk failure")
        return replace(source, target)

    if stage == "fsync":
        monkeypatch.setattr(storage.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk full")))
    else:
        monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(StorageError):
        store.save(book.data)
    assert store.path.read_bytes() == original
    assert store.backup.read_bytes() == original
    assert not list(tmp_path.glob(".notebook-*.tmp"))
    monkeypatch.undo()
    store.save(book.data)
    assert len(Store(tmp_path).load()["items"]) == 2


def test_repeated_load_failure_disables_saving(tmp_path):
    store, _ = saved_book(tmp_path)
    store.path.write_bytes(b"broken")
    store.backup.unlink()
    with pytest.raises(StorageError):
        store.load()
    assert not store.writable


def test_change_during_backup_is_not_overwritten(tmp_path, monkeypatch):
    import app.storage as storage

    store, book = saved_book(tmp_path)
    book.add("local")
    write = storage.atomic_write

    def external_change(path, raw):
        write(path, raw)
        if path == store.backup:
            store.path.write_bytes(b"external edit")

    monkeypatch.setattr(storage, "atomic_write", external_change)
    with pytest.raises(StorageError, match="while saving"):
        store.save(book.data)
    assert store.path.read_bytes() == b"external edit"


def test_failed_recovery_archive_never_replaces_damaged_original(tmp_path, monkeypatch):
    store, _ = saved_book(tmp_path)
    store.path.write_bytes(b"damaged original")

    def denied(*args):
        raise OSError("no space for recovery archive")

    monkeypatch.setattr("app.storage.atomic_write", denied)
    reopened = Store(tmp_path)
    with pytest.raises(StorageError):
        reopened.load()
    assert not reopened.writable
    assert store.path.read_bytes() == b"damaged original"
    assert json.loads(store.backup.read_bytes())["items"]


def test_backup_generations_contain_previous_three_states(tmp_path):
    store, book = saved_book(tmp_path)
    for n in range(4):
        book.add(str(n))
        store.save(book.data)
    assert [len(json.loads(p.read_bytes())["items"]) for p in store.backups] == [4, 3, 2]


@pytest.mark.parametrize("after_replace", [False, True])
def test_interruption_at_commit_reopens_complete_old_or_new_state(tmp_path, monkeypatch, after_replace):
    import app.storage as storage

    store, book = saved_book(tmp_path)
    book.add("new work")
    replace = storage.os.replace

    def interrupted(source, target):
        if target == store.path:
            if after_replace:
                replace(source, target)
            raise SystemExit("simulated abrupt interruption")
        return replace(source, target)

    monkeypatch.setattr(storage.os, "replace", interrupted)
    with pytest.raises(SystemExit):
        store.save(book.data)
    reopened = Store(tmp_path).load()
    assert len(reopened["items"]) == (2 if after_replace else 1)
    assert len(json.loads(store.backup.read_bytes())["items"]) == 1
