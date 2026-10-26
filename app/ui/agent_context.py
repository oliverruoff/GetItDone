"""Independent, asynchronous agent context inspector."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.agents import agents
from app.agents.base import executable_path
from app.session_paths import session_folder
from app.ui.common import Job, SafeBrowser
from app.ui.icons import icon_button


class AgentContextPanel(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.generation = 0
        self.workdir = str(session_folder(settings))
        self.adapters = agents(settings)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 0, 0, 0)
        header = QHBoxLayout()
        title = QLabel("Agent context")
        title.setStyleSheet("font-weight:600;font-size:15px")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(icon_button("refresh", "Refresh installed agents and context", self.refresh))
        layout.addLayout(header)
        self.agent = QComboBox()
        self.agent.setToolTip("Installed coding agents. Select one to inspect its context.")
        layout.addWidget(self.agent)
        self.folder = QPushButton()
        self.folder.clicked.connect(self.choose_folder)
        layout.addWidget(self.folder)
        self.status = QLabel("Checking installed agents …")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        explanation = QLabel(
            "Loaded in session: not reported by these CLIs. Skills are available on demand. MCP connection status is shown when reported. Instructions below are local sources for this folder; a running session may have an older snapshot or extra CLI instructions."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color:#697586;font-size:11px")
        layout.addWidget(explanation)
        self.tabs = QTabWidget()
        self.lists = {}
        for kind, title in [("Skill", "Skills"), ("MCP", "MCPs"), ("Instructions", "Instructions")]:
            listing = QListWidget()
            listing.currentItemChanged.connect(self.show_finding)
            listing.setWordWrap(True)
            listing.setSpacing(4)
            self.tabs.addTab(listing, title)
            self.lists[kind] = listing
        self.preview = SafeBrowser()
        self.preview.setPlaceholderText("Select a source to read its contents.")
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.preview)
        splitter.setSizes([250, 260])
        layout.addWidget(splitter)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.agent.currentIndexChanged.connect(self.load)
        self.update_folder()
        QTimer.singleShot(0, self.refresh)

    def update_folder(self):
        self.folder.setText("Folder: " + Path(self.workdir).name + " …")
        self.folder.setToolTip(self.workdir + "\nClick to choose a working folder")

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Agent working folder", self.workdir)
        if folder:
            self.workdir = folder
            self.update_folder()
            self.load()

    def refresh(self):
        self.adapters = agents(self.settings)
        previous = self.agent.currentData() or self.settings.get("default_agent")
        self.agent.blockSignals(True)
        self.agent.clear()
        missing = []
        for ident, adapter in self.adapters.items():
            if executable_path(adapter.executable):
                self.agent.addItem(adapter.name, ident)
            else:
                missing.append(adapter.name)
        index = self.agent.findData(previous)
        if index >= 0:
            self.agent.setCurrentIndex(index)
        self.agent.blockSignals(False)
        self.agent.setToolTip(
            "Not installed: " + ", ".join(missing) if missing else "All configured agents are installed"
        )
        self.load()

    def follow_session(self, session):
        if not session:
            return
        self.workdir = session["workdir"]
        self.update_folder()
        self.agent.blockSignals(True)
        index = self.agent.findData(session["agent"])
        if index >= 0:
            self.agent.setCurrentIndex(index)
        self.agent.blockSignals(False)
        self.load()

    def load(self, *_):
        self.generation += 1
        generation = self.generation
        adapter = self.adapters.get(self.agent.currentData())
        for listing in self.lists.values():
            listing.clear()
        self.preview.clear()
        if not adapter:
            self.status.setText(
                "No supported coding CLI found. Install an agent or add a custom profile in Settings."
            )
            return
        folder = self.workdir
        self.status.setText("Reading agent context …")

        def finished(result, exc):
            if generation != self.generation:
                return
            if exc:
                self.status.setText("Context could not be read. Check folder permissions and refresh.")
                return
            version, (stamp, findings) = result
            notices = [f.name for f in findings if f.kind == "Notice"]
            self.status.setText(
                f"{adapter.name} · {version}\nUpdated {stamp[11:19]}"
                + ("\n" + "\n".join(notices) if notices else "")
            )
            for kind, listing in self.lists.items():
                matches = [f for f in findings if f.kind == kind]
                for finding in matches:
                    item = QListWidgetItem(f"{finding.name}\n{finding.scope} · {finding.state}")
                    item.setToolTip(finding.path)
                    item.setData(Qt.UserRole, finding)
                    listing.addItem(item)
                if not matches:
                    item = QListWidgetItem(
                        "No local sources found"
                        if kind != "MCP"
                        else "No MCP servers configured in inspected sources"
                    )
                    item.setFlags(Qt.NoItemFlags)
                    listing.addItem(item)
                self.tabs.setTabText(
                    self.tabs.indexOf(listing),
                    f"{'Skills' if kind == 'Skill' else 'MCPs' if kind == 'MCP' else 'Instructions'} ({len(matches)})",
                )
            self.tab_changed()

        Job(lambda: (adapter.probe(), adapter.context(folder)), finished, self)

    def tab_changed(self, *_):
        listing = self.tabs.currentWidget()
        if listing.currentRow() < 0 and listing.count():
            listing.setCurrentRow(0)
        self.show_finding(listing.currentItem())

    def show_finding(self, item, *_):
        finding = item.data(Qt.UserRole) if item else None
        if not finding:
            self.preview.setPlainText(
                "No sources to display. Additional plugins or CLI options may provide context outside these locations."
            )
            return
        # Plain text avoids remote resource loads and treats instruction documents as data.
        self.preview.setPlainText(
            f"{finding.name}\n{finding.scope} · {finding.state}\n{finding.path}\n\n{finding.content}"
        )
