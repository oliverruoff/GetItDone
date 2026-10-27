"""Atomic notebook storage with validated backups and lossless recovery archives."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.models import empty_data


class StorageError(Exception):
    pass


def validate(data):
    def fail(message):
        raise StorageError(message)

    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
    ):
        fail("Unknown data version. The file has not been changed.")
    for key, kind in (("settings", dict), ("items", list), ("categories", list), ("sessions", list)):
        if not isinstance(data.get(key), kind):
            fail(f"Invalid data field: {key}")
    ids = set()
    for group in ("items", "categories", "sessions"):
        for row in data[group]:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not row["id"]
                or row["id"] in ids
            ):
                fail("Missing or duplicate IDs.")
            ids.add(row["id"])
    items = {i["id"]: i for i in data["items"]}
    cats = {c["id"] for c in data["categories"]}
    for category in data["categories"]:
        if not all(isinstance(category.get(k), str) for k in ("name", "color")):
            fail("Invalid category.")
    for ident, item in items.items():
        if (
            not all(isinstance(item.get(k), str) for k in ("text", "notes", "created_at", "updated_at"))
            or type(item.get("done")) is not bool
            or type(item.get("position")) is not int
            or "parent_id" not in item
            or "category_id" not in item
            or "reminder" not in item
        ):
            fail("Invalid task item.")
        if item["category_id"] is not None and (
            not isinstance(item["category_id"], str) or item["category_id"] not in cats
        ):
            fail("A task references a missing category.")
        visited = {ident}
        parent = item["parent_id"]
        while parent is not None:
            if not isinstance(parent, str) or parent not in items or parent in visited:
                fail("Invalid or circular task hierarchy.")
            visited.add(parent)
            parent = items[parent]["parent_id"]
        reminder = item["reminder"]
        if reminder is not None:
            if not isinstance(reminder, dict) or not isinstance(reminder.get("at"), str):
                fail("Invalid reminder.")
            try:
                if datetime.fromisoformat(reminder["at"]).tzinfo is None:
                    fail("Reminder is missing a time zone.")
            except (TypeError, ValueError):
                fail("Invalid reminder date or time.")
    for session in data["sessions"]:
        if (
            not isinstance(session.get("item_id"), str)
            or session.get("item_id") not in items
            or not all(isinstance(session.get(k), str) for k in ("agent", "workdir", "title", "created_at"))
            or not isinstance(session.get("native_session_id"), (str, type(None)))
        ):
            fail("Invalid session link.")
        reply = session.get("last_reply")
        if reply is not None and (
            not isinstance(reply, dict)
            or not isinstance(reply.get("text"), str)
            or not isinstance(reply.get("saved_at"), str)
        ):
            fail("Invalid saved agent reply.")
        if "reply_unread" in session and type(session["reply_unread"]) is not bool:
            fail("Invalid agent reply state.")
    settings = data["settings"]
    for key in ("default_workdir", "default_agent", "knowledge_folder", "knowledge_last_file"):
        if key in settings and not isinstance(settings[key], str):
            fail(f"Invalid setting: {key}")
    view = settings.get("task_view", {})
    if (not isinstance(view, dict)
            or any(not isinstance(view.get(key, []), list)
                   or any(not isinstance(ident, str) for ident in view.get(key, []))
                   for key in ("titles", "notes", "hidden_notes"))
            or not isinstance(view.get("expanded", {}), dict)
            or any(not isinstance(k, str) or type(v) is not bool
                   for k, v in view.get("expanded", {}).items())):
        fail("Invalid task view state.")
    jobs = data.get("scheduled_jobs", [])
    if not isinstance(jobs, list):
        fail("Invalid scheduled jobs.")

    def date(value, optional=False):
        if optional and value is None:
            return True
        try:
            return isinstance(value, str) and datetime.fromisoformat(value).tzinfo is not None
        except ValueError:
            return False

    for job in jobs:
        if (not isinstance(job, dict)
                or not all(isinstance(job.get(k), str) and job[k]
                           for k in ("id", "title", "prompt", "agent", "workdir"))
                or job["id"] in ids
                or type(job.get("enabled")) is not bool
                or type(job.get("every")) is not int or not 0 <= job["every"] <= 999
                or job.get("unit") not in ("minutes", "hours", "days", "weeks", "months")
                or not date(job.get("next_at"), optional=True)
                or (job["enabled"] and job.get("next_at") is None)
                or not isinstance(job.get("runs"), list)):
            fail("Invalid scheduled job.")
        ids.add(job["id"])
        for run in job["runs"]:
            if (not isinstance(run, dict)
                    or not all(isinstance(run.get(k), str) for k in
                               ("id", "output", "prompt", "agent", "workdir"))
                    or not run["id"] or run["id"] in ids
                    or run.get("status") not in ("running", "completed", "failed", "interrupted")
                    or not date(run.get("started_at"))
                    or not date(run.get("finished_at"), optional=True)
                    or not isinstance(run.get("session_id"), (str, type(None)))):
                fail("Invalid scheduled run.")
            ids.add(run["id"])
    profiles = settings.get("profiles", [])
    if not isinstance(profiles, list) or any(
        not isinstance(p, dict)
        or not all(isinstance(p.get(k), str) for k in ("id", "name", "executable"))
        or not isinstance(p.get("args"), list)
        or not all(isinstance(a, str) for a in p["args"])
        for p in profiles
    ):
        fail("Invalid agent profiles.")
    return data


def atomic_write(path, raw):
    """Flush the file before replace and the directory afterwards (POSIX)."""
    temp = None
    try:
        fd, temp = tempfile.mkstemp(prefix=".notebook-", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        temp = None
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if temp:
            Path(temp).unlink(missing_ok=True)


def decode(raw):
    return validate(json.loads(raw.decode("utf-8-sig")))


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "notebook.json"
        self.backup = self.folder / "notebook.backup.json"
        self.backups = [self.backup, self.folder / "notebook.backup.2.json",
                        self.folder / "notebook.backup.3.json"]
        self.writable = False
        self.expected = None
        self.recovery_notice = ""

    def current_bytes(self):
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def load(self):
        self.writable = False
        self.recovery_notice = ""
        try:
            raw = self.current_bytes()
            # A future version must never be replaced with an older backup.
            if raw is not None:
                try:
                    version = json.loads(raw.decode("utf-8-sig")).get("schema_version")
                except (ValueError, AttributeError):
                    version = None
                if type(version) is int and version != 1:
                    raise StorageError("Unknown data version. The file has not been changed.")
            try:
                data = decode(raw) if raw is not None else None
            except (StorageError, ValueError, TypeError, KeyError, RecursionError):
                data = None
            if data is None:
                for candidate in self.backups:
                    try:
                        recovered = candidate.read_bytes()
                        data = decode(recovered)
                    except (OSError, StorageError, ValueError, TypeError, KeyError, RecursionError):
                        continue
                    preserved = None
                    if raw is not None:
                        preserved = self.folder / f"notebook.damaged-{uuid4().hex}.json"
                        atomic_write(preserved, raw)
                    # Recovery must not overwrite a file changed while reading backups.
                    if self.current_bytes() != raw:
                        raise StorageError("The notebook changed during recovery. Please reopen it.")
                    atomic_write(self.path, recovered)
                    raw = recovered
                    self.recovery_notice = (
                        f"Recovered notebook from {candidate.name}. "
                        "The most recent changes may be missing. "
                        + (f"The damaged original is preserved as {preserved.name}." if preserved else
                           "The main notebook file was missing.")
                    )
                    break
                else:
                    if raw is not None or any(p.exists() for p in self.backups):
                        raise StorageError("No valid notebook or backup found. All files have been preserved.")
                    data = empty_data()
            self.expected = raw
            self.writable = True
            return data
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StorageError(f"Could not load data: {exc}. Original and backups preserved.") from exc

    def save(self, data):
        if not self.writable:
            raise StorageError("Saving is blocked because data could not be loaded successfully.")
        validate(data)
        try:
            raw = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
            previous = self.current_bytes()
            if previous != self.expected:
                raise StorageError(
                    "The notebook was changed or deleted outside this app. Saving stopped to protect "
                    "both versions. Your edits remain in memory; copy the data folder before reopening."
                )
            if previous == raw:
                return
            # Keep three distinct generations. Never rotate a damaged backup into history.
            for source, target in reversed(list(zip(self.backups, self.backups[1:]))):
                if source.exists():
                    old = source.read_bytes()
                    try:
                        decode(old)
                    except (StorageError, ValueError, TypeError, KeyError, RecursionError):
                        continue
                    atomic_write(target, old)
            atomic_write(self.backup, previous if previous is not None else raw)
            if self.current_bytes() != previous:
                raise StorageError("The notebook changed while saving. Saving stopped; edits remain in memory.")
            try:
                atomic_write(self.path, raw)
            except OSError:
                # A directory fsync can fail after replace: permit a safe retry of our own write.
                if self.current_bytes() == raw:
                    self.expected = raw
                raise
            self.expected = raw
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StorageError(f"Could not save: {exc}") from exc
