import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QLineEdit, QStyleOptionViewItem

from app.models import Notebook
from app.ui.tasks import ROLE, Tasks


def test_direct_child_counts_exclude_notes_sessions_and_filtering(qtbot):
    book = Notebook()
    parent = book.add("Parent")
    first = book.add("First child", parent["id"])
    second = book.add("Second child", parent["id"])
    grandchild = book.add("Grandchild", first["id"])
    book.update(parent["id"], notes="A note is not a subtask")
    book.data["sessions"].append(dict(id="session", item_id=parent["id"], workdir=".", title="Session", agent="test"))
    tasks = Tasks(book, {})
    qtbot.addWidget(tasks)
    tasks.resize(1200, 600)
    tasks.show()

    assert tasks.rows[parent["id"]].data(0, ROLE + 6) == "2"
    assert tasks.rows[first["id"]].data(0, ROLE + 6) == "1"
    assert tasks.rows[second["id"]].data(0, ROLE + 6) == ""
    assert tasks.rows[grandchild["id"]].data(0, ROLE + 6) == ""

    row = tasks.rows[parent["id"]]
    index = tasks.tree.indexFromItem(row)
    delegate = tasks.tree.itemDelegate()
    option = QStyleOptionViewItem()
    option.rect = tasks.tree.visualRect(index)
    delegate.initStyleOption(option, index)
    with_count = delegate.title_rect(option, index)
    count_area = option.rect.adjusted(option.rect.width() - 24, 2, -2, -2)
    count_image = tasks.tree.viewport().grab(count_area).toImage()
    row.setData(0, ROLE + 6, "")
    without_count = delegate.title_rect(option, index)
    assert with_count.right() < without_count.right()
    assert count_image != tasks.tree.viewport().grab(count_area).toImage()
    tasks.rebuild()
    assert not tasks.tree.viewport().grab().isNull()

    tasks.search.setText("First child")
    assert second["id"] not in tasks.rows
    assert tasks.rows[parent["id"]].data(0, ROLE + 6) == "2"
    assert all(row.toolTip(0) == "" for row in tasks.rows.values())

    tasks.search.clear()
    tasks.drop_item(second["id"], first["id"], None)
    assert tasks.rows[parent["id"]].data(0, ROLE + 6) == "1"
    assert tasks.rows[first["id"]].data(0, ROLE + 6) == "2"
    book.delete(second["id"])
    book.delete(grandchild["id"])
    tasks.rebuild()
    assert tasks.rows[first["id"]].data(0, ROLE + 6) == ""


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Enter])
def test_enter_commits_existing_title_without_requesting_another_task(qtbot, key):
    book = Notebook()
    item = book.add("Original")
    tasks = Tasks(book, {})
    qtbot.addWidget(tasks)
    tasks.show()
    requests = []
    tasks.new_requested.connect(requests.append)
    tasks.tree.editItem(tasks.rows[item["id"]], 0)
    editor = tasks.tree.findChild(QLineEdit)
    editor.selectAll()
    qtbot.keyClicks(editor, "Updated")
    qtbot.keyClick(editor, key)
    qtbot.waitUntil(lambda: tasks.tree.state() != QAbstractItemView.EditingState)
    qtbot.wait(20)
    assert item["text"] == "Updated"
    assert tasks.rows[item["id"]].text(0) == "Updated"
    assert len(book.items) == 1
    assert requests == []
    assert tasks.tree.findChild(QLineEdit) is None
