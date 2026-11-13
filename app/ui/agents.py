"""Vertical task/session tabs sharing the existing integrated terminal widgets."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.common import SafeBrowser


class Agents(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.selected_session = None
        self.rows = {}
        self.session_rows = {}
        self.signature = None
        self.reply_signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(QLabel("Open todos · Attached sessions"))
        self.tree = QTreeWidget()
        self.tree.setObjectName("agentTabs")
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setUniformRowHeights(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.setMinimumWidth(180)
        self.tree.currentItemChanged.connect(self.selection_changed)
        side_layout.addWidget(self.tree)
        self.sidebar_empty = QLabel("No open todo has an attached agent session.")
        self.sidebar_empty.setWordWrap(True)
        side_layout.addWidget(self.sidebar_empty)
        self.splitter.addWidget(sidebar)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
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
        for session in book.data["sessions"]:
            item = book.get(session["item_id"])
            if item and not item["done"]:
                sessions.setdefault(item["id"], []).append(session)
        visible = set(sessions)
        for ident in sessions:
            visible.update(item["id"] for item in book.ancestors(ident))
        signature = (
            tuple((item["id"], item["parent_id"], item["position"], item["text"])
                  for item in book.items if item["id"] in visible),
            tuple((ident, tuple(s["id"] for s in linked)) for ident, linked in sessions.items()),
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
            unread = session.get("reply_unread") or terminal and (
                terminal.unread or getattr(terminal, "agent_message", False)
            )
            title = item["text"] if row is self.rows[item["id"]] else session["title"]
            row.setText(0, ("● " if unread else "") + f"{title} · {session['agent']} · {status}")
            row.setToolTip(0, f"{item['text']}\n{session['title']}\n{session['workdir']}\n{status}")
        self.sidebar_empty.setVisible(not self.session_rows)
        self.show_selected()

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
