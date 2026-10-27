import json
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.agents import agents
from app.agents.replies import snapshots
from app.agents.sessions import codex_sessions, native_sessions
from app.executions import execution_records, recover_process_runs
from app.models import Notebook, now_iso, uid
from app.notifications import Notifier
from app.reminders import Reminders
from app.scheduling import Scheduler
from app.storage import StorageError
from app.terminal.bridge import Terminal
from app.ui.agent_context import AgentContextPanel
from app.ui.colors import ColorPalette
from app.ui.common import DismissibleDialog, Job, TerminalPopout, confirm, error
from app.ui.dialogs import ReminderDialog, SessionDialog, SettingsDialog
from app.ui.executions import Executions
from app.ui.icons import icon, icon_button
from app.ui.knowledge import Knowledge
from app.ui.scheduled import Scheduled
from app.ui.tasks import Tasks


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setBrush(QColor("#355d84"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(5, 5, 54, 54, 9, 9)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setPixelSize(34)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "✓")
    painter.end()
    return QIcon(pixmap)


class Window(QMainWindow):
    def __init__(self, store, data):
        super().__init__()
        self.store = store
        self.notebook = Notebook(data)
        recovered_executions = recover_process_runs(self.notebook)
        self.terminals = {}
        self.terminal_popout = None
        self.terminals_maximized = False
        self.status_polling = False
        self.reply_baselined = set()
        self.context_generation = 0
        self.selected_session = None
        self.quitting = False
        self.save_failed = False
        self.completion_undos = {}
        self.note_undos = {}
        self.setWindowTitle("GetItDone · Personal notebook")
        self.setWindowIcon(app_icon())
        self.resize(1440, 900)
        self.setMinimumSize(900, 580)
        self.saver = QTimer(self)
        self.saver.setSingleShot(True)
        self.saver.setInterval(400)
        self.saver.timeout.connect(self.flush)
        self.reminders = Reminders(self.notebook)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 5, 10, 6)
        self.workspace = QTabWidget()
        self.workspace.setDocumentMode(True)
        self.task_page = QWidget()
        task_layout = QVBoxLayout(self.task_page)
        task_layout.setContentsMargins(0, 5, 0, 0)
        self.vertical = QSplitter(Qt.Vertical)
        self.draft_items = set()
        self.tasks = Tasks(self.notebook, self.terminals)
        self.tasks.escape_pressed.connect(self.discard_empty_draft)
        self.inspector = AgentContextPanel(self.notebook.data["settings"], self)
        self.vertical.addWidget(self.tasks)
        self.terminal_panel = QWidget()
        term_layout = QVBoxLayout(self.terminal_panel)
        term_layout.setContentsMargins(0, 3, 0, 0)
        terminal_header = QHBoxLayout()
        terminal_header.addWidget(QLabel("Integrated terminals · Output stays in memory only"))
        terminal_header.addStretch()
        for name, title, callback in [
            ("paste", "Paste", self.paste_terminal),
            ("copy", "Copy selection", self.copy_terminal),
            ("session", "Send Ctrl+C", self.interrupt_terminal),
        ]:
            button = icon_button(name, title, callback)
            terminal_header.addWidget(button)
        self.maximize_terminal_button = icon_button("maximize", "Maximize", self.toggle_terminal_maximized)
        terminal_header.addWidget(self.maximize_terminal_button)
        self.popout_terminal_button = icon_button("external", "Pop out", self.toggle_terminal_popout)
        terminal_header.addWidget(self.popout_terminal_button)
        term_layout.addLayout(terminal_header)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(self.visibility)
        self.tabs.tabCloseRequested.connect(self.close_terminal)
        term_layout.addWidget(self.tabs)
        self.tabs.hide()
        self.terminal_empty = QLabel("No terminal open · Start a session from a task’s terminal button.")
        term_layout.addWidget(self.terminal_empty)
        self.terminal_header = terminal_header
        for index in range(terminal_header.count()):
            widget = terminal_header.itemAt(index).widget()
            if widget:
                widget.hide()
        self.vertical.addWidget(self.terminal_panel)
        self.vertical.setSizes([780, 50])
        self.vertical.setCollapsible(0, False)
        task_layout.addWidget(self.vertical)
        self.knowledge = Knowledge(self.notebook.data["settings"])
        self.knowledge.settings_changed.connect(self.schedule_save)
        self.workspace.addTab(self.task_page, "Tasks")
        self.workspace.addTab(self.knowledge, "Knowledge")
        self.workspace.addTab(self.inspector, "Agent context")
        self.last_workspace = 0
        self.workspace.currentChanged.connect(self.workspace_changed)
        layout.addWidget(self.workspace)
        self.setCentralWidget(central)
        for title, callback, shortcut in [
            ("New todo", self.quick_todo, "Ctrl+T"),
            ("New note", self.quick_note, "Ctrl+N"),
            ("Child item", lambda: self.add_item(True), "Ctrl+Shift+N"),
            ("Move up", lambda: self.move(-1), "Alt+Up"),
            ("Move down", lambda: self.move(1), "Alt+Down"),
        ]:
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.WindowShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
        self.tasks.action_requested.connect(self.task_action)
        self.tasks.append_requested.connect(self.append_item)
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("Settings …", self.settings_dialog)
        file_menu.addAction("Save", self.save_all, "Ctrl+S")
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.quit_app, "Ctrl+Q")
        view_menu = self.menuBar().addMenu("View")
        for title, widget in [
            ("Terminal panel", self.terminal_panel),
        ]:
            action = view_menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(widget.setVisible)
            action.toggled.connect(self.visibility)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Keyboard shortcuts", self.show_shortcuts)
        help_menu.addAction("Test notification", self.test_notification)
        help_menu.addAction(
            "About GetItDone",
            lambda: error(
                self,
                "GetItDone 0.1.0\nLocal notebook · Python / Qt\nTerminal: xterm.js (MIT)\nDocuments: Qt PDF and python-docx\nPlatform limitations and testing: README.md",
            ),
        )
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("GetItDone · Notebook")
        tray_menu = QMenu(self)
        tray_menu.addAction("Open notebook", self.restore)
        tray_menu.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(
            lambda reason: (
                self.restore() if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None
            )
        )
        self.tray.show()
        self.notifier = Notifier(self.tray, self)
        self.save_status = QLabel("All changes saved")
        self.save_status.setObjectName("saveStatus")
        self.statusBar().addPermanentWidget(self.save_status)
        self.notification_status = QPushButton("Notifications: status / settings")
        self.notification_status.clicked.connect(self.notification_settings)
        self.notification_status.setToolTip(self.notifier.status)
        self.statusBar().addPermanentWidget(self.notification_status)
        self.notifier.status_changed.connect(self.update_notification_status)
        self.notifier.native_result.connect(self.notification_result)
        self.notifier.activated.connect(self.open_reminder)
        self.notifier.status_changed.connect(lambda text: self.statusBar().showMessage(text, 20000))
        self.scheduler = Scheduler(self.notebook, self.flush, self)
        self.scheduled = Scheduled(self.scheduler)
        self.scheduled.session_open.connect(self.resume_session)
        self.scheduled.session_details.connect(self.session_details)
        self.session_tree_refresh = QTimer(self)
        self.session_tree_refresh.setSingleShot(True)
        self.session_tree_refresh.timeout.connect(self.refresh_scheduled_sessions)
        self.scheduler.sessions_changed.connect(lambda: self.session_tree_refresh.start(0))
        self.workspace.addTab(self.scheduled, "Scheduled tasks")
        self.executions = Executions(self)
        self.executions.session_open.connect(self.resume_session)
        self.executions.session_details.connect(self.session_details)
        self.executions.scheduled_open.connect(self.open_scheduled_execution)
        self.workspace.addTab(self.executions, "Agent executions")
        self.execution_indicator = QPushButton("0 agents running")
        self.execution_indicator.setToolTip("Open all agent executions, including scheduled runs and idle terminals")
        self.execution_indicator.clicked.connect(lambda: self.workspace.setCurrentWidget(self.executions))
        self.statusBar().insertPermanentWidget(0, self.execution_indicator)
        self.scheduler.changed.connect(self.refresh_executions)
        self.refresh_executions()
        if recovered_executions:
            QTimer.singleShot(0, self.flush)
        self.tasks.changed.connect(self.schedule_save)
        self.tasks.new_requested.connect(self.add_item)
        self.tasks.indent_requested.connect(self.indent)
        self.tasks.completion_requested.connect(self.complete, Qt.QueuedConnection)
        self.tasks.completion_undo_requested.connect(self.undo_completion)
        self.tasks.note_delete_requested.connect(self.delete_note)
        self.tasks.note_undo_requested.connect(self.undo_note)
        self.tasks.undo_expired.connect(self.expire_undo)
        self.tasks.session_start.connect(self.start_session)
        self.tasks.session_resume.connect(self.resume_session)
        self.tasks.session_reply.connect(self.show_last_reply)
        self.tasks.session_details.connect(self.session_details)
        self.tasks.selected.connect(self.select_session)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.minute = None
        self.statusBar().showMessage(f"Local data: {self.store.path}")
        self.update_notification_status(self.notifier.status)
        geometry = data["settings"].get("window_geometry")
        if isinstance(geometry, str):
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        QApplication.instance().applicationStateChanged.connect(self.visibility)

    def workspace_changed(self, index):
        if self.last_workspace == 1 and index != 1 and not self.knowledge.guard():
            self.workspace.blockSignals(True)
            self.workspace.setCurrentIndex(1)
            self.workspace.blockSignals(False)
            return
        self.last_workspace = index
        self.visibility()

    def schedule_save(self):
        self.flush()

    def update_notification_status(self, text):
        self.notification_status.setToolTip(text)
        if "not allowed" in text or "disabled" in text or "unavailable" in text:
            label = "Notifications: unavailable / blocked"
        elif text == "Notifications allowed.":
            label = "Notifications: allowed"
        else:
            label = "Notifications: check permission"
        self.notification_status.setText(label)

    def notification_result(self, ident, accepted, message):
        if not accepted:
            self.statusBar().showMessage("System notification not sent: " + message)
        else:
            self.statusBar().showMessage(message, 5000)

    def notification_settings(self):
        import sys

        dialog = DismissibleDialog(self)
        dialog.setWindowTitle("System notifications")
        layout = QVBoxLayout(dialog)
        status = QLabel(self.notifier.status)
        status.setWordWrap(True)
        layout.addWidget(status)
        hint = QLabel(
            "Allow GetItDone notifications and choose Banners or Alerts. Check Focus / Do Not Disturb if notifications still do not appear. Reminders work while the app is open or hidden in the menu bar."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        if sys.platform in ("darwin", "win32"):
            button = QPushButton("Open System Settings")
            button.clicked.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile("/System/Applications/System Settings.app")
                    if sys.platform == "darwin"
                    else QUrl("ms-settings:notifications")
                )
            )
            layout.addWidget(button)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def flush(self):
        self.saver.stop()
        try:
            self.store.save(self.notebook.data)
            self.save_failed = False
            self.save_status.setText("All changes saved")
            self.save_status.setStyleSheet("color: #28765b; padding: 3px 10px;")
            self.statusBar().showMessage("Saved locally", 2500)
            return True
        except StorageError as exc:
            self.save_status.setText("Save failed — changes are not on disk")
            self.save_status.setStyleSheet("color: #b02c35; font-weight: 600; padding: 3px 10px;")
            self.statusBar().showMessage(f"NOT SAVED · {exc}")
            if not self.save_failed:
                self.save_failed = True
                error(self, exc)
            return False

    def save_all(self):
        return self.knowledge.save(interactive=True) and self.flush()

    def refresh_scheduled_sessions(self):
        focus = QApplication.focusWidget()
        if (self.tasks.tree.state() == QAbstractItemView.EditingState
                or isinstance(focus, QPlainTextEdit) and self.tasks.isAncestorOf(focus)):
            self.session_tree_refresh.start(500)
            return
        self.tasks.rebuild()

    def show_shortcuts(self):
        dialog = DismissibleDialog(self)
        dialog.setWindowTitle("Keyboard shortcuts")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "Command on macOS · Ctrl on Windows / Linux\n\n"
            "⌘/Ctrl+T — New parent todo at the bottom; type immediately\n"
            "⌘/Ctrl+N — Knowledge: new note; type immediately\n"
            "⌘/Ctrl+Shift+N — Add child todo\n"
            "⌘/Ctrl+S — Save\n⌘/Ctrl+Q — Quit\n"
            "Alt+Up / Down — Move todo\n"
            "Todo: Enter — next item; Shift+Enter — new line in expanded titles\n"
            "Todo: Tab / Shift+Tab — indent / outdent\n"
            "Todo: Escape — finish editing; double-click / F2 — edit\n"
            "New note: Enter — save; Shift+Enter — new line; Escape — cancel"))
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def quick_todo(self):
        self.restore()
        self.workspace.setCurrentIndex(0)
        if self.workspace.currentIndex() == 0:
            self.append_item()

    def quick_note(self):
        self.restore()
        self.workspace.setCurrentIndex(1)
        self.knowledge.new_note()

    def add_item(self, child=False):
        if self.workspace.currentIndex() == 1:
            self.knowledge.new_note()
            return
        current = self.tasks.current_id()
        parent = current if child else self.notebook.get(current)["parent_id"] if current else None
        item = self.notebook.add(text="", parent=parent, after=None if child else current)
        self.draft_items.add(item["id"])
        if parent:
            self.tasks.view_state.setdefault("expanded", {})[parent] = True
        self.tasks.search.clear()
        self.tasks.status.setCurrentIndex(0)
        self.tasks.rebuild(select=item["id"])
        self.tasks.tree.scrollToItem(self.tasks.rows[item["id"]])
        self.tasks.tree.setFocus()
        self.tasks.tree.editItem(self.tasks.rows[item["id"]], 0)
        self.schedule_save()

    def discard_empty_draft(self, ident):
        item = self.notebook.get(ident)
        if (ident in self.draft_items and item and not item["text"].strip()
                and not item["notes"] and not item["reminder"]
                and not self.notebook.children(ident)
                and not any(s["item_id"] == ident for s in self.notebook.data["sessions"])):
            self.notebook.delete(ident)
            self.draft_items.discard(ident)
            self.tasks.rebuild()
            self.flush()

    def append_item(self):
        self.workspace.setCurrentIndex(0)
        if self.workspace.currentIndex() != 0:
            return
        self.tasks.tree.setCurrentItem(None)
        self.add_item()

    def task_action(self, ident, action):
        self.tasks.tree.setCurrentItem(self.tasks.rows[ident])
        callbacks = {
            "edit": lambda: self.tasks.tree.editItem(self.tasks.rows[ident], 0),
            "child": lambda: self.add_item(True),
            "indent": lambda: self.indent(False),
            "outdent": lambda: self.indent(True),
            "up": lambda: self.move(-1),
            "down": lambda: self.move(1),
            "category": self.assign_category,
            "reminder": self.reminder_dialog,
            "delete": self.delete_item,
        }
        callbacks[action]()

    def indent(self, out=False):
        ident = self.tasks.current_id()
        if ident:
            self.notebook.indent(ident, out)
            self.tasks.rebuild(select=ident)
            self.schedule_save()

    def move(self, delta):
        ident = self.tasks.current_id()
        if ident:
            self.notebook.move(ident, delta)
            self.tasks.rebuild(select=ident)
            self.schedule_save()

    def complete(self, ident, done):
        if self.notebook.get(ident) is None:
            self.tasks.dismiss_undo(ident)
            return
        try:
            affected = {ident, *(i["id"] for i in self.notebook.descendants(ident))}
            linked = [s for s in self.notebook.data["sessions"] if s["item_id"] in affected]
            if done and any(self.terminals.get(s["id"]) and self.terminals[s["id"]].running for s in linked):
                if not confirm(
                    self,
                    "Running sessions",
                    "This item will be hidden from the open list. Its sessions will keep running. Complete it?",
                ):
                    self.tasks.rebuild(select=ident)
                    return
            before = self.notebook.complete(ident, done)
            if done:
                self.completion_undos[ident] = before
            else:
                self.completion_undos.pop(ident, None)
            self.schedule_save()
        except ValueError as exc:
            error(self, exc)
            self.tasks.rebuild(select=ident)
            return
        if done:
            self.tasks.show_completed(ident)
        else:
            self.tasks.dismiss_undo(ident)
            self.tasks.rebuild(select=ident)

    def undo_completion(self, ident):
        snapshot = self.completion_undos.pop(ident, None)
        if snapshot is None:
            return
        self.notebook.restore_completion(snapshot)
        self.tasks.dismiss_undo(ident)
        self.tasks.rebuild(select=ident)
        self.schedule_save()

    def expire_undo(self, key):
        if key.startswith("note:"):
            self.note_undos.pop(key[5:], None)
        else:
            self.completion_undos.pop(key, None)

    def delete_note(self, ident):
        item = self.notebook.get(ident)
        if item is None:
            return
        self.note_undos[ident] = item["notes"]
        self.notebook.update(ident, notes="")
        self.tasks.notes_open.discard(ident)
        self.tasks.notes_hidden.add(ident)
        self.tasks.rebuild(select=ident)
        self.tasks.show_note_undo(ident)
        self.schedule_save()

    def undo_note(self, ident):
        text = self.note_undos.pop(ident, None)
        if text is None or self.notebook.get(ident) is None:
            return
        current = self.notebook.get(ident)["notes"]
        self.notebook.update(ident, notes=text + ("\n\n" + current if current and current != text else ""))
        self.tasks.notes_hidden.discard(ident)
        self.tasks.notes_open.add(ident)
        self.tasks.dismiss_undo("note:" + ident)
        self.tasks.rebuild(select=ident)
        self.schedule_save()

    def delete_item(self):
        ident = self.tasks.current_id()
        if not ident:
            return
        ids = {ident, *(i["id"] for i in self.notebook.descendants(ident))}
        linked = [s for s in self.notebook.data["sessions"] if s["item_id"] in ids]
        if len(ids) > 1 or linked:
            if not confirm(
                self,
                "Delete item",
                f"{len(ids)} item(s) and {len(linked)} link(s)? Running sessions will stay open in their terminals.",
            ):
                return
        self.notebook.delete(ident)
        for deleted_id in ids:
            self.tasks.dismiss_undo(deleted_id)
            self.tasks.dismiss_undo("note:" + deleted_id)
            self.completion_undos.pop(deleted_id, None)
            self.note_undos.pop(deleted_id, None)
        self.tasks.refresh_categories()
        self.tasks.rebuild()
        self.schedule_save()

    def assign_category(self):
        ident = self.tasks.current_id()
        if not ident:
            return
        current_id = self.notebook.get(ident)["category_id"]
        category = next((c for c in self.notebook.data["categories"] if c["id"] == current_id), None)
        self.color_palette = ColorPalette(category["color"] if category else None, self)
        self.color_palette.selected.connect(lambda value: self.set_row_color(ident, value))
        button = self.tasks.tree.itemWidget(self.tasks.rows[ident], 1)
        self.color_palette.move(button.mapToGlobal(button.rect().bottomLeft()))
        self.color_palette.show()

    def set_row_color(self, ident, value):
        category_id = None
        if value:
            name, color = value
            cats = self.notebook.data["categories"]
            category = next((c for c in cats if c["color"].lower() == color.lower()), None)
            if category is None:
                category = {"id": uid(), "name": name, "color": color}
                cats.append(category)
            category_id = category["id"]
        for item in [self.notebook.get(ident), *self.notebook.descendants(ident)]:
            self.notebook.update(item["id"], category_id=category_id)
        self.tasks.refresh_categories()
        self.tasks.rebuild(select=ident)
        self.schedule_save()

    def reminder_dialog(self):
        ident = self.tasks.current_id()
        if not ident:
            return
        dialog = ReminderDialog(self.notebook.get(ident), self)
        if dialog.exec():
            self.notebook.update(ident, reminder=dialog.value())
            self.reminders.changed(ident)
            self.tasks.rebuild(select=ident)
            self.schedule_save()
            if self.notebook.get(ident)["reminder"]:
                self.notifier.request_permission()

    def settings_dialog(self):
        dialog = SettingsDialog(self.notebook.data, self.store.path, self.notifier.status, self)
        if dialog.exec():
            old_ids = {c["id"] for c in self.notebook.data["categories"]}
            new_ids = {c["id"] for c in dialog.categories}
            for ident in old_ids - new_ids:
                self.notebook.delete_category(ident)
            self.notebook.data["settings"].update(dialog.settings)
            self.notebook.data["categories"] = dialog.categories
            self.inspector.refresh()
            self.tasks.refresh_categories()
            self.tasks.rebuild()
            self.schedule_save()

    def session(self, ident):
        return next((s for s in self.notebook.data["sessions"] if s["id"] == ident), None)

    def start_session(self):
        ident = self.tasks.current_id()
        if not ident:
            error(self, "Select or create an item first.")
            return
        dialog = SessionDialog(self.notebook.data["settings"], self)
        if dialog.exec():
            item = self.notebook.get(ident)
            session = dict(
                id=uid(),
                item_id=ident,
                agent=dialog.agent.currentData(),
                native_session_id=dialog.native_session_id,
                workdir=dialog.directory,
                title=item["text"][:70],
                created_at=now_iso(),
            )
            if self.launch(session, dialog.command):
                self.terminals[session["id"]].agent_baselined = True
                self.notebook.data["sessions"].append(session)
                self.refresh_executions()
                QApplication.clipboard().setText(item["text"])
                self.tasks.rebuild(select=ident)
                self.select_session(session["id"])
                self.schedule_save()

    def launch(self, session, command):
        baseline = (
            codex_sessions(session["workdir"])
            if session["agent"] == "codex" and not session.get("native_session_id")
            else None
        )
        terminal = Terminal(self)
        terminal.codex_baseline = baseline
        try:
            terminal.start(command, session["workdir"])
        except Exception as exc:
            terminal.deleteLater()
            error(self, f"Could not start the session: {exc}")
            return False
        ident = session["id"]
        old = self.terminals.get(ident)
        if old:
            index = self.tabs.indexOf(old)
            if index >= 0:
                self.tabs.removeTab(index)
            old.deleteLater()
        terminal.agent_state = None
        terminal.agent_message = False
        terminal.agent_baselined = False
        terminal.last_agent_message = None
        execution = dict(id=uid(), started_at=now_iso(), finished_at=None, status="running",
                         resumed=bool(session.get("process_runs")) or session in self.notebook.data["sessions"])
        session.setdefault("process_runs", []).append(execution)
        terminal.execution_id = execution["id"]
        terminal.ended.connect(lambda code: self.finish_execution(session, terminal, execution, code))
        if not terminal.running:
            QTimer.singleShot(0, lambda: self.finish_execution(session, terminal, execution, getattr(terminal, "exited", None)))
        self.terminals[ident] = terminal
        terminal.changed.connect(lambda: self.session_changed(ident))
        index = self.tabs.addTab(terminal, f"{session['agent']} · {session['title'][:28]}")
        self.tabs.setTabToolTip(index, session["workdir"])
        self.tabs.setCurrentIndex(index)
        self.terminal_panel.show()
        self.vertical.setSizes([530, 280])
        self.visibility()
        self.schedule_save()
        self.refresh_executions()
        return True

    def open_session(self, ident):
        terminal = self.terminals.get(ident)
        if not terminal:
            error(
                self,
                "No terminal is connected. Use Resume to open the saved native session.",
            )
            return
        terminal.agent_message = False
        self.session_changed(ident)
        self.workspace.setCurrentIndex(0)
        self.terminal_panel.show()
        self.tabs.setCurrentWidget(terminal)
        self.visibility()
        if self.terminal_popout:
            self.terminal_popout.showNormal()
            self.terminal_popout.raise_()
            self.terminal_popout.activateWindow()
        terminal.setFocus()
        self.select_session(ident)

    def resume_session(self, ident):
        session = self.session(ident)
        if not session:
            return
        terminal = self.terminals.get(ident)
        if terminal and terminal.running:
            self.open_session(ident)
            return
        for job in self.scheduler.jobs:
            for run in job["runs"]:
                if run.get("session_id") == ident and run["status"] == "running":
                    self.open_scheduled_execution(job["id"], run["id"])
                    return
        if not Path(session["workdir"]).is_dir():
            error(self, "This session's working directory is unavailable on this computer. "
                  "Your tasks and saved session link are preserved. You can start a new session locally.")
            return
        registry = agents(self.notebook.data["settings"])
        agent = registry.get(session["agent"])
        if not agent or not agent.resume_args:
            error(self, "This agent profile no longer exists or does not support resume.")
            return
        if not session.get("native_session_id"):
            self.discover_session_ids()
        if not session.get("native_session_id"):
            self.session_details(ident)
            if not session.get("native_session_id"):
                return
        try:
            command = agent.command(session["native_session_id"])
        except ValueError as exc:
            error(self, exc)
            return
        if self.launch(session, command):
            self.open_session(ident)

    def session_details(self, ident):
        session = self.session(ident)
        if not session:
            return
        dialog = DismissibleDialog(self)
        dialog.setWindowTitle("Session details")
        dialog.resize(620, 330)
        layout = QFormLayout(dialog)
        title = QLineEdit(session["title"])
        native = QLineEdit(session.get("native_session_id") or "")
        path = QLineEdit(session["workdir"])
        path.setReadOnly(True)
        layout.addRow("Agent", QLabel(session["agent"]))
        layout.addRow("Label", title)
        layout.addRow("Working directory", path)
        layout.addRow("Native session ID", native)
        hint = QLabel(
            "Enter the exact native session ID from the agent (pi also accepts an absolute session-file path). Do not use a latest-session shortcut or a partial ID. Runtime context use is unknown."
        )
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            value = native.text().strip()
            if value:
                try:
                    self.validate_native_id(session["agent"], value)
                except ValueError as exc:
                    error(self, exc)
                    return
            session.update(title=title.text().strip() or session["title"], native_session_id=value or None)
            self.session_changed(ident)
            self.schedule_save()

    @staticmethod
    def validate_native_id(agent, value):
        import re
        from uuid import UUID

        if any(ord(c) < 32 for c in value) or value.startswith("-"):
            raise ValueError("Invalid native session ID.")
        if agent in ("codex", "claude", "pi"):
            if (
                agent == "pi"
                and Path(value).is_absolute()
                and Path(value).is_file()
                and value.endswith(".jsonl")
            ):
                return
            try:
                UUID(value)
            except ValueError as exc:
                raise ValueError("Enter the full UUID of the native session.") from exc
        if agent == "opencode" and not re.fullmatch(r"ses_[A-Za-z0-9]+", value):
            raise ValueError("OpenCode requires the full session ID (ses_…).")

    def session_changed(self, ident):
        session = self.session(ident)
        terminal = self.terminals.get(ident)
        if session:
            self.tasks.update_session(session)
        self.refresh_executions()
        if not terminal:
            return
        index = self.tabs.indexOf(terminal)
        if index >= 0:
            title = f"{session['agent']} · {session['title'][:28]}" if session else "Session · Link removed"
            self.tabs.setTabText(
                index,
                ("● " if terminal.unread or terminal.agent_message else "")
                + title
                + (" · " + terminal.agent_state if terminal.agent_state else "")
                + (" · New agent message" if terminal.agent_message else "")
                + (" · ended" if not terminal.running else ""),
            )

    def close_terminal(self, index):
        terminal = self.tabs.widget(index)
        if terminal.running:
            if not confirm(
                self,
                "Close terminal",
                "Stop the running agent and its child processes, and close this tab?",
            ):
                return
            terminal.stop_requested = True
            terminal.stop()
            # Keep the tab until termination is confirmed by the backend.
            terminal.ended.connect(lambda code, t=terminal: self.remove_terminal(t))
        else:
            self.remove_terminal(terminal)

    def remove_terminal(self, terminal):
        index = self.tabs.indexOf(terminal)
        if index >= 0:
            self.tabs.removeTab(index)
        ident = next((i for i, t in self.terminals.items() if t is terminal), None)
        if ident:
            del self.terminals[ident]
            session = self.session(ident)
            if session:
                self.tasks.update_session(session)
        terminal.close()
        terminal.deleteLater()
        self.visibility()
        self.refresh_executions()

    def select_session(self, ident):
        self.selected_session = ident
        self.refresh_context()

    def refresh_context(self):
        self.inspector.follow_session(self.session(self.selected_session))

    def visibility(self, *args):
        has_terminals = self.tabs.count() > 0
        self.tabs.setVisible(has_terminals)
        self.terminal_empty.setVisible(not has_terminals)
        for index in range(self.terminal_header.count()):
            widget = self.terminal_header.itemAt(index).widget()
            if widget:
                widget.setVisible(has_terminals)
        if not has_terminals and not self.terminal_popout:
            self.vertical.setSizes([max(1, self.vertical.height() - 48), 48])
        visible = (
            not self.terminal_popout
            and self.isVisible()
            and not self.isMinimized()
            and self.workspace.currentIndex() == 0
            and self.terminal_panel.isVisible()
        )
        for terminal in list(self.terminals.values()):
            terminal.mark_visible(
                (
                    visible
                    or bool(
                        self.terminal_popout
                        and self.terminal_popout.isVisible()
                        and not self.terminal_popout.isMinimized()
                    )
                )
                and terminal is self.tabs.currentWidget()
            )

    def update_terminal_button(self, button, name, label):
        button.setIcon(icon(name))
        button.setAccessibleName(label)
        button.setToolTip(label)

    def toggle_terminal_maximized(self):
        if self.terminal_popout:
            if self.terminal_popout.isMaximized():
                self.terminal_popout.showNormal()
                self.update_terminal_button(self.maximize_terminal_button, "maximize", "Maximize")
            else:
                self.terminal_popout.showMaximized()
                self.update_terminal_button(self.maximize_terminal_button, "restore", "Restore")
            return
        self.terminals_maximized = not self.terminals_maximized
        if self.terminals_maximized:
            self.terminal_split_sizes = self.vertical.sizes()
        self.tasks.setVisible(not self.terminals_maximized)
        self.workspace.tabBar().setVisible(not self.terminals_maximized)
        self.update_terminal_button(self.maximize_terminal_button, "restore" if self.terminals_maximized else "maximize", "Restore" if self.terminals_maximized else "Maximize")
        if not self.terminals_maximized:
            self.vertical.setSizes(self.terminal_split_sizes)
        self.visibility()

    def toggle_terminal_popout(self):
        if self.terminal_popout:
            self.terminal_popout.close()
            return
        if self.terminals_maximized:
            self.toggle_terminal_maximized()
        self.terminal_popout = TerminalPopout(self)
        self.terminal_popout.addActions(self.actions())
        self.terminal_popout.layout().addWidget(self.terminal_panel)
        self.update_terminal_button(self.popout_terminal_button, "dock", "Dock")
        self.terminal_popout.show()
        self.visibility()

    def dock_terminals(self):
        popout = self.terminal_popout
        if popout is None:
            return
        self.vertical.addWidget(self.terminal_panel)
        self.terminal_panel.show()
        self.vertical.setSizes([780, 50])
        self.update_terminal_button(self.popout_terminal_button, "external", "Pop out")
        self.terminal_popout = None
        self.update_terminal_button(self.maximize_terminal_button, "maximize", "Maximize")
        popout.deleteLater()
        self.visibility()

    def paste_terminal(self):
        terminal = self.tabs.currentWidget()
        if terminal:
            # xterm handles bracketed paste and does not submit a prompt automatically.
            text = QApplication.clipboard().text()
            terminal.page().runJavaScript("terminal.paste(" + json.dumps(text) + ")")

    def copy_terminal(self):
        terminal = self.tabs.currentWidget()
        if terminal:
            terminal.page().runJavaScript(
                "terminal.getSelection()", lambda value: QApplication.clipboard().setText(value or "")
            )

    def interrupt_terminal(self):
        terminal = self.tabs.currentWidget()
        if terminal:
            terminal.input("\x03")

    def show_last_reply(self, ident):
        session = self.session(ident)
        if not session:
            return
        session["reply_unread"] = False
        terminal = self.terminals.get(ident)
        if terminal:
            terminal.agent_message = False
        self.tasks.update_session(session)
        self.schedule_save()
        dialog = DismissibleDialog(self)
        dialog.setWindowTitle("Last reply · " + session["title"])
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        reply = session.get("last_reply") or {}
        saved_at = reply.get("saved_at") or "No saved reply"
        try:
            saved_at = datetime.fromisoformat(saved_at).astimezone().strftime("%d.%m.%Y %H:%M")
        except ValueError:
            pass
        layout.addWidget(QLabel(session["agent"] + " · " + saved_at))
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(reply.get("text") or "No assistant reply has been captured for this session yet.")
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def apply_agent_snapshot(self, ident, snapshot):
        session = self.session(ident)
        if not session or not snapshot:
            return
        terminal = self.terminals.get(ident)
        if terminal and snapshot.get("status_known", True):
            terminal.agent_state = (
                "Agent running" if snapshot["busy"] else "Agent error" if snapshot["failed"] else "Ready"
            )
        observed = ident in self.reply_baselined
        self.reply_baselined.add(ident)
        output = snapshot.get("output")
        previous = session.get("last_reply") or {}
        if output and (output != previous.get("text") or snapshot.get("message") != previous.get("message")):
            session["last_reply"] = dict(text=output, message=snapshot.get("message"),
                                         timestamp=snapshot.get("timestamp"), saved_at=now_iso())
            session["reply_unread"] = True
            if terminal:
                execution_id = getattr(terminal, "execution_id", None)
                for execution in session.get("process_runs", []):
                    if execution["id"] == execution_id:
                        execution["last_reply"] = dict(session["last_reply"])
                terminal.agent_message = True
            self.schedule_save()
            # Historical imports are saved quietly; notify only for an observed new reply.
            if (previous or observed or terminal and terminal.agent_baselined) and not self.isActiveWindow():
                self.flush()
                self.notifier.send({"id": "agent:" + ident, "text": "New agent reply · " + session["title"],
                                    "notification_title": "GetItDone · Agent"})
        self.session_changed(ident)

    def poll_agent_status(self):
        if self.status_polling or self.quitting:
            return
        tracked = [dict(s) for s in self.notebook.data["sessions"] if s.get("native_session_id")]
        if not tracked:
            return
        self.status_polling = True

        def loaded(result, exc):
            self.status_polling = False
            if not self.quitting and result:
                for ident, snapshot in result.items():
                    self.apply_agent_snapshot(ident, snapshot)

        Job(lambda: snapshots(tracked), loaded, self)

    def discover_session_ids(self, background=False):
        pending = [
            dict(session)
            for session in self.notebook.data["sessions"]
            if not session.get("native_session_id") and session["agent"] in ("codex", "claude", "pi")
        ]
        if not pending or (background and getattr(self, "discovering_ids", False)):
            return
        baselines = {
            s["id"]: getattr(self.terminals.get(s["id"]), "codex_baseline", None) or set() for s in pending
        }

        def read():
            result = {}
            for session in pending:
                try:
                    candidates = native_sessions(
                        session["agent"], session["workdir"], session["created_at"]
                    )
                except (OSError, ValueError, TypeError, KeyError, RuntimeError, OverflowError):
                    # Native histories are optional local resources, never notebook dependencies.
                    candidates = set()
                result[session["id"]] = candidates - baselines[session["id"]]
            return result

        def apply(result, exc):
            self.discovering_ids = False
            if exc or self.quitting:
                return
            claimed = {s.get("native_session_id") for s in self.notebook.data["sessions"]}
            changed = False
            for ident, candidates in result.items():
                candidates -= claimed
                if len(candidates) != 1:
                    continue
                native = next(iter(candidates))
                # A candidate must belong unambiguously to one notebook session.
                if sum(native in values for values in result.values()) != 1:
                    continue
                session = self.session(ident)
                if session and not session.get("native_session_id"):
                    session["native_session_id"] = native
                    claimed.add(native)
                    changed = True
            if changed:
                self.tasks.rebuild()
                self.schedule_save()

        if background:
            self.discovering_ids = True
            Job(read, apply, self)
        else:
            apply(read(), None)

    def refresh_executions(self):
        if not hasattr(self, "executions"):
            return
        records = execution_records(self.notebook, self.terminals)
        self.executions.refresh(records)
        self.tasks.scheduled_runs = {
            run["session_id"]: run for job in self.scheduler.jobs for run in job["runs"] if run.get("session_id")
        }
        for session in self.notebook.data["sessions"]:
            if session["id"] in self.tasks.scheduled_runs:
                self.tasks.update_session(session)
        live = [r for r in records if r["active"]]
        scheduled = sum(r["origin"] == "Scheduled" for r in live)
        self.execution_indicator.setText(f"{len(live)} running · {scheduled} scheduled" if live else "No agents running")
        self.workspace.setTabText(self.workspace.indexOf(self.executions),
                                  f"Agent executions ({len(live)})" if live else "Agent executions")
        self.workspace.setTabText(self.workspace.indexOf(self.scheduled),
                                  f"Scheduled tasks ({scheduled})" if scheduled else "Scheduled tasks")
        self.tray.setToolTip(f"GetItDone · {len(live)} running · {scheduled} scheduled")

    def finish_execution(self, session, terminal, execution, code):
        if execution["status"] != "running":
            return
        status = "stopped" if getattr(terminal, "stop_requested", False) else (
            "completed" if code == 0 else "interrupted" if code is None else "failed")
        execution.update(status=status, finished_at=now_iso(), exit_code=code)
        self.schedule_save()
        self.refresh_executions()

    def open_scheduled_execution(self, job_id, run_id):
        for index in range(self.scheduled.jobs.count()):
            if self.scheduled.jobs.item(index).data(Qt.UserRole) == job_id:
                self.scheduled.selected_runs[job_id] = run_id
                self.scheduled.jobs.setCurrentRow(index)
                self.scheduled.show_job()
                self.workspace.setCurrentWidget(self.scheduled)
                return

    def tick(self):
        self.scheduler.tick()
        self.refresh_executions()
        # Discovery reads agent files in a worker so large histories cannot freeze typing.
        if not getattr(self, "id_discovery_tick", 0) % 5:
            self.discover_session_ids(background=True)
        self.id_discovery_tick = getattr(self, "id_discovery_tick", 0) + 1
        self.poll_agent_status()
        due = self.reminders.due()
        if due:
            # Persist once-only marker before asking the OS to display anything.
            if self.flush():
                for item in due:
                    self.notifier.send(item)
            else:
                for item in due:
                    item["reminder"]["notified_at"] = None
        minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        if minute != self.minute:
            self.minute = minute
            for ident, row in self.tasks.rows.items():
                self.tasks.reminder_cell(row, self.notebook.get(ident))
        self.visibility()

    def test_notification(self):
        self.notifier.refresh_permission()
        self.notifier.send({"id": "", "text": "Test notification · GetItDone is ready."})
        self.statusBar().showMessage(self.notifier.status, 20000)

    def open_reminder(self, ident):
        if ident.startswith("agent:"):
            self.restore()
            self.show_last_reply(ident[6:])
            return
        self.restore()
        self.workspace.setCurrentIndex(0)
        self.tasks.search.clear()
        self.tasks.status.setCurrentIndex(2)
        self.tasks.rebuild(select=ident)
        if ident in self.tasks.rows:
            self.tasks.tree.scrollToItem(self.tasks.rows[ident])

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.visibility()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.visibility)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibility()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self.visibility()

    def closeEvent(self, event):
        if self.quitting:
            for action in self.actions():
                action.setEnabled(False)
            for terminal in self.terminals.values():
                if not terminal.running:
                    terminal.close()
            event.accept()
            return
        event.ignore()
        if not self.knowledge.save(interactive=True) or not self.flush():
            return
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()
            self.statusBar().showMessage("No system tray is available; the app remains open and minimized.")

    def quit_app(self):
        if self.quitting:
            return
        if not self.knowledge.guard():
            return
        running = [t for t in self.terminals.values() if t.running]
        scheduled_running = len(self.scheduler.active)
        if (running or scheduled_running) and not confirm(
            self,
            "Quit GetItDone",
            f"{len(running)} session(s) and {scheduled_running} scheduled run(s) are running. Stop the agents and their child processes? Reminders are inactive while the app is closed.",
        ):
            return
        self.notebook.data["settings"]["window_geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        if not self.flush():
            return
        self.quitting = True
        self.timer.stop()
        self.scheduler.shutdown()
        self.saver.stop()
        self.setEnabled(False)
        self.statusBar().showMessage("Stopping sessions …")
        for terminal in running:
            terminal.stop_requested = True
            terminal.stop()
        QTimer.singleShot(1800 if running else 0, self.finish_quit)

    def finish_quit(self):
        for terminal in self.terminals.values():
            terminal.force_stop()
        if any(terminal.running for terminal in self.terminals.values()):
            QTimer.singleShot(100, self.finish_quit)
            return
        from PySide6.QtCore import QCoreApplication

        for session in self.notebook.data["sessions"]:
            for execution in session.get("process_runs", []):
                if execution["status"] == "running":
                    execution.update(status="stopped", finished_at=now_iso())
        self.flush()
        for terminal in self.terminals.values():
            terminal.close()
            terminal.deleteLater()
        self.terminals.clear()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.tray.hide()
        self.close()
        QApplication.instance().quit()
