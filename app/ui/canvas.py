from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget

from app.canvas import prepare_canvas
from app.terminal.bridge import Terminal
from app.ui.common import Job, confirm, error
from app.ui.dialogs import SessionDialog
from app.ui.theme import color, is_dark


class CanvasPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if is_main_frame and navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if url.scheme() in ("http", "https", "mailto"):
                QDesktopServices.openUrl(url)
                return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class Canvas(QWidget):
    def __init__(self, data_folder, settings, parent=None):
        super().__init__(parent)
        self.folder = prepare_canvas(data_folder)
        self.session_settings = settings
        self.terminals = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        self.view = QWebEngineView(self)
        # Keep WebEngine's GPU surface in a native child. Otherwise the first
        # lazy-loaded view makes Qt destroy/recreate the visible main window.
        self.view.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.view.setAttribute(Qt.WA_NativeWindow)
        self.view.setPage(CanvasPage(self.view))
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        self.apply_theme()
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(self.view)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_terminal)
        self.splitter.addWidget(self.tabs)
        self.tabs.hide()
        layout.addWidget(self.splitter, 1)
        footer = QHBoxLayout()
        label = QLabel(str(self.folder))
        label.setToolTip("This entire folder is included in full ZIP backups. External files are not.")
        footer.addWidget(label, 1)
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self.reload)
        footer.addWidget(reload_button)
        self.agent_button = QPushButton("Open agent …")
        self.agent_button.clicked.connect(self.open_agent)
        footer.addWidget(self.agent_button)
        layout.addLayout(footer)
        self.snapshot = None
        self.scanning = False
        self.reload()
        # Polling also catches atomic replacements and nested asset changes.
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.queue_check_changes)
        self.timer.start()
        QTimer.singleShot(0, self.queue_check_changes)

    def apply_theme(self):
        self.view.page().setBackgroundColor(QColor(color("base")))
        # Rendering only: never rewrite the user's HTML or CSS on disk.
        force_dark = getattr(QWebEngineSettings.WebAttribute, "ForceDarkMode", None)
        if force_dark is not None:
            self.view.settings().setAttribute(force_dark, is_dark())

    def open_agent(self):
        dialog = SessionDialog(self.session_settings, self, fixed_directory=self.folder.resolve())
        dialog.setWindowTitle("Canvas agent")
        if not dialog.exec():
            return
        terminal = Terminal(self)
        try:
            terminal.start(dialog.command, str(self.folder.resolve()))
        except Exception as exc:
            terminal.deleteLater()
            error(self, f"Could not start Canvas agent: {exc}")
            return
        self.terminals.append(terminal)
        index = self.tabs.addTab(terminal, dialog.agent.currentText())
        self.tabs.setCurrentIndex(index)
        self.tabs.show()
        self.splitter.setSizes([650, 300])

    def close_terminal(self, index):
        terminal = self.tabs.widget(index)
        if terminal.running and not confirm(self, "Close Canvas agent", "Stop this agent and its child processes?"):
            return
        if terminal.running:
            terminal.ended.connect(lambda _code: self.remove_terminal(terminal))
            terminal.stop()
            return
        self.remove_terminal(terminal)

    def remove_terminal(self, terminal):
        if terminal not in self.terminals:
            return
        terminal.close()
        self.tabs.removeTab(self.tabs.indexOf(terminal))
        self.terminals.remove(terminal)
        terminal.deleteLater()
        self.tabs.setVisible(bool(self.terminals))

    def file_snapshot(self):
        result = []
        for path in self.folder.rglob("*"):
            try:
                if path.is_file():
                    info = path.stat()
                    result.append((str(path), info.st_mtime_ns, info.st_size))
            except OSError:
                continue
        return sorted(result)

    def check_changes(self):
        snapshot = self.file_snapshot()
        if snapshot != self.snapshot:
            self.snapshot = snapshot
            self.reload()

    def queue_check_changes(self):
        # Never walk a large asset tree in the input/painting thread, or scan
        # a hidden Canvas while the user is working on todos.
        if self.scanning or not self.isVisible():
            return
        self.scanning = True

        def loaded(snapshot, exc):
            self.scanning = False
            if exc is None and snapshot != self.snapshot:
                self.snapshot = snapshot
                self.reload()

        Job(self.file_snapshot, loaded, self)

    def reload(self):
        url = QUrl.fromLocalFile(str((self.folder / "canvas.html").resolve()))
        if self.view.url() != url:
            self.view.load(url)
        else:
            self.view.page().triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache)
