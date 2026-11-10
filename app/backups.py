"""Scheduled, complete notebook snapshots and separate knowledge files."""

import copy
import json
import os
import stat
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QStandardPaths, Signal

from app.scheduling import local_zone, next_occurrence


def default_backup_folder():
    documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return (Path(documents) if documents else Path.home() / "Documents") / "GetItDone" / "Backups"


def backup_defaults():
    return dict(enabled=False, time="18:00", every=1, unit="days", folder=str(default_backup_folder()), next_at=None,
                last_at=None, last_file="", last_error="")


def validate_backup(config):
    if not isinstance(config, dict):
        raise ValueError("Invalid backup settings.")
    value = backup_defaults() | config
    if (type(value["enabled"]) is not bool or type(value["every"]) is not int
            or not 1 <= value["every"] <= 999 or value["unit"] not in ("days", "weeks", "months")
            or any(not isinstance(value[k], str) for k in ("time", "folder", "last_file", "last_error"))):
        raise ValueError("Invalid backup settings.")
    try:
        parsed = datetime.strptime(value["time"], "%H:%M")
        if parsed.strftime("%H:%M") != value["time"]:
            raise ValueError()
        for key in ("next_at", "last_at"):
            if value[key] is not None and datetime.fromisoformat(value[key]).tzinfo is None:
                raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("Invalid backup date or time.") from None
    if value["enabled"] and (not value["folder"].strip() or value["next_at"] is None):
        raise ValueError("Enabled backups need a destination and next date.")
    return value


def schedule_key(config):
    return tuple(config.get(key) for key in ("enabled", "time", "every", "unit", "folder"))


def configure_backup(previous, *, enabled, time, every, unit, folder, now=None):
    value = backup_defaults() | previous
    value.update(enabled=enabled, time=time, every=every, unit=unit, folder=folder)
    if schedule_key(value) != schedule_key(backup_defaults() | previous):
        now = now or datetime.now(local_zone())
        hour, minute = map(int, time.split(":"))
        first = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if first < now:
            first += timedelta(days=1)
        value.update(next_at=first.isoformat() if enabled else None, last_error="")
    return validate_backup(value)


def check_destination(folder, data_folder, knowledge_folder=""):
    if not folder.strip():
        raise ValueError("Choose a backup folder.")
    target = Path(folder).expanduser().resolve()
    for source in (data_folder, knowledge_folder):
        if source:
            root = Path(source).expanduser().resolve()
            if target == root or root in target.parents:
                raise ValueError("Choose a backup folder outside the data and knowledge folders.")
    return target


