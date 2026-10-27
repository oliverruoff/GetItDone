from datetime import datetime

import pytest
from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QDialogButtonBox, QPushButton

from app.main import configure_style
from app.models import Notebook, now_iso, uid
from app.storage import Store
from app.ui.colors import PALETTE
from app.ui.dialogs import ReminderDialog
from app.ui.tasks import ROLE
from app.ui.window import Window


@pytest.fixture
def notebook(qtbot, tmp_path):
    configure_style(QApplication.instance())
    store = Store(tmp_path)
    book = Notebook(store.load())
    item = book.add("Parent item")
    child = book.add("Child item", parent=item["id"])
    grandchild = book.add("Grandchild item", parent=child["id"])
    next_root = book.add("Next parent")
    window = Window(store, book.data)
    window.timer.stop()
    qtbot.addWidget(window)
    window.show()
    yield window, item, child, grandchild, next_root
    window.saver.stop()
    window.tray.hide()
    window.quitting = True


def test_palette_is_one_click_and_colors_entire_row(notebook, qtbot):
    window, item, child, *_ = notebook
    tasks = window.tasks
    assert len(PALETTE) == 16 and len({color for _, color in PALETTE}) == 16
    for name, color in PALETTE:
        qtbot.mouseClick(tasks.tree.itemWidget(tasks.rows[item["id"]], 1), Qt.LeftButton)
        popup = window.color_palette
        assert popup.isVisible()
        qtbot.mouseClick(next(b for b in popup.swatches if b.property("color") == color), Qt.LeftButton)
        assert not popup.isVisible()
        assigned = next(c for c in window.notebook.data["categories"] if c["id"] == item["category_id"])
        assert assigned["name"] == name and assigned["color"] == color
        assert child["category_id"] == item["category_id"]
        tasks.tree.clearSelection()
        tasks.tree.setCurrentItem(None)
        QApplication.processEvents()
        row = tasks.rows[item["id"]]
        bounds = tasks.tree.visualItemRect(row)
        image = tasks.tree.viewport().grab().toImage()
        # Check actual pixels in every column, including cell-widget backgrounds.
        x = 0
        for column in range(5):
            width = tasks.tree.columnWidth(column)
            assert row.data(column, ROLE + 2).name() == color
            sampled = image.pixelColor(x + width - 8, bounds.top() + 8)
            assert sampled == QColor(color), (column, color, sampled.name())
            x += width
    assert window.flush()
    saved = Store(window.store.folder).load()
    assert saved["items"][0]["category_id"] == item["category_id"]
    assert tasks.tree.columnWidth(1) <= 60
    qtbot.mouseClick(tasks.tree.itemWidget(tasks.rows[item["id"]], 1), Qt.LeftButton)
    qtbot.mouseClick(window.color_palette.findChild(QPushButton), Qt.LeftButton)
    assert item["category_id"] is None


def test_save_reminder_creates_displays_persists_and_fires_once(notebook, qtbot, monkeypatch):
    window, item, *_ = notebook
    window.tasks.tree.setCurrentItem(window.tasks.rows[item["id"]])
    when = QDateTime.currentDateTime().addSecs(-10)

    def save_dialog():
        dialog = next(
            w for w in QApplication.topLevelWidgets() if isinstance(w, ReminderDialog) and w.isVisible()
        )
        assert isinstance(dialog, ReminderDialog)
        assert not dialog.findChildren(QCheckBox)
        dialog.when.setDateTime(when)
        qtbot.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save), Qt.LeftButton)

    QTimer.singleShot(0, save_dialog)
    window.reminder_dialog()
    assert item["reminder"] is not None
    assert datetime.fromisoformat(item["reminder"]["at"]).timestamp() == when.toSecsSinceEpoch()
    row = window.tasks.rows[item["id"]]
    button = window.tasks.tree.itemWidget(row, 2)
    assert button.text() and "Overdue" in button.text()
    assert window.flush()
    assert Store(window.store.folder).load()["items"][0]["reminder"]["at"] == item["reminder"]["at"]
    sent = []
    monkeypatch.setattr(window.notifier, "send", lambda value: sent.append(value["id"]))
    window.tick()
    window.tick()
    assert sent == [item["id"]]
    assert Store(window.store.folder).load()["items"][0]["reminder"]["notified_at"]

    def remove_dialog():
        dialog = next(
            w for w in QApplication.topLevelWidgets() if isinstance(w, ReminderDialog) and w.isVisible()
        )
        button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Remove reminder")
        qtbot.mouseClick(button, Qt.LeftButton)

    QTimer.singleShot(0, remove_dialog)
    window.reminder_dialog()
    assert item["reminder"] is None
    assert window.tasks.tree.itemWidget(window.tasks.rows[item["id"]], 2).text() == ""


