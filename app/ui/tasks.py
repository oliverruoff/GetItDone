import html
import re
from datetime import datetime, timezone

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QPen, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleFactory,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.colors import text_color
from app.ui.completion import CompletionOverlay
from app.ui.icons import icon, icon_button

ROLE = Qt.UserRole


class ItemDelegate(QStyledItemDelegate):
    next_item = Signal(bool, bool)
    text_edited = Signal(str, str)

    def __init__(self, parent):
        super().__init__(parent)
        self.cell_style = QStyleFactory.create("Fusion")

    def paint(self, painter, option, index):
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)
        background = index.data(ROLE + 2) or QColor("#ffffff")
        painter.save()
        painter.fillRect(cell.rect, background)
        cell.state &= ~(QStyle.State_Selected | QStyle.State_HasFocus)
        cell.backgroundBrush = QBrush(background)
        title = index.column() == 0 and index.data(ROLE + 1) == "item"
        if title:
            cell.text = ""
        self.cell_style.drawControl(QStyle.CE_ItemViewItem, cell, painter, cell.widget)
        if title:
            rect = self.cell_style.subElementRect(QStyle.SE_ItemViewItemText, cell, cell.widget)
            document = self.title_document(index, rect.width())
            painter.save()
            painter.setClipRect(rect)
            painter.translate(
                rect.left(), rect.top() + max(0, (rect.height() - document.size().height()) / 2)
            )
            document.drawContents(painter)
            painter.restore()
        if cell.features & QStyleOptionViewItem.HasCheckIndicator:
            indicator = self.cell_style.subElementRect(
                QStyle.SE_ItemViewItemCheckIndicator, cell, cell.widget
            )
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#62768d"), 1.4))
            painter.drawRoundedRect(indicator.adjusted(1, 1, -1, -1), 2, 2)
            if cell.checkState == Qt.Checked:
                painter.setPen(QPen(QColor("#244e79"), 2.4))
                center = indicator.center()
                painter.drawLine(center.x() - 5, center.y(), center.x() - 1, center.y() + 4)
                painter.drawLine(center.x() - 1, center.y() + 4, center.x() + 6, center.y() - 5)
        painter.setPen(QColor("#cbd4e0"))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(cell.rect.bottomLeft(), cell.rect.bottomRight())
        if index.siblingAtColumn(0).data(ROLE + 1) == "item" and index.data(ROLE + 3) == 0:
            painter.setPen(QPen(QColor("#9aaec7"), 2))
            painter.drawLine(cell.rect.topLeft(), cell.rect.topRight())
        painter.restore()

    def title_document(self, index, width):
        document = QTextDocument()
        document.setDefaultFont(index.data(Qt.FontRole))
        source = index.data(Qt.DisplayRole) or ""
        parts, end = [], 0
        for match in re.finditer(r"\[([^\]]+)\]\((https?://[^\s)]+)\)|https?://[^\s<>]+", source):
            parts.append(html.escape(source[end : match.start()]))
            url = match[2] or match[0]
            label = match[1] or url
            parts.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>')
            end = match.end()
        parts.append(html.escape(source[end:]))
        text = "".join(parts).replace("\n", "<br>")
        color = index.data(Qt.ForegroundRole).color().name()
        document.setDefaultStyleSheet(
            f"body {{color: {color};}} a {{color: {color}; text-decoration: underline;}}"
        )
        document.setHtml("<body>" + text + "</body>")
        document.setDocumentMargin(0)
        document.setTextWidth(max(40, width))
        return document

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if index.column() == 0 and index.data(ROLE + 5):
            cell = QStyleOptionViewItem(option)
            self.initStyleOption(cell, index)
            cell.rect.setWidth(self.parent().columnWidth(0))
            rect = self.cell_style.subElementRect(QStyle.SE_ItemViewItemText, cell, cell.widget)
            size.setHeight(
                max(size.height(), int(self.title_document(index, rect.width()).size().height()) + 6)
            )
        return size

    def updateEditorGeometry(self, editor, option, index):
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)
        rect = self.cell_style.subElementRect(QStyle.SE_ItemViewItemText, cell, cell.widget)
        rect = rect.adjusted(0, 2, -2, -2)
        if isinstance(editor, QLineEdit):
            rect.setHeight(editor.fontMetrics().height() + 8)
        editor.setGeometry(rect)

    def editorEvent(self, event, model, option, index):
        if (
            index.column() == 0
            and index.data(ROLE + 1) == "item"
            and event.type() == QEvent.MouseButtonRelease
        ):
            cell = QStyleOptionViewItem(option)
            self.initStyleOption(cell, index)
            rect = self.cell_style.subElementRect(QStyle.SE_ItemViewItemText, cell, cell.widget)
            point = event.position() - rect.topLeft()
            document = self.title_document(index, rect.width())
            point.setY(point.y() - max(0, (rect.height() - document.size().height()) / 2))
            anchor = document.documentLayout().anchorAt(point)
            if anchor and QUrl(anchor).scheme() in ("https", "http"):
                QDesktopServices.openUrl(QUrl(anchor))
                return True
        return super().editorEvent(event, model, option, index)

    def createEditor(self, parent, option, index):
        if index.column() != 0 or index.data(ROLE + 1) != "item":
            return None
        if index.data(ROLE + 5):
            editor = QPlainTextEdit(parent)
            editor.textChanged.connect(
                lambda ident=index.data(ROLE): self.text_edited.emit(ident, editor.toPlainText())
            )
        else:
            editor = super().createEditor(parent, option, index)
            editor.textEdited.connect(lambda text, ident=index.data(ROLE): self.text_edited.emit(ident, text))
        editor.setObjectName("itemTextEditor")
        editor.setFont(index.data(Qt.FontRole))
        background = index.data(ROLE + 2).name()
        foreground = index.data(Qt.ForegroundRole).color().name()
        editor.setStyleSheet(
            f"background: {background}; color: {foreground}; border: none; border-bottom: 1px solid {foreground}; padding: 0px;"
        )
        return editor

    def setEditorData(self, editor, index):
        if isinstance(editor, QPlainTextEdit):
            editor.blockSignals(True)
            editor.setPlainText(index.data(Qt.EditRole))
            editor.blockSignals(False)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QPlainTextEdit):
            model.setData(index, editor.toPlainText(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
            return True
        if event.type() == QEvent.KeyPress and event.key() in (
            Qt.Key_Return,
            Qt.Key_Enter,
            Qt.Key_Tab,
            Qt.Key_Backtab,
        ):
            key = event.key()
            backwards = key == Qt.Key_Backtab or bool(event.modifiers() & Qt.ShiftModifier)
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
            QTimer.singleShot(0, lambda: self.next_item.emit(key in (Qt.Key_Tab, Qt.Key_Backtab), backwards))
            return True
        return super().eventFilter(editor, event)


class TaskTree(QTreeWidget):
    dropped = Signal(str, object, object)
    new_requested = Signal()
    indent_requested = Signal(bool)

    def dropEvent(self, event):
        source = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        if event.source() is not self or source is None or source.data(0, ROLE + 1) != "item":
            event.ignore()
            return
        parent, before = None, None
        if target is not None and target.data(0, ROLE + 1) != "add":
            if target.data(0, ROLE + 1) != "item":
                event.ignore()
                return
            placement = self.dropIndicatorPosition()
            if placement == QAbstractItemView.OnItem:
                parent = target.data(0, ROLE)
            else:
                parent_row = target.parent()
                parent = parent_row.data(0, ROLE) if parent_row else None
                if placement == QAbstractItemView.AboveItem:
                    before = target.data(0, ROLE)
                else:
                    container = parent_row or self.invisibleRootItem()
                    index = container.indexOfChild(target) + 1
                    while index < container.childCount():
                        sibling = container.child(index)
                        if sibling.data(0, ROLE + 1) == "item":
                            before = sibling.data(0, ROLE)
                            break
                        index += 1
        self.dropped.emit(source.data(0, ROLE), parent, before)
        event.setDropAction(Qt.MoveAction)
        event.accept()

    def drawBranches(self, painter, rect, index):
        if index.data(ROLE + 1) == "add":
            painter.fillRect(rect, QColor("#ffffff"))
            return
        background = index.data(ROLE + 2) or QColor("#ffffff")
        accent = index.data(ROLE + 4) or QColor("#8799b0")
        painter.fillRect(rect, background)
        super().drawBranches(painter, rect, index)
        painter.save()
        painter.fillRect(2, rect.top(), 4, rect.height(), accent)
        depth = index.data(ROLE + 3) or 0
        painter.setPen(QPen(accent, 1))
        for level in range(depth):
            x = 17 + level * self.indentation()
            painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.restore()

    def keyPressEvent(self, event):
        if self.state() != QAbstractItemView.EditingState:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.new_requested.emit()
                return
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                self.indent_requested.emit(
                    event.key() == Qt.Key_Backtab or bool(event.modifiers() & Qt.ShiftModifier)
                )
                return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, next):
        # A tree's Tab key indents; multiline note widgets keep normal text editing.
        if self.hasFocus() and self.state() != QAbstractItemView.EditingState:
            self.indent_requested.emit(not next)
            return False
        return super().focusNextPrevChild(next)


class Tasks(QWidget):
    undo_expired = Signal(str)
    completion_undo_requested = Signal(str)
    note_delete_requested = Signal(str)
    note_undo_requested = Signal(str)
    action_requested = Signal(str, str)
    append_requested = Signal()
    changed = Signal()
    selected = Signal(str)
    session_resume = Signal(str)
    session_details = Signal(str)
    session_start = Signal()
    completion_requested = Signal(str, bool)
    new_requested = Signal(bool)
    indent_requested = Signal(bool)

    def __init__(self, notebook, terminal_lookup, parent=None):
        super().__init__(parent)
        self.notebook = notebook
        self.terminals = terminal_lookup
        self.rows = {}
        self.session_rows = {}
        self.titles_open = set()
        self.notes_open = set()
        self.notes_hidden = set()
        self.building = False
        self.completion_overlay = None
        self.undo_notices = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        filterbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search items and notes …")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.rebuild)
        self.status = QComboBox()
        for title, value in [("Open", "open"), ("Completed", "done"), ("All", "all")]:
            self.status.addItem(title, value)
        self.status.currentIndexChanged.connect(self.rebuild)
        filterbar.addWidget(self.search, 1)
        filterbar.addWidget(self.status)
        layout.addLayout(filterbar)
        hint = QLabel(
            "Check to complete · Double-click to edit · Indentation and colored rails show parent groups"
        )
        hint.setObjectName("taskHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.tree = TaskTree()
        self.tree.setObjectName("taskTree")
        self.tree.setHeaderLabels(["Todos", "Color", "Reminder", "Agent status", "Actions"])
        self.tree.setColumnWidth(0, 530)
        self.tree.setColumnWidth(1, 56)
        self.tree.setColumnWidth(2, 125)
        self.tree.setColumnWidth(3, 100)
        self.tree.setColumnWidth(4, 155)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().sectionResized.connect(lambda *_: self.tree.scheduleDelayedItemsLayout())
        self.tree.setAlternatingRowColors(False)
        self.tree.setWordWrap(True)
        self.tree.setIndentation(32)
        self.tree.setUniformRowHeights(False)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        self.tree.setDropIndicatorShown(True)
        self.tree.dropped.connect(self.drop_item)
        delegate = ItemDelegate(self.tree)
        delegate.next_item.connect(self.editor_next)
        delegate.text_edited.connect(self.edit_text)
        self.tree.setItemDelegate(delegate)
        self.tree.itemChanged.connect(self.item_changed)
        self.tree.currentItemChanged.connect(self.selection_changed)
        self.tree.new_requested.connect(lambda: self.new_requested.emit(False))
        self.tree.indent_requested.connect(self.indent_requested)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.menu)
        layout.addWidget(self.tree, 1)
        self.add_button = QPushButton("+  Add item")
        self.add_button.setObjectName("addTask")
        self.add_button.setMinimumHeight(36)
        self.add_button.clicked.connect(self.append_requested)
        layout.addWidget(self.add_button)
        self.undo_area = QWidget()
        self.undo_layout = QVBoxLayout(self.undo_area)
        self.undo_layout.setContentsMargins(0, 0, 0, 0)
        self.undo_area.hide()
        layout.addWidget(self.undo_area)
        self.tree.verticalScrollBar().valueChanged.connect(self.cancel_completion_animation)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.refresh_categories()
        self.rebuild()

    def drop_item(self, ident, parent, before):
        if self.notebook.relocate(ident, parent, before):
            self.rebuild()
            self.tree.setCurrentItem(self.rows.get(ident))
            self.changed.emit()

    def toggle_title(self, row):
        ident = row.data(0, ROLE)
        if ident in self.titles_open:
            self.titles_open.remove(ident)
        else:
            self.titles_open.add(ident)
        row.setData(0, ROLE + 5, ident in self.titles_open)
        self.tree.scheduleDelayedItemsLayout()

    def editor_next(self, indent, backwards):
        if indent:
            self.indent_requested.emit(backwards)
        else:
            self.new_requested.emit(False)

    def refresh_categories(self):
        pass  # Row colors remain available; color filtering has been removed.

    def current_id(self):
        row = self.tree.currentItem()
        while row:
            if row.data(0, ROLE + 1) == "item":
                return row.data(0, ROLE)
            row = row.parent()
        return None

    def rebuild(self, *args, select=None):
        self.cancel_completion_animation()
        selected = select or self.current_id()
        scroll = self.tree.verticalScrollBar().value()
        self.building = True
        self.tree.blockSignals(True)
        self.tree.clear()
        self.rows.clear()
        self.session_rows.clear()
        visible, direct = self.notebook.visible(self.search.text(), self.status.currentData(), None)
        cats = {c["id"]: c for c in self.notebook.data["categories"]}
        sessions = self.notebook.data["sessions"]

        def add(parent_id, parent_row=None, depth=0, accent=None):
            for number, item in enumerate(self.notebook.children(parent_id)):
                ident = item["id"]
                if ident not in visible:
                    continue
                row = QTreeWidgetItem(parent_row if parent_row else self.tree)
                self.rows[ident] = row
                row.setData(0, ROLE, ident)
                row.setData(0, ROLE + 1, "item")
                row.setData(0, ROLE + 5, ident in self.titles_open)
                rail = accent or QColor(
                    ("#4d729c", "#8a649c", "#408b81", "#ac784d", "#89764f", "#637fa3")[number % 6]
                )
                row.setFlags(row.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
                row.setCheckState(0, Qt.Checked if item["done"] else Qt.Unchecked)
                row.setText(0, item["text"])
                row.setTextAlignment(0, Qt.AlignLeft | Qt.AlignVCenter)
                row.setTextAlignment(3, Qt.AlignCenter)
                row.setSizeHint(0, QSize(100, 28))
                row.setToolTip(
                    0,
                    "Checkbox: complete · Double-click: edit text\n"
                    + item["text"]
                    + ("\n\n" + item["notes"] if item["notes"] else ""),
                )
                if ident not in direct:
                    row.setForeground(0, QBrush(QColor("#737d8c")))
                    row.setToolTip(0, "Parent context · " + row.toolTip(0))
                font = row.font(0)
                font.setStrikeOut(item["done"])
                font.setBold(depth == 0)
                font.setPointSize(11 if depth == 0 else 10)
                font.setItalic(ident not in direct)
                row.setFont(0, font)
                cat = cats.get(item["category_id"])
                tint = QColor(cat["color"] if cat else "#e8edf5" if depth == 0 else "#ffffff")
                foreground = text_color(tint.name())
                for column in range(self.tree.columnCount()):
                    row.setData(column, ROLE + 2, tint)
                    row.setData(column, ROLE + 3, depth)
                    row.setData(column, ROLE + 4, rail)
                    row.setForeground(column, QBrush(QColor(foreground)))
                category_button = QPushButton("●" if cat else "+")
                category_button.setAccessibleName("Choose row color")
                category_button.setToolTip((cat["name"] + " · " if cat else "") + "Choose row color")
                category_button.clicked.connect(
                    lambda checked=False, i=ident: self.action_requested.emit(i, "category")
                )
                self.tree.setItemWidget(row, 1, category_button)
                self.reminder_cell(row, item)
                reminder_button = QPushButton(row.text(2))
                reminder_button.setIcon(icon("bell", foreground))
                reminder_button.setAccessibleName("Set reminder")
                reminder_button.setToolTip("Set, change or remove reminder")
                reminder_button.clicked.connect(
                    lambda checked=False, i=ident: self.action_requested.emit(i, "reminder")
                )
                self.tree.setItemWidget(row, 2, reminder_button)
                linked = [s for s in sessions if s["item_id"] == ident]
                row.setText(3, str(len(linked)) if linked else "")
                actions = QWidget()
                action_layout = QHBoxLayout(actions)
                action_layout.setContentsMargins(2, 0, 2, 0)
                action_layout.setSpacing(3)
                for name, title, callback in [
                    ("note", "Edit note", lambda checked=False, i=ident: self.toggle_note(i)),
                    ("session", "New session", lambda checked=False, i=ident: self.start_at(i)),
                ]:
                    button = icon_button(name, title, callback, foreground)
                    button.setFixedSize(28, 24)
                    action_layout.addWidget(button)
                more = icon_button(
                    "more", "More actions", lambda checked=False, i=ident: self.item_menu(i), foreground
                )
                more.setFixedSize(28, 24)
                action_layout.addWidget(more)
                expand = icon_button("expand", "Show full title / collapse title", lambda: None, foreground)
                expand.setAccessibleName("Expand or collapse full title")
                expand.setToolTip("Show full title / collapse title")
                expand.setFixedSize(28, 24)
                expand.clicked.connect(lambda checked=False, r=row: self.toggle_title(r))
                action_layout.addWidget(expand)
                if tint:
                    # Cell widgets otherwise cover the item's category background.
                    actions.setObjectName("taskActions")
                    actions.setStyleSheet(f"QWidget#taskActions {{ background: {tint.name()}; }}")
                    for button in [category_button, reminder_button, *actions.findChildren(QPushButton)]:
                        button.setStyleSheet(
                            f"QPushButton {{ background: {tint.name()}; color: {foreground}; border: none; border-radius: 0; padding: 2px; }}"
                            "QPushButton:hover { border: 1px solid #46627e; background: rgba(255,255,255,45); }"
                            "QPushButton:pressed { background: rgba(0,0,0,25); }"
                        )
                self.tree.setItemWidget(row, 4, actions)
                if ident in self.notes_open or (item["notes"] and ident not in self.notes_hidden):
                    note_row = QTreeWidgetItem(row)
                    note_row.setData(0, ROLE + 1, "note")
                    for column in range(self.tree.columnCount()):
                        note_row.setData(column, ROLE + 2, tint)
                        note_row.setData(column, ROLE + 3, depth + 1)
                        note_row.setData(column, ROLE + 4, rail)
                    editor = QPlainTextEdit()
                    editor.setPlainText(item["notes"])
                    editor.setPlaceholderText("Multiline note …")
                    height = max(48, min(96, 16 + 17 * len(item["notes"].splitlines())))
                    editor.setFixedHeight(height)
                    note_row.setSizeHint(0, QSize(100, height + 5))
                    editor.textChanged.connect(lambda i=ident, e=editor: self.note_changed(i, e))
                    note_row.setFirstColumnSpanned(True)
                    container = QWidget()
                    container.setObjectName("inlineNote")
                    container.setStyleSheet(
                        f"QWidget#inlineNote, QWidget#inlineNote QPlainTextEdit {{ background: {tint.name()}; color: {foreground}; }}"
                    )
                    note_layout = QHBoxLayout(container)
                    note_layout.setContentsMargins(6, 4, 6, 4)
                    note_layout.setSpacing(8)
                    note_layout.addWidget(editor, 1)
                    trash = icon_button(
                        "trash",
                        "Delete note",
                        lambda checked=False, i=ident: self.note_delete_requested.emit(i),
                    )
                    note_layout.addWidget(trash, 0, Qt.AlignTop)
                    note_row.setSizeHint(0, QSize(100, height + 8))
                    self.tree.setItemWidget(note_row, 0, container)
                for session in linked:
                    self.add_session(row, session)
                add(ident, row, depth + 1, rail)
                row.setExpanded(True)

        add(None)
        if selected in self.rows:
            self.tree.setCurrentItem(self.rows[selected])
        self.tree.blockSignals(False)
        self.building = False
        self.tree.verticalScrollBar().setValue(scroll)
        self.summary.setText(
            f"{len(direct)} matches · {sum(not i['done'] for i in self.notebook.items)} open · {len(self.notebook.items)} items total"
        )
        if not self.notebook.items:
            self.summary.setText(
                "Start with “+ Add item” · Enter: next item · Tab / Shift+Tab: indent / outdent · Double-click: edit"
            )

    def cancel_completion_animation(self, *args):
        if self.completion_overlay is not None:
            overlay = self.completion_overlay
            self.completion_overlay = None
            overlay.dispose()

    def show_completed(self, ident):
        row = self.rows.get(ident)
        visible, _ = self.notebook.visible(self.search.text(), self.status.currentData(), None)
        before = None
        if row is not None and ident not in visible:
            # Capture the checked state and include expanded notes, sessions and children.
            self.tree.blockSignals(True)
            for item in [self.notebook.get(ident), *self.notebook.descendants(ident)]:
                existing = self.rows.get(item["id"])
                if existing:
                    existing.setCheckState(0, Qt.Checked)
            font = row.font(0)
            font.setStrikeOut(True)
            row.setFont(0, font)
            self.tree.blockSignals(False)
            bounds = self.tree.visualItemRect(row)
            following = self.tree.itemBelow(row)
            while following is not None:
                ancestor = following.parent()
                while ancestor is not None and ancestor is not row:
                    ancestor = ancestor.parent()
                if ancestor is None:
                    break
                bounds = bounds.united(self.tree.visualItemRect(following))
                following = self.tree.itemBelow(following)
            bounds = bounds.intersected(self.tree.viewport().rect())
            if not bounds.isEmpty():
                self.cancel_completion_animation()
                before = self.tree.viewport().grab()
        self.rebuild(select=ident)
        if before is not None:
            self.completion_overlay = CompletionOverlay(
                self.tree.viewport(),
                before,
                self.tree.viewport().grab(),
                bounds.top(),
                bounds.height(),
                self.cancel_completion_animation,
            )
        self.show_undo(ident)

    def show_undo(self, ident):
        self.dismiss_undo(ident)
        item = self.notebook.get(ident)
        if item is None:
            return
        notice = QFrame()
        notice.setObjectName("undoNotice")
        notice.setStyleSheet(
            "QFrame#undoNotice { background: #eaf5ef; border: 1px solid #a5c9b4; border-radius: 6px; }"
        )
        line = QHBoxLayout(notice)
        line.setContentsMargins(12, 6, 8, 6)
        text = item["text"]
        label = QLabel("✓ Completed: " + (text[:70] + "…" if len(text) > 70 else text))
        label.setToolTip(text)
        line.addWidget(label, 1)
        button = QPushButton("Undo")
        button.setAccessibleName(text + " restore")
        button.clicked.connect(lambda: self.completion_undo_requested.emit(ident))
        line.addWidget(button)
        timer = QTimer(notice)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.expire_undo(ident))
        self.undo_notices[ident] = notice
        self.undo_layout.addWidget(notice)
        self.undo_area.show()
        timer.start(5000)

    def show_note_undo(self, ident):
        key = "note:" + ident
        self.dismiss_undo(key)
        notice = QFrame()
        notice.setObjectName("undoNotice")
        line = QHBoxLayout(notice)
        line.setContentsMargins(12, 6, 8, 6)
        label = QLabel("Note deleted")
        line.addWidget(label, 1)
        button = QPushButton("Undo")
        button.setAccessibleName("Restore deleted note")
        button.clicked.connect(lambda: self.note_undo_requested.emit(ident))
        line.addWidget(button)
        self.undo_notices[key] = notice
        self.undo_layout.addWidget(notice)
        self.undo_area.show()
        timer = QTimer(notice)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.expire_undo(key))
        timer.start(8000)

    def expire_undo(self, key):
        self.undo_expired.emit(key)
        self.dismiss_undo(key)

    def edit_text(self, ident, text):
        self.notebook.update(ident, text=text)
        self.changed.emit()

    def dismiss_undo(self, ident):
        notice = self.undo_notices.pop(ident, None)
        if notice is not None:
            self.undo_layout.removeWidget(notice)
            notice.hide()
            notice.deleteLater()
        self.undo_area.setVisible(bool(self.undo_notices))

    def start_at(self, ident):
        self.tree.setCurrentItem(self.rows[ident])
        self.session_start.emit()

    def reminder_cell(self, row, item):
        row.setText(2, "")
        reminder = item.get("reminder")
        if reminder:
            when = datetime.fromisoformat(reminder["at"]).astimezone()
            overdue = when <= datetime.now(timezone.utc) and not item["done"]
            row.setText(2, ("Overdue · " if overdue else "") + when.strftime("%d %b %H:%M"))
            row.setToolTip(2, when.strftime("%d %b %Y %H:%M %Z"))
            row.setForeground(2, QBrush(QColor("#a44b26" if overdue else "#445165")))

        button = self.tree.itemWidget(row, 2)
        if isinstance(button, QPushButton):
            button.setText(row.text(2))
            button.setToolTip(row.toolTip(2) or "Set reminder")
        if button:
            row.setText(2, "")

    def add_session(self, parent, session):
        row = QTreeWidgetItem(parent)
        ident = session["id"]
        row.setData(0, ROLE, ident)
        row.setData(0, ROLE + 1, "session")
        for column in range(self.tree.columnCount()):
            row.setData(column, ROLE + 2, parent.data(column, ROLE + 2))
            row.setData(column, ROLE + 3, (parent.data(0, ROLE + 3) or 0) + 1)
            row.setData(column, ROLE + 4, parent.data(0, ROLE + 4))
        row.setSizeHint(0, QSize(100, 26))
        self.session_rows[ident] = row
        row.setToolTip(0, session["workdir"])
        row.setForeground(0, parent.foreground(0))
        row.setTextAlignment(3, Qt.AlignCenter)
        actions = QWidget()
        buttons = QHBoxLayout(actions)
        buttons.setContentsMargins(2, 0, 2, 0)
        buttons.setSpacing(2)
        resume = QPushButton(icon("play"), "Resume")
        resume.setToolTip("Resume this session or focus its running terminal")
        resume.setAccessibleName("Resume session")
        resume.clicked.connect(lambda checked=False: self.session_resume.emit(ident))
        buttons.addWidget(resume)
        buttons.addWidget(
            icon_button("info", "Session details", lambda checked=False: self.session_details.emit(ident))
        )
        actions.setStyleSheet(
            f"QWidget {{ background: {parent.data(0, ROLE + 2).name()}; color: {parent.foreground(0).color().name()}; }}"
        )
        self.tree.setItemWidget(row, 4, actions)
        self.update_session(session)

    def update_session(self, session):
        ident = session["id"]
        row = self.session_rows.get(ident)
        if not row:
            return
        terminal = self.terminals.get(ident)
        state = getattr(terminal, "agent_state", None) or (
            "Terminal running" if terminal and terminal.running else "Ended" if terminal else "Disconnected"
        )
        message = bool(terminal and getattr(terminal, "agent_message", False))
        unread = (
            " · New agent message" if message else " · new output" if terminal and terminal.unread else ""
        )
        label = f"↳ {session['agent']} · {session['title']} · {state}{unread}"
        row.setText(0, label)
        row.setText(3, "ID ✓" if session.get("native_session_id") else "No ID")
        row.setToolTip(
            3,
            "Native session ID: " + session["native_session_id"]
            if session.get("native_session_id")
            else "Automatic resume is unavailable. Add the native session ID in Details.",
        )
        self.update_item_status(session["item_id"])

    def update_item_status(self, item_id):
        row = self.rows.get(item_id)
        if row is None:
            return
        linked = [s for s in self.notebook.data["sessions"] if s["item_id"] == item_id]
        terminals = [self.terminals[s["id"]] for s in linked if s["id"] in self.terminals]
        busy = any(getattr(t, "agent_state", None) == "Agent running" for t in terminals)
        message = any(getattr(t, "agent_message", False) for t in terminals)
        labels = []
        if busy:
            labels.append("Agent running")
        if message:
            labels.append("New agent message")
        row.setSizeHint(0, QSize(100, max(28, 38 if len(labels) > 1 else 0)))
        row.setText(3, "\n".join(labels) or (str(len(linked)) if linked else ""))
        row.setToolTip(3, " · ".join(labels) or "Linked sessions")

    def note_changed(self, ident, editor):
        self.notebook.update(ident, notes=editor.toPlainText())
        self.changed.emit()

    def item_changed(self, row, column):
        if self.building or row.data(0, ROLE + 1) != "item" or column != 0:
            return
        ident = row.data(0, ROLE)
        item = self.notebook.get(ident)
        done = row.checkState(0) == Qt.Checked
        if done != item["done"]:
            self.completion_requested.emit(ident, done)
        elif row.text(0) != item["text"]:
            self.notebook.update(ident, text=row.text(0))
            self.changed.emit()

    def selection_changed(self, row, previous):
        if row and row.data(0, ROLE + 1) == "session":
            self.selected.emit(row.data(0, ROLE))

    def toggle_note(self, ident=None):
        ident = ident or self.current_id()
        if not ident:
            return
        item = self.notebook.get(ident)
        if ident in self.notes_open or (item["notes"] and ident not in self.notes_hidden):
            self.notes_open.discard(ident)
            self.notes_hidden.add(ident)
        else:
            self.notes_open.add(ident)
            self.notes_hidden.discard(ident)
        self.rebuild(select=ident)

    def item_menu(self, ident, position=None):
        menu = QMenu(self)
        for label, action in [
            ("Edit text", "edit"),
            ("+ Add child item", "child"),
            ("Change row color …", "category"),
            ("Edit reminder …", "reminder"),
            ("Indent", "indent"),
            ("Outdent", "outdent"),
            ("↑ Move up", "up"),
            ("↓ Move down", "down"),
            ("Delete item", "delete"),
        ]:
            if action in ("indent", "delete"):
                menu.addSeparator()
            menu.addAction(label, lambda i=ident, a=action: self.action_requested.emit(i, a))
        anchor = self.tree.visualItemRect(self.rows[ident]).bottomRight()
        menu.exec(position or self.tree.viewport().mapToGlobal(anchor))

    def menu(self, position):
        row = self.tree.itemAt(position)
        if not row or row.data(0, ROLE + 1) != "item":
            return
        self.tree.setCurrentItem(row)
        self.item_menu(row.data(0, ROLE), self.tree.viewport().mapToGlobal(position))
