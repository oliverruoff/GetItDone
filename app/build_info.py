"""Identify the code actually loaded, rather than only the package version."""

import hashlib
import json
import sys
from pathlib import Path


def source_revision(root=None):
    root = Path(root) if root else Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.name == "build-info.json":
            continue
        if path.suffix not in {".py", ".js", ".html", ".css", ".svg"}:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def revision():
    if getattr(sys, "frozen", False):
        path = Path(sys._MEIPASS) / "app/build-info.json"
        return json.loads(path.read_text(encoding="utf-8"))["revision"]
    return source_revision()
