"""Developer-only visual check with disposable example data."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.main import configure_style
from app.models import Notebook, uid
from app.storage import Store
from app.ui.window import Window

app = QApplication([])
configure_style(app)
store = Store(tempfile.mkdtemp(prefix="getitdone-preview-"))
book = Notebook(store.load())
cat = {"id": uid(), "name": "Product", "color": "#3565c7"}
book.data["categories"].append(cat)
a = book.add("Prepare API alignment for the next release")
book.update(
    a["id"],
    category_id=cat["id"],
    notes="Collect open questions from refinement.\nRecord decisions in the knowledge area.",
)
b = book.add("Get feedback on the data model", parent=a["id"])
book.update(
    b["id"],
    reminder={"at": (datetime.now().astimezone() + timedelta(hours=1)).isoformat(), "notified_at": None},
)
c = book.add("Verify optional fields", parent=b["id"])
book.add("Review acceptance criteria with the team")
book.add("Document technical findings")
book.data["sessions"].append(
    {
        "id": uid(),
        "item_id": a["id"],
        "agent": "codex",
        "native_session_id": None,
        "workdir": str(Path.cwd()),
        "title": "API data model",
        "created_at": datetime.now().astimezone().isoformat(),
    }
)
window = Window(store, book.data)
window.show()


def capture():
    window.grab().save("/tmp/getitdone-preview.png")
    window.tray.hide()
    window.quitting = True
    app.quit()


QTimer.singleShot(600, capture)
app.exec()