def test_hierarchy_and_session_actions_are_clear_and_english(notebook):
    window, root, child, grandchild, next_root = notebook
    tasks = window.tasks
    rows = tasks.rows
    assert rows[child["id"]].parent() is rows[root["id"]]
    assert rows[grandchild["id"]].parent() is rows[child["id"]]
    assert rows[next_root["id"]].parent() is None
    assert rows[root["id"]].font(0).bold()
    assert not rows[child["id"]].font(0).bold()
    assert rows[root["id"]].data(0, ROLE + 4) == rows[grandchild["id"]].data(0, ROLE + 4)
    assert rows[next_root["id"]].data(0, ROLE + 4) != rows[root["id"]].data(0, ROLE + 4)
    assert tasks.tree.indentation() >= 30
    session = dict(
        id=uid(),
        item_id=root["id"],
        agent="codex",
        title="Saved session",
        workdir=str(window.store.folder),
        native_session_id=None,
        created_at=now_iso(),
    )
    window.notebook.data["sessions"].append(session)
    tasks.rebuild()
    actions = tasks.tree.itemWidget(tasks.session_rows[session["id"]], 4)
    buttons = actions.findChildren(QPushButton)
    assert [b.text() for b in buttons] == ["Resume", ""]
    assert buttons[1].accessibleName() == "Session details"
    item_buttons = tasks.tree.itemWidget(tasks.rows[root["id"]], 4).findChildren(QPushButton)
    assert all(not button.text() and button.toolTip() and button.accessibleName() for button in item_buttons)
    assert window.workspace.tabText(0) == "Tasks" and window.workspace.tabText(1) == "Knowledge"
    assert [tasks.status.itemText(n) for n in range(3)] == ["Open", "Completed", "All"]
    assert tasks.tree.headerItem().text(1) == "Color"


def test_compact_rows_and_terminal_window_roundtrip(notebook, qtbot):
    window, item, child, grandchild, _ = notebook
    tree = window.tasks.tree
    assert tree.headerItem().text(0) == "Todos"
    assert tree.columnWidth(2) <= 125
    assert tree.columnWidth(3) <= 100
    assert tree.visualItemRect(window.tasks.rows[item["id"]]).height() <= 30
    window.set_row_color(item["id"], ("Blue", "#335577"))
    assert item["category_id"] == child["category_id"] == grandchild["category_id"]
    added = window.notebook.add("New child", parent=item["id"])
    assert added["category_id"] == item["category_id"]
    window.toggle_terminal_maximized()
    assert window.tasks.isHidden()
    window.toggle_terminal_maximized()
    assert not window.tasks.isHidden()
    tabs = window.tabs
    window.toggle_terminal_popout()
    assert window.terminal_popout.isVisible()
    assert window.tabs is tabs
    assert window.terminal_panel.window() is window.terminal_popout
    window.terminal_popout.close()
    assert window.terminal_popout is None
    assert window.vertical.indexOf(window.terminal_panel) == 1


def test_reminder_popup_cancels_on_outside_click(notebook, qtbot):
    window, item, *_ = notebook
    dialog = ReminderDialog(item, window)
    qtbot.addWidget(dialog)
    dialog.move(window.mapToGlobal(window.rect().center()))
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    from PySide6.QtTest import QTest

    QTest.mouseClick(
        window.windowHandle(),
        Qt.LeftButton,
        pos=window.tasks.search.mapTo(window, window.tasks.search.rect().center()),
    )
    qtbot.waitUntil(lambda: not dialog.isVisible())
    assert dialog.result() == 0
    assert item["reminder"] is None
