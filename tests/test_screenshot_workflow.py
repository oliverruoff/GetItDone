"""End-to-end task actions and reminder failures through the actual main window."""

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from app.models import Notebook
from app.storage import Store
from app.ui.window import Window


def test_add_copy_delete_cleanup_and_failed_reminder(qtbot, tmp_path, monkeypatch):
    store = Store(tmp_path)
    book = Notebook(store.load())
    parent = book.add("Parent")
    book.add("Existing child", parent["id"])
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.timer.stop()
    window.show()
    try:
        tasks = window.tasks
        row = tasks.rows[parent["id"]]
        assert not row.isExpanded()
        row.setExpanded(True)
        QApplication.processEvents()
        plus_row = row.child(row.childCount() - 1)
        plus = tasks.tree.itemWidget(plus_row, 0).findChild(QPushButton)
        qtbot.mouseClick(plus, Qt.LeftButton, pos=QPoint(plus.width() - 3, plus.height() // 2))
        editor = tasks.tree.findChild(QLineEdit)
        assert editor is not None and editor.hasFocus()
        qtbot.keyClicks(editor, "New child")
        new = window.notebook.children(parent["id"])[-1]
        assert new["text"] == "New child"
        assert not tasks.rows[new["id"]].isExpanded()
        qtbot.keyClick(editor, Qt.Key_Escape)
        qtbot.waitUntil(lambda: tasks.tree.findChild(QLineEdit) is None)
        controls = {b.accessibleName(): b for b in tasks.tree.itemWidget(tasks.rows[new["id"]], 4)
                    .findChildren(QPushButton)}
        qtbot.mouseClick(controls["Copy item text"], Qt.LeftButton)
        assert QApplication.clipboard().text() == "New child"
        qtbot.mouseClick(controls["Delete item"], Qt.LeftButton)
        assert window.notebook.get(new["id"]) is None
        assert all(i["id"] != new["id"] for i in Store(tmp_path).load()["items"])
        monkeypatch.setattr("app.ui.window.confirm", lambda *args: False)
        controls = {b.accessibleName(): b for b in tasks.tree.itemWidget(tasks.rows[parent["id"]], 4)
                    .findChildren(QPushButton)}
        qtbot.mouseClick(controls["Delete item"], Qt.LeftButton)
        assert window.notebook.get(parent["id"]) is not None  # Cancel preserves subtree.
        window.complete(parent["id"], True)
        assert tasks.rows[parent["id"]].font(0).strikeOut()
        tasks.expire_undo(parent["id"])
        assert parent["id"] in tasks.rows
        qtbot.mouseClick(tasks.cleanup_button, Qt.LeftButton)
        assert not tasks.rows and len(window.notebook.items) == 2
        tasks.status.setCurrentIndex(2)
        assert len(tasks.rows) == 2
        window.complete(parent["id"], False)
        at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        reminder = {"at": at}
        window.notebook.update(parent["id"], reminder=reminder)
        window.reminders.changed(parent["id"])
        sends = []

        def rejected(item):
            sends.append(item["id"])
            window.notifier.native_result.emit(item["id"], False, "Windows notifications are disabled.")

        monkeypatch.setattr(window.notifier, "send", rejected)
        window.tick()
        assert sends == [parent["id"]]
        assert reminder["notified_at"] is None
        saved = next(i for i in Store(tmp_path).load()["items"] if i["id"] == parent["id"])
        assert saved["reminder"]["notified_at"] is None
        window.tick()
        assert len(sends) == 1  # No notification flood while permissions are blocked.
        monkeypatch.setattr("app.ui.window.confirm", lambda *args: True)
        window.tasks.tree.setCurrentItem(window.tasks.rows[parent["id"]])
        window.delete_item()
        assert not Store(tmp_path).load()["items"]
    finally:
        window.timer.stop()
        window.scheduler.shutdown()
        window.saver.stop()
        window.tray.hide()
        window.quitting = True
        window.close()
