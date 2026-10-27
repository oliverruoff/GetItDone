"""Capture the user guide with disposable example data, without starting an agent."""

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.main import configure_style
from app.models import Notebook, uid
from app.storage import Store
from app.terminal.bridge import Terminal
from app.ui.colors import ColorPalette
from app.ui.dialogs import ReminderDialog
from app.ui.window import Window


def capture_guide():
    app = QApplication([])
    configure_style(app)
    output = Path(__file__).resolve().parents[1] / "docs" / "images"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="getitdone-guide-") as temporary:
        root = Path(temporary)
        knowledge = root / "Knowledge"
        knowledge.mkdir()
        (knowledge / "Release notes.txt").write_text(
            "Release planning\n\nGoal\nMake the next release easy to use.\n\n"
            "Decisions\n• Keep tasks short and actionable.\n• Collect details in task notes.\n"
            "• Keep reference documents in this Knowledge folder.\n\n"
            "Next review\nCheck the documentation and confirm the release checklist.\n",
            encoding="utf-8",
        )
        (knowledge / "Meeting notes.txt").write_text("Team review\n\nDiscuss the release checklist.\n", encoding="utf-8")
        (knowledge / "Project overview.md").write_text("# Project overview\n\nA small, focused release.\n", encoding="utf-8")
        store = Store(root / "Notebook")
        book = Notebook(store.load())
        book.data["settings"]["knowledge_folder"] = str(knowledge)
        category = {"id": uid(), "name": "Release", "color": "#d1dcf5"}
        book.data["categories"].append(category)
        parent = book.add("Prepare the next release")
        book.update(parent["id"], category_id=category["id"], notes="Collect feedback from the team.\nCheck the documentation before publishing.")
        child = book.add("Review the user guide", parent=parent["id"])
        book.update(child["id"], reminder={"at": "2026-10-28T09:00:00+01:00", "notified_at": None})
        book.add("Capture screenshots", parent=child["id"])
        book.add("Test the new task workflow", parent=parent["id"])
        book.add("Plan next week's priorities")
        book.add("Collect ideas for the next milestone")
        window = Window(store, book.data)
        window.resize(1280, 850)
        window.show()
        window.vertical.setSizes([550, 180])
        window.timer.stop()
        QTest.qWait(650)

        def save(widget, name):
            QTest.qWait(200)
            pixmap = widget.grab()
            pixmap.setDevicePixelRatio(1)
            pixmap = pixmap.scaledToWidth(min(pixmap.width(), 1600), Qt.SmoothTransformation)
            assert pixmap.save(str(output / name))

        save(window, "tasks.png")
        palette = ColorPalette(category["color"], window)
        palette.show()
        save(palette, "colors.png")
        palette.close()
        reminder = ReminderDialog(book.get(child["id"]), window)
        reminder.when.setDateTime(QDateTime.fromString("2026-10-28T09:00:00+01:00", Qt.ISODate))
        reminder.show()
        save(reminder, "reminder.png")
        reminder.close()
        window.workspace.setCurrentIndex(1)
        files = window.knowledge.files
        for index in range(files.count()):
            if files.item(index).text().startswith("Release notes"):
                assert files.item(index).data(Qt.UserRole)
                files.setCurrentRow(index)
                break
        QTest.qWait(800)
        assert window.knowledge.document is not None
        save(window, "knowledge.png")
        window.workspace.setCurrentIndex(0)
        terminal = Terminal(window)
        window.tabs.addTab(terminal, "Demo shell · no agent running")
        window.tabs.setCurrentWidget(terminal)
        window.vertical.setSizes([380, 350])
        terminal.start(["/bin/sh"], temporary)
        QTest.qWait(800)
        terminal.input("printf '\\033[2J\\033[HGetItDone - terminal example\\n\\nThis is a local demo shell. No AI agent is running.\\n\\nUse the toolbar to paste, copy, interrupt, maximize or pop out.\\n'\n")
        QTest.qWait(500)
        save(window, "terminals.png")
        terminal.stop()
        QTest.qWait(200)
        terminal.close()
        window.timer.stop()
        window.saver.stop()
        window.tray.hide()
        window.quitting = True
        window.close()
        app.processEvents()


if __name__ == "__main__":
    if os.name != "posix":
        raise SystemExit("The screenshot demo currently requires a POSIX shell.")
    capture_guide()
