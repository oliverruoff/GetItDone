"""Validated, atomic storage; damaged or future files must never be overwritten."""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

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
    settings = data["settings"]
    for key in ("default_workdir", "default_agent", "knowledge_folder", "knowledge_last_file"):
        if key in settings and not isinstance(settings[key], str):
            fail(f"Invalid setting: {key}")
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


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "notebook.json"
        self.backup = self.folder / "notebook.backup.json"
        self.writable = False

    def load(self):
        try:
            data = (
                validate(json.loads(self.path.read_text(encoding="utf-8")))
                if self.path.exists()
                else empty_data()
            )
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StorageError(
                f"Could not load data: {exc}. The original file and backup have been preserved."
            ) from exc
        self.writable = True
        return data

    def save(self, data):
        if not self.writable:
            raise StorageError("Saving is blocked because data could not be loaded successfully.")
        validate(data)
        temp = None
        try:
            fd, temp = tempfile.mkstemp(prefix=".notebook-", suffix=".tmp", dir=self.folder)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                validate(json.loads(self.path.read_text(encoding="utf-8")))
                backup_temp = self.backup.with_suffix(".tmp")
                shutil.copy2(self.path, backup_temp)
                os.replace(backup_temp, self.backup)
            os.replace(temp, self.path)
            temp = None
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StorageError(f"Could not save: {exc}") from exc
        finally:
            if temp and Path(temp).exists():
                Path(temp).unlink()