def create_backup(data, data_folder, now=None):
    """Publish only a fully written, verified ZIP. Never change source files."""
    from app.storage import validate

    validate(data)
    config = validate_backup(data["settings"]["backups"])
    knowledge = data["settings"].get("knowledge_folder", "")
    target = check_destination(config["folder"], data_folder, knowledge)
    target.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(local_zone())
    destination = target / f"GetItDone-{now:%Y-%m-%d_%H-%M-%S}-{uuid4().hex[:12]}.zip"
    fd, temporary = tempfile.mkstemp(prefix=".getitdone-backup-", suffix=".tmp", dir=target)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                             allowZip64=True, strict_timestamps=False) as archive:
            archive.writestr("notebook.json", json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
            canvas = Path(data_folder) / "canvas"
            sources = [("knowledge", Path(knowledge).expanduser())] if knowledge else []
            if canvas.exists() or canvas.is_symlink():
                sources.append(("canvas", canvas))
            for kind, root in sources:
                if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
                    raise OSError(f"Backup cannot safely include a linked {kind} path: {root}")
                if not root.is_dir():
                    raise OSError(f"The {kind} folder is unavailable; no complete backup was created.")
                # os.walk reports traversal errors rather than silently omitting unreadable folders.
                def failed(exc):
                    raise exc

                for directory, folders, files in os.walk(root, onerror=failed, followlinks=False):
                    for name in folders + files:
                        path = Path(directory) / name
                        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                            raise OSError(f"Backup cannot safely include a linked {kind} path: {path}")
                        relative = kind + "/" + path.relative_to(root).as_posix()
                        if name in folders:
                            archive.writestr(relative + "/", b"")
                        else:
                            before = path.stat()
                            if not stat.S_ISREG(before.st_mode):
                                raise OSError(f"{kind.title()} path is not a regular file: {path}")
                            archive.write(path, relative)
                            after = path.stat()
                            if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                                    after.st_size, after.st_mtime_ns, after.st_ino):
                                raise OSError(f"{kind.title()} file changed during backup: {path}")
                archive.writestr(kind + "/", b"")
            archive.writestr("manifest.json", json.dumps(dict(
                format="GetItDone backup", version=1, created_at=now.isoformat(),
                data_folder=str(Path(data_folder).resolve()), knowledge_folder=knowledge,
                canvas_folder=str(canvas.resolve()),
            ), ensure_ascii=False, indent=2))
            archive.writestr("RESTORE.txt", (
                "Quit GetItDone before restoring. Preserve your current data first.\n"
                "Extract notebook.json into the data folder shown in Settings.\n"
                "Restore canvas/ into that same data folder, including all its files and subfolders.\n"
                "Files outside canvas/ referenced by the Canvas HTML are not part of the Canvas backup.\n"
                "Restore knowledge/ into your knowledge folder (its original path is in manifest.json).\n"
                "If that path changed, choose the restored folder in Knowledge after starting the app.\n"
                "External agent projects, credentials and native chat histories are not included.\n"
            ))
        with zipfile.ZipFile(temporary) as archive:
            damaged = archive.testzip()
            if damaged:
                raise OSError(f"Backup verification failed: {damaged}")
        with open(temporary, "r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return str(destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


class BackupScheduler(QObject):
    changed = Signal()
    status = Signal(str)
    completed = Signal(str)

    def __init__(self, notebook, data_folder, prepare, persist, launch, parent=None):
        super().__init__(parent)
        self.notebook = notebook
        self.data_folder = data_folder
        self.prepare = prepare
        self.persist = persist
        self.launch = launch
        self.active = False
        self.retry_at = None

    def tick(self, now=None):
        now = now or datetime.now(local_zone())
        config = backup_defaults() | self.notebook.data["settings"].get("backups", {})
        if (not self.active and config["enabled"] and config["next_at"]
                and datetime.fromisoformat(config["next_at"]) <= now
                and (self.retry_at is None or now >= self.retry_at)):
            self.start(now)

    def backup_now(self, folder, now=None):
        if self.active:
            return False
        folder = str(check_destination(folder, self.data_folder,
                                       self.notebook.data["settings"].get("knowledge_folder", "")))
        return self.start(now or datetime.now(local_zone()), manual=True, folder=folder)

    def start(self, now, manual=False, folder=None):
        if self.active:
            return False
        self.notebook.data["settings"].setdefault("backups", backup_defaults())
        if not manual:
            self.retry_at = now + timedelta(minutes=5)
        if not self.prepare():
            self.failed("Current edits could not be saved; backup postponed.", retry=not manual)
            return False
        config = backup_defaults() | copy.deepcopy(self.notebook.data["settings"]["backups"])
        snapshot = copy.deepcopy(self.notebook.data)
        following = None
        if not manual:
            following = next_occurrence(datetime.fromisoformat(config["next_at"]).astimezone(local_zone()),
                                        config["every"], config["unit"], now)
            hour, minute = map(int, config["time"].split(":"))
            following = following.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0)
            if following <= now:
                following = next_occurrence(following, config["every"], config["unit"], now)
        snapshot["settings"]["backups"] = copy.deepcopy(config)
        if manual:
            snapshot["settings"]["backups"]["folder"] = folder
        # Restoring this archive must not immediately repeat its already completed occurrence.
        snapshot["settings"]["backups"].update(last_at=now.isoformat(), last_file="", last_error="")
        if following:
            snapshot["settings"]["backups"]["next_at"] = following.isoformat()
        self.active = True
        self.status.emit("Backup in progress …")
        self.changed.emit()

        def finished(path, exc):
            self.active = False
            current = self.notebook.data["settings"].get("backups", {})
            same = (schedule_key(backup_defaults() | current) == schedule_key(config)
                    and current.get("next_at") == config["next_at"])
            if exc:
                self.failed(str(exc), record=same, retry=not manual)
            else:
                current.update(last_at=now.isoformat(), last_file=path, last_error="")
                if same and following:
                    current["next_at"] = following.isoformat()
                if not manual:
                    self.retry_at = None
                self.persist()
                self.status.emit("Backup saved: " + path)
                self.changed.emit()
                self.completed.emit(path)

        self.launch(lambda: create_backup(snapshot, self.data_folder, now), finished)
        return True

    def failed(self, message, record=True, retry=True):
        if record:
            self.notebook.data["settings"].setdefault("backups", backup_defaults())["last_error"] = message
            self.persist()
        self.status.emit(("Backup failed — retry in 5 minutes: " if retry else "Backup failed: ") + message)
        self.changed.emit()
