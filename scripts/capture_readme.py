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
        book.update(child["id"], reminder={"at": "2030-10-28T09:00:00+01:00", "notified_at": None})
        book.add("Capture screenshots", parent=child["id"])
        book.add("Test the new task workflow", parent=parent["id"])
        planning = book.add("Plan next week's priorities")
        ideas = book.add("Collect ideas for the next milestone")
        green = {"id": uid(), "name": "Planning", "color": "#cce6d4"}
        orange = {"id": uid(), "name": "Ideas", "color": "#f4d9bb"}
        book.data["categories"].extend([green, orange])
        book.update(planning["id"], category_id=green["id"])
        book.update(ideas["id"], category_id=orange["id"])
        book.add("Prioritize customer feedback", parent=planning["id"])
        book.add("Draft the roadmap", parent=planning["id"])
        book.data["scheduled_jobs"] = [{
            "id": uid(), "title": "Weekly project summary", "prompt": "Summarize the project status.",
            "agent": "codex", "workdir": str(root / "Example project"), "enabled": True,
            "next_at": "2030-11-04T09:00:00+00:00", "every": 1, "unit": "weeks", "runs": [{
                "id": uid(), "agent": "codex", "workdir": str(root / "Example project"),
                "prompt": "Summarize the project status.", "started_at": "2030-10-28T09:00:00+00:00",
                "finished_at": "2030-10-28T09:01:12+00:00", "status": "completed",
                "output": "Example output: Documentation updated. Next: review the release checklist.",
            }],
        }]
        canvas = store.folder / "canvas"
        canvas.mkdir(parents=True, exist_ok=True)
        (canvas / "canvas.html").write_text('''<!doctype html><html><head><meta charset="utf-8"><style>
body{font:16px system-ui;background:#f2f5f9;color:#23364c;margin:0;padding:48px}
main{max-width:960px;margin:auto} h1{font-size:38px;margin-bottom:6px} p{color:#5a6b7c}
.grid{display:flex;gap:18px;margin-top:32px}.card{background:white;border-radius:14px;padding:24px;flex:1;box-shadow:0 4px 20px #21314a12}
.tag{font-size:13px;color:#5079a4;font-weight:700} h2{font-size:20px} li{margin:12px 0;line-height:1.5}
</style></head><body><main><span class="tag">PROJECT WORKSPACE · EXAMPLE</span>
<h1>Release planning</h1><p>A simple Canvas built with local HTML and CSS.</p><div class="grid">
<section class="card"><span class="tag">THIS WEEK</span><h2>Priorities</h2><ul><li>Review the user guide</li><li>Capture fresh screenshots</li><li>Test the release workflow</li></ul></section>
<section class="card"><span class="tag">NEXT UP</span><h2>Ideas &amp; notes</h2><ul><li>Collect team feedback</li><li>Polish the onboarding experience</li><li>Plan the next milestone</li></ul></section>
</div></main></body></html>''', encoding="utf-8")
        window = Window(store, book.data)
        window.resize(1280, 850)
        window.show()
        window.vertical.setSizes([550, 180])
        window.timer.stop()
        window.tasks.set_all_expanded(True)
        QTest.qWait(650)

        def save(widget, name):
            QTest.qWait(200)
            pixmap = widget.grab()
            pixmap.setDevicePixelRatio(1)
            pixmap = pixmap.scaledToWidth(min(pixmap.width(), 1600), Qt.SmoothTransformation)
            assert pixmap.save(str(output / name))

        save(window, "tasks-overview-2026.png")
        configure_style(app, "everforest")
        window.tasks.refresh_categories()
        window.tasks.rebuild()
        QTest.qWait(400)
        save(window, "tasks-dark-2026.png")
        configure_style(app, "light")
        window.tasks.refresh_categories()
        window.tasks.rebuild()
        QTest.qWait(400)
        palette = ColorPalette(category["color"], window)
        palette.show()
        save(palette, "colors-2026.png")
        palette.close()
        reminder = ReminderDialog(book.get(child["id"]), window)
        reminder.when.setDateTime(QDateTime.fromString("2030-10-28T09:00:00+01:00", Qt.ISODate))
        reminder.show()
        save(reminder, "reminder-2026.png")
        reminder.close()
        window.workspace.setCurrentIndex(1)
        QTest.qWait(1500)  # Lazy tab initialization and asynchronous folder discovery.
        files = window.knowledge.files
        for index in range(files.count()):
            if files.item(index).text().startswith("Release notes"):
                assert files.item(index).data(Qt.UserRole)
                files.setCurrentRow(index)
                break
        QTest.qWait(800)
        assert window.knowledge.document is not None
        save(window, "knowledge-2026.png")
        window.workspace.setCurrentIndex(2)
        QTest.qWait(2000)
        save(window, "canvas-2026.png")
        window.workspace.setCurrentIndex(4)
        QTest.qWait(1500)
        save(window, "scheduled-2026.png")
        window.workspace.setCurrentIndex(0)
        terminal = Terminal(window)
        window.tabs.addTab(terminal, "Demo shell · no agent running")
        window.tabs.setCurrentWidget(terminal)
        window.vertical.setSizes([380, 350])
        terminal.start(["/bin/sh"], temporary)
        QTest.qWait(800)
        terminal.input("printf '\\033[2J\\033[HGetItDone - terminal example\\n\\nThis is a local demo shell. No AI agent is running.\\n\\nUse the toolbar to paste, copy, interrupt, maximize or pop out.\\n'\n")
        QTest.qWait(500)
        save(window, "terminals-2026.png")
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
