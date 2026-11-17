"""Vertical task/session tabs sharing the existing integrated terminal widgets."""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.common import SafeBrowser
from app.ui.icons import icon


class Agents(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.selected_session = None
        self.rows = {}
        self.session_rows = {}
        self.signature = None
        self.reply_signature = None
        self.trash_signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        self.new_session = QPushButton("Session")
        self.new_session.setIcon(icon("plus"))
        self.new_session.setObjectName("addSession")
        self.new_session.setAccessibleName("New session")
        self.new_session.setToolTip("Start an agent session without a todo")
        self.new_session.clicked.connect(lambda: window.start_session(standalone=True))
        session_layout = QHBoxLayout()
        session_layout.setContentsMargins(8, 4, 8, 4)
        session_layout.addWidget(self.new_session)
        side_layout.addLayout(session_layout)
        self.sidebar_heading = QLabel("Pinned sessions · Open todos")
        side_layout.addWidget(self.sidebar_heading)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.header().setMinimumSectionSize(26)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 30)
        self.tree.setObjectName("agentTabs")
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setUniformRowHeights(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.setMinimumWidth(180)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.session_menu)
        self.tree.currentItemChanged.connect(self.selection_changed)
        side_layout.addWidget(self.tree)
        self.sidebar_empty = QLabel("No pinned sessions yet. Start an ad-hoc session or attach one to an open todo.")
        self.sidebar_empty.setWordWrap(True)
        side_layout.addWidget(self.sidebar_empty)
        self.trash_panel = QWidget()
        trash_layout = QVBoxLayout(self.trash_panel)
        trash_layout.setContentsMargins(8, 0, 8, 4)
        trash_title = QLabel("Session trash")
        trash_title.setObjectName("documentTitle")
        trash_layout.addWidget(trash_title)
        trash_hint = QLabel("Removed from the sidebar, not deleted. History and running agents are kept.")
        trash_hint.setProperty("muted", True)
        trash_hint.setWordWrap(True)
        trash_layout.addWidget(trash_hint)
        self.trash_search = QLineEdit()
        self.trash_search.setPlaceholderText("Find a removed session …")
        self.trash_search.setAccessibleName("Search session trash")
        self.trash_search.setClearButtonEnabled(True)
        self.trash_search.textChanged.connect(self.filter_trash)
        trash_layout.addWidget(self.trash_search)
        self.trash_list = QListWidget()
        self.trash_list.setObjectName("sessionTrashList")
        self.trash_list.setToolTip("Select a session to restore. Use Ctrl or Shift to select several.")
        self.trash_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.trash_list.itemSelectionChanged.connect(self.trash_selection_changed)
        trash_layout.addWidget(self.trash_list, 1)
        self.trash_empty = QLabel("Trash is empty. Removed sessions will appear here.")
        self.trash_empty.setProperty("muted", True)
        self.trash_empty.setWordWrap(True)
        trash_layout.addWidget(self.trash_empty)
        self.restore_button = QPushButton("Restore session")
        self.restore_button.setIcon(icon("refresh"))
        self.restore_button.clicked.connect(self.restore_sessions)
        trash_layout.addWidget(self.restore_button)
        self.trash_panel.hide()
        side_layout.addWidget(self.trash_panel, 1)
        self.trash_button = QPushButton("Trash")
        self.trash_button.setObjectName("sessionTrash")
        self.trash_button.setIcon(icon("trash"))
        self.trash_button.setCheckable(True)
        self.trash_button.setAccessibleName("Open session trash")
        self.trash_button.setToolTip("View and restore removed sessions")
        self.trash_button.toggled.connect(self.toggle_trash)
        footer = QHBoxLayout()
        footer.setContentsMargins(8, 4, 8, 8)
        footer.addWidget(self.trash_button)
        side_layout.addLayout(footer)
        self.splitter.addWidget(sidebar)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 0, 0, 0)
        self.title = QLabel("Select an agent session on the left.")
        self.title.setWordWrap(True)
        self.content_layout.addWidget(self.title)
        controls = QHBoxLayout()
        self.resume = QPushButton("Resume session")
        self.resume.clicked.connect(lambda: window.resume_session(self.selected_session))
        controls.addWidget(self.resume)
        self.details = QPushButton("Session details")
        self.details.clicked.connect(lambda: window.session_details(self.selected_session))
        controls.addWidget(self.details)
        self.close_terminal = QPushButton("Close terminal")
        self.close_terminal.clicked.connect(self.close_selected_terminal)
        controls.addWidget(self.close_terminal)
        controls.addStretch()
        self.content_layout.addLayout(controls)
        self.saved = QWidget()
        saved_layout = QVBoxLayout(self.saved)
        saved_layout.setContentsMargins(0, 0, 0, 0)
        self.reply = SafeBrowser()
        saved_layout.addWidget(self.reply)
        self.content_layout.addWidget(self.saved)
        self.splitter.addWidget(self.content)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([300, 1100])
        layout.addWidget(self.splitter)
        self.refresh()

    def active(self):
        return self.window.workspace.currentWidget() is self

    def close_selected_terminal(self):
        terminal = self.window.terminals.get(self.selected_session)
        if terminal:
            self.window.close_terminal(self.window.tabs.indexOf(terminal))

    def refresh(self):
        book = self.window.notebook
        sessions = {}
        standalone = []
        for session in book.data["sessions"]:
            item = book.get(session["item_id"])
            if session["item_id"] is None and not session.get("agents_hidden"):
                standalone.append(session)
            elif item and not item["done"]:
                sessions.setdefault(item["id"], []).append(session)
        visible = set(sessions)
        for ident in sessions:
            visible.update(item["id"] for item in book.ancestors(ident))
        signature = (
            tuple((item["id"], item["parent_id"], item["position"], item["text"])
                  for item in book.items if item["id"] in visible),
            tuple((ident, tuple(s["id"] for s in linked)) for ident, linked in sessions.items()),
            tuple(s["id"] for s in standalone),
        )
        if signature != self.signature:
            collapsed = {ident for ident, row in self.rows.items() if not row.isExpanded()}
            self.tree.blockSignals(True)
            self.tree.clear()
            self.rows = {}
            self.session_rows = {}

            def add_children(parent=None, parent_row=None):
                for item in book.children(parent):
                    ident = item["id"]
                    if ident not in visible:
                        continue
                    row = QTreeWidgetItem([item["text"]])
                    if parent_row is None:
                        self.tree.addTopLevelItem(row)
                    else:
                        parent_row.addChild(row)
                    self.rows[ident] = row
                    linked = sessions.get(ident, [])
                    if len(linked) == 1:
                        row.setData(0, Qt.UserRole, linked[0]["id"])
                        self.session_rows[linked[0]["id"]] = row
                    else:
                        row.setFlags(row.flags() & ~Qt.ItemIsSelectable)
                        for session in linked:
                            session_row = QTreeWidgetItem()
                            session_row.setData(0, Qt.UserRole, session["id"])
                            row.addChild(session_row)
                            self.session_rows[session["id"]] = session_row
                    add_children(ident, row)
                    row.setExpanded(ident not in collapsed)

            for session in standalone:
                row = QTreeWidgetItem()
                row.setData(0, Qt.UserRole, session["id"])
                self.tree.addTopLevelItem(row)
                self.session_rows[session["id"]] = row
                button = QToolButton()
                button.setObjectName("unpinSession")
                button.setIcon(icon("trash"))
                button.setIconSize(QSize(14, 14))
                button.setAutoRaise(True)
                button.setFixedSize(20, 26)
                button.setFocusPolicy(Qt.NoFocus)
                button.setAccessibleName("Move session to trash")
                button.setToolTip("Move to trash · Restore anytime · Keeps history and running agent")
                button.clicked.connect(lambda checked=False, ident=session["id"]: QTimer.singleShot(
                    0, lambda: self.unpin_session(ident)))
                actions = QWidget()
                actions_layout = QHBoxLayout(actions)
                actions_layout.setContentsMargins(0, 0, 0, 0)
                actions_layout.addWidget(button, 0, Qt.AlignCenter)
                self.tree.setItemWidget(row, 1, actions)
            add_children()
            self.signature = signature
            if self.selected_session not in self.session_rows:
                self.selected_session = next(iter(self.session_rows), None)
            row = self.session_rows.get(self.selected_session)
            self.tree.setCurrentItem(row)
            for ident in collapsed:
                if ident in self.rows:
                    self.rows[ident].setExpanded(False)
            self.tree.blockSignals(False)
        for ident, row in self.session_rows.items():
            session = self.window.session(ident)
            item = book.get(session["item_id"])
            terminal = self.window.terminals.get(ident)
            status = "Saved session"
            if terminal:
                status = (getattr(terminal, "agent_state", None) or "Terminal running") if terminal.running else "Ended"
            unread = session.get("reply_unread") or terminal and getattr(terminal, "agent_message", False)
            title = (item["text"] if item and row is self.rows[item["id"]]
                     and not session.get("title_custom") else session["title"])
            row.setText(0, ("● " if unread else "") + f"{title} · {session['agent']}")
            context = item["text"] if item else "Ad-hoc session · No todo"
            row.setToolTip(0, f"{context}\n{session['title']}\n{session['workdir']}\n{status}"
                           + ("\nUnread agent reply" if unread else ""))
        self.sidebar_empty.setVisible(not self.session_rows and not self.trash_button.isChecked())
        self.refresh_trash()
        self.show_selected()

    def toggle_trash(self, checked):
        self.sidebar_heading.setVisible(not checked)
        self.tree.setVisible(not checked)
        self.sidebar_empty.setVisible(not checked and not self.session_rows)
        self.trash_panel.setVisible(checked)
        self.trash_button.setText(
            f"Back to sessions · {len(self.session_rows)}" if checked else f"Trash · {self.trash_list.count()}"
        )
        self.trash_button.setIcon(icon("session" if checked else "trash"))
        self.trash_button.setAccessibleName("Back to sessions" if checked else "Open session trash")
        self.trash_button.setToolTip("Back to pinned sessions and open todos" if checked
                                    else "View and restore removed sessions")
        if checked:
            self.trash_search.setFocus()

    def refresh_trash(self):
        hidden = [session for session in self.window.notebook.data["sessions"]
                  if session["item_id"] is None and session.get("agents_hidden")]
        signature = tuple((s["id"], s["title"], s["agent"], s["workdir"]) for s in hidden)
        if signature != self.trash_signature:
            selected = {item.data(Qt.UserRole) for item in self.trash_list.selectedItems()}
            self.trash_list.clear()
            for session in hidden:
                row = QListWidgetItem(icon("session"), f"{session['title']}\n{session['agent']}")
                row.setData(Qt.UserRole, session["id"])
                row.setToolTip(session["workdir"])
                self.trash_list.addItem(row)
                row.setSelected(session["id"] in selected)
            self.trash_signature = signature
        self.filter_trash()
        self.trash_button.setText(
            f"Back to sessions · {len(self.session_rows)}" if self.trash_button.isChecked()
            else f"Trash · {len(hidden)}"
        )

    def filter_trash(self):
        query = self.trash_search.text().strip().casefold()
        visible = 0
        for index in range(self.trash_list.count()):
            row = self.trash_list.item(index)
            matches = query in (row.text() + "\n" + row.toolTip()).casefold()
            if not matches:
                row.setSelected(False)
            row.setHidden(not matches)
            visible += matches
        self.trash_list.setVisible(bool(visible))
        self.trash_empty.setVisible(not visible)
        self.trash_empty.setText("No matching sessions." if self.trash_list.count()
                                 else "Trash is empty. Removed sessions will appear here.")
        self.trash_selection_changed()

    def trash_selection_changed(self):
        count = len(self.trash_list.selectedItems())
        self.restore_button.setEnabled(count > 0)
        self.restore_button.setText(f"Restore {count} sessions" if count > 1 else "Restore session")

    def restore_sessions(self):
        restored = []
        for row in self.trash_list.selectedItems():
            session = self.window.session(row.data(Qt.UserRole))
            if session and session["item_id"] is None and session.get("agents_hidden"):
                session["agents_hidden"] = False
                restored.append(session["id"])
        if not restored:
            return
        self.selected_session = restored[0]
        self.window.schedule_save()
        self.trash_button.setChecked(False)
        self.tree.setCurrentItem(self.session_rows[self.selected_session])
        self.tree.scrollToItem(self.session_rows[self.selected_session])
        self.window.select_session(self.selected_session)
        self.show_selected()

    def session_menu(self, position):
        row = self.tree.itemAt(position)
        ident = row.data(0, Qt.UserRole) if row else None
        if not ident:
            return
        menu = QMenu(self)
        menu.addAction("Rename …", lambda: self.rename_session(ident))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def rename_session(self, ident):
        session = self.window.session(ident)
        if not session:
            return
        title, accepted = QInputDialog.getText(self, "Rename session", "Session name", text=session["title"])
        title = title.strip()
        if not accepted or not title:
            return
        session.update(title=title, title_custom=True)
        self.window.session_changed(ident)
        self.window.schedule_save()

    def unpin_session(self, ident):
        session = self.window.session(ident)
        if session and session["item_id"] is None:
            session["agents_hidden"] = True
            self.window.schedule_save()
            self.window.select_session(self.selected_session)

    def selection_changed(self, row, previous):
        ident = row.data(0, Qt.UserRole) if row else None
        if not ident:
            return
        self.selected_session = ident
        self.window.select_session(ident)
        terminal = self.window.terminals.get(ident)
        if terminal:
            terminal.agent_message = False
        self.show_selected()
        self.window.session_changed(ident)
        if terminal:
            terminal.setFocus()

    def show_selected(self):
        session = self.window.session(self.selected_session)
        terminal = self.window.terminals.get(self.selected_session) if session else None
        if self.active():
            self.window.terminal_panel.setVisible(terminal is not None)
            if terminal:
                self.window.tabs.setCurrentWidget(terminal)
        self.saved.setVisible(terminal is None)
        self.resume.setVisible(session is not None and (terminal is None or not terminal.running))
        self.details.setVisible(session is not None)
        self.close_terminal.setVisible(terminal is not None)
        self.title.setText(
            f"{session['title']} · {session['agent']}" + (
                "" if terminal else "\nNo terminal connected. Resume opens the saved agent chat."
            )
            if session else "Select an agent session on the left."
        )
        text = (session.get("last_reply") or {}).get("text") if session else None
        if text != self.reply_signature:
            self.reply_signature = text
            self.reply.setMarkdown(text or "No saved assistant reply available.")
        elif self.reply.document().isEmpty():
            self.reply.setMarkdown("No saved assistant reply available.")
        if self.active():
            self.window.visibility()
            if self.window.isActiveWindow() and self.window.isVisible() and not self.window.isMinimized() and session:
                unread = session.get("reply_unread")
                message = terminal and getattr(terminal, "agent_message", False)
                if unread or message:
                    session["reply_unread"] = False
                    if terminal:
                        terminal.agent_message = False
                    self.window.schedule_save()
                    self.window.session_changed(session["id"])

    def activate(self):
        if self.window.terminal_popout:
            self.window.dock_terminals()
        if self.window.terminals_maximized:
            self.window.toggle_terminal_maximized()
        self.content_layout.addWidget(self.window.terminal_panel)
        self.window.tabs.tabBar().hide()
        self.window.maximize_terminal_button.hide()
        self.window.popout_terminal_button.hide()
        self.refresh()

    def deactivate(self):
        self.window.vertical.addWidget(self.window.terminal_panel)
        self.window.terminal_panel.show()
        self.window.tabs.tabBar().show()
        self.window.vertical.setSizes([530, 280] if self.window.tabs.count() else [780, 50])
