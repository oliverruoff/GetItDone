from copy import deepcopy

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication

from app.main import configure_style
from app.models import Notebook
from app.ui.tasks import ROLE, Tasks


@pytest.fixture
def tasks(qtbot):
    configure_style(QApplication.instance())
    book = Notebook()
    parent = book.add("Parent")
    book.add("Child", parent=parent["id"])
    book.add("Second")
    book.add("Third")
    book.data["settings"]["task_view"] = {"expanded": {i["id"]: True for i in book.items}}
    widget = Tasks(book, {})
    qtbot.addWidget(widget)
    widget.resize(1000, 600)
    widget.show()
    QApplication.processEvents()
    return widget


class DragEvent:
    def __init__(self, tree, position, external=False):
        self.tree = tree
        self.point = QPointF(position)
        self.external = external
        self.accepted = False
        self.action = None

    def source(self):
        return None if self.external else self.tree

    def position(self):
        return self.point

    def setDropAction(self, action):
        self.action = action

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def test_drag_preview_creates_space_without_changing_notebook(tasks):
    tree = tasks.tree
    parent, child, second, third = tasks.notebook.items
    tree.setCurrentItem(tasks.rows[third["id"]])
    target = tasks.rows[second["id"]]
    rect = tree.visualItemRect(target)
    before = deepcopy(tasks.notebook.data)
    changes = []
    tasks.changed.connect(lambda: changes.append(True))
    event = DragEvent(tree, QPoint(rect.center().x(), rect.top() + 1))
    tree.dragEnterEvent(event)
    assert event.accepted
    tree.dragMoveEvent(event)
    assert event.accepted
    preview = tree.drop_preview
    assert preview.data(0, ROLE + 1) == "drop-preview"
    assert preview.parent() is None
    assert tree.preview_target == (None, second["id"])
    assert tree.visualItemRect(target).top() > rect.top()
    assert tree.visualItemRect(preview).height() >= 28
    assert tasks.notebook.data == before
    assert changes == []

    # Hovering over the newly opened gap must not jitter or select another target.
    event.point = QPointF(tree.visualItemRect(preview).center())
    tree.dragMoveEvent(event)
    assert tree.drop_preview is preview
    tree.dropEvent(event)
    assert event.accepted
    assert tree.drop_preview is None
    assert [item["id"] for item in tasks.notebook.children()] == [parent["id"], third["id"], second["id"]]
    assert child["parent_id"] == parent["id"]
    assert len(tasks.rows) == 4
    assert changes == [True]


def test_child_preview_is_indented_and_cancel_restores_collapsed_parent(tasks):
    tree = tasks.tree
    parent, _, _, third = tasks.notebook.items
    target = tasks.rows[parent["id"]]
    target.setExpanded(False)
    before = deepcopy(tasks.notebook.data)
    tree.setCurrentItem(tasks.rows[third["id"]])
    event = DragEvent(tree, tree.visualItemRect(target).center())
    tree.dragMoveEvent(event)
    assert tree.drop_preview.parent() is target
    assert target.isExpanded()
    assert tree.visualItemRect(tree.drop_preview).left() > tree.visualItemRect(target).left()
    assert tasks.notebook.data == before
    tree.dragLeaveEvent(event)
    assert tree.drop_preview is None
    assert not target.isExpanded()
    assert tasks.notebook.data == before


def test_drop_on_collapsed_parent_keeps_moved_subtree_visible(tasks):
    tree = tasks.tree
    parent, child, second, _ = tasks.notebook.items
    target = tasks.rows[second["id"]]
    target.setExpanded(False)
    tree.setCurrentItem(tasks.rows[parent["id"]])
    event = DragEvent(tree, tree.visualItemRect(target).center())
    tree.dragMoveEvent(event)
    event.point = QPointF(tree.visualItemRect(tree.drop_preview).center())
    tree.dropEvent(event)
    assert parent["parent_id"] == second["id"]
    assert child["parent_id"] == parent["id"]
    assert tasks.rows[second["id"]].isExpanded()
    assert tree.visualItemRect(tasks.rows[parent["id"]]).isValid()
    assert tree.visualItemRect(tasks.rows[child["id"]]).isValid()
    assert len(tasks.rows) == 4


def test_native_drag_return_does_not_delete_rebuilt_rows(tasks, monkeypatch):
    tree = tasks.tree
    parent, child, second, _ = tasks.notebook.items
    tree.setCurrentItem(tasks.rows[parent["id"]])
    calls = []

    class NativeDrag:
        def __init__(self, owner):
            assert owner is tree

        def setMimeData(self, data):
            assert data.hasFormat("application/x-qabstractitemmodeldatalist")

        def setPixmap(self, pixmap):
            assert not pixmap.isNull()

        def setHotSpot(self, point):
            assert point.y() > 0

        def exec(self, action):
            calls.append(action)
            event = DragEvent(tree, tree.visualItemRect(tasks.rows[second["id"]]).center())
            tree.dragMoveEvent(event)
            event.point = QPointF(tree.visualItemRect(tree.drop_preview).center())
            tree.dropEvent(event)
            assert event.accepted
            return Qt.MoveAction

        def deleteLater(self):
            pass

    monkeypatch.setattr("app.ui.tasks.QDrag", NativeDrag)
    tree.startDrag(Qt.MoveAction)
    assert calls == [Qt.MoveAction]
    assert tree.drag_id is None
    assert tree.drop_preview is None
    assert parent["parent_id"] == second["id"]
    assert child["parent_id"] == parent["id"]
    assert len(tasks.rows) == 4
    assert tree.topLevelItemCount() == 2
    assert tree.currentItem() is tasks.rows[parent["id"]]


@pytest.mark.parametrize("external", [False, True])
def test_invalid_drop_preserves_all_items_and_clears_preview(tasks, external):
    tree = tasks.tree
    parent, child, _, _ = tasks.notebook.items
    tree.setCurrentItem(tasks.rows[parent["id"]])
    before = deepcopy(tasks.notebook.data)
    event = DragEvent(tree, tree.visualItemRect(tasks.rows[child["id"]]).center(), external)
    tree.dragMoveEvent(event)
    assert not event.accepted
    assert tree.drop_preview is None
    tree.dropEvent(event)
    assert not event.accepted
    assert tasks.notebook.data == before
    assert len(tasks.rows) == 4


def test_drop_in_empty_area_outdents_and_places_at_end(tasks):
    tree = tasks.tree
    parent, child, second, third = tasks.notebook.items
    tree.setCurrentItem(tasks.rows[child["id"]])
    event = DragEvent(tree, QPoint(100, tree.viewport().height() - 40))
    tree.dragMoveEvent(event)
    assert tree.preview_target == (None, None)
    tree.dropEvent(event)
    assert child["parent_id"] is None
    assert [item["id"] for item in tasks.notebook.children()] == [
        parent["id"], second["id"], third["id"], child["id"],
    ]
    assert len(tasks.rows) == 4


def test_rebuild_during_drag_clears_temporary_rows(tasks):
    tree = tasks.tree
    parent, _, second, _ = tasks.notebook.items
    tree.drag_id = parent["id"]
    tree.setCurrentItem(tasks.rows[parent["id"]])
    event = DragEvent(tree, tree.visualItemRect(tasks.rows[second["id"]]).center())
    tree.dragMoveEvent(event)
    assert tree.drop_preview is not None
    tasks.rebuild()
    assert tree.drop_preview is None
    assert tree.drag_source() is tasks.rows[parent["id"]]
    tree.drag_id = None
