"""Live processes and durable history, with direct links to their sessions."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.scheduled import Scheduled, readable_output


class Executions(QWidget):
    session_open = Signal(str)
    session_details = Signal(str)
    scheduled_open = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []
        self.signature = None
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        title = QLabel("Agent executions")
        title.setObjectName("documentTitle")
        bar.addWidget(title)
        self.summary = QLabel()
        bar.addWidget(self.summary)
        bar.addStretch()
        self.filter = QComboBox()
        self.filter.addItems(["All executions", "Running", "History"])
        self.filter.setAccessibleName("Execution filter")
        self.filter.currentIndexChanged.connect(lambda: self.refresh(self.records))
        bar.addWidget(self.filter)
        layout.addLayout(bar)
        hint = QLabel("All agent processes launched from this notebook. Open terminals can be idle; saved history stays available after restart.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64738b;")
        layout.addWidget(hint)
        split = QSplitter(Qt.Vertical)
        self.table = QTreeWidget()
        self.table.setAccessibleName("Agent execution history")
        self.table.setHeaderLabels(["Execution", "Agent", "Origin", "State", "Started", "Finished"])
        self.table.setRootIsDecorated(False)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTreeWidget::item:selected { background: #dce9f7; color: #172b43; }")
        for index, width in enumerate([300, 95, 105, 150, 170, 170]):
            self.table.setColumnWidth(index, width)
        self.table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.currentItemChanged.connect(self.show_record)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_session())
        split.addWidget(self.table)
        viewer = QWidget()
        body = QVBoxLayout(viewer)
        body.setContentsMargins(0, 6, 0, 0)
        self.details = QLabel("Select an execution")
        self.details.setTextFormat(Qt.PlainText)
        self.details.setWordWrap(True)
        body.addWidget(self.details)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        body.addWidget(self.output, 1)
        buttons = QHBoxLayout()
        self.open_button = QPushButton("Open session")
        self.open_button.clicked.connect(self.open_session)
        self.schedule_button = QPushButton("View scheduled run")
        self.schedule_button.clicked.connect(self.open_scheduled)
        self.details_button = QPushButton("Session details")
        self.details_button.clicked.connect(self.open_details)
        self.copy_button = QPushButton("Copy output")
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.output.toPlainText()))
        for button in (self.open_button, self.schedule_button, self.details_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(self.copy_button)
        body.addLayout(buttons)
        split.addWidget(viewer)
        split.setSizes([340, 260])
        layout.addWidget(split, 1)
        self.refresh([])

    def current_record(self):
        row = self.table.currentItem()
        ident = row.data(0, Qt.UserRole) if row else None
        return next((r for r in self.records if r["id"] == ident), None)

    def refresh(self, records):
        current = self.current_record()
        selected = current["id"] if current else None
        self.records = records
        live = [r for r in records if r["active"]]
        scheduled = sum(r["origin"] == "Scheduled" for r in live)
        self.summary.setText(f"{len(live)} running · {scheduled} scheduled · {len(records)-len(live)} in history")
        mode = self.filter.currentIndex()
        visible = [r for r in records if mode == 0 or (r["active"] if mode == 1 else not r["active"])]
        signature = tuple((r["id"], r["title"], r["agent"], r["origin"], r["status"], r["active"],
                           r["started_at"], r["finished_at"]) for r in visible)
        if signature != self.signature:
            self.signature = signature
            self.table.blockSignals(True)
            self.table.clear()
            for record in visible:
                row = QTreeWidgetItem([record["title"], record["agent"], record["origin"], record["status"],
                                       Scheduled.local_time(record["started_at"]), Scheduled.local_time(record["finished_at"])])
                row.setData(0, Qt.UserRole, record["id"])
                row.setToolTip(0, record["title"])
                color = "#23588b" if record["active"] else "#a63434" if record["status"] in ("Failed", "Interrupted") else "#52647e"
                row.setForeground(3, QColor(color))
                self.table.addTopLevelItem(row)
                if record["id"] == selected:
                    self.table.setCurrentItem(row)
            if not self.table.currentItem() and self.table.topLevelItemCount():
                self.table.setCurrentItem(self.table.topLevelItem(0))
            self.table.blockSignals(False)
        self.show_record()

    def show_record(self, *_):
        record = self.current_record()
        text = ""
        if record:
            self.details.setText(f"{record['title']} · {record['status']}\n{record['agent']} · {record['workdir']}")
            text = readable_output(dict(output=record["output"], agent=record["output_agent"]))
            self.output.setPlaceholderText("Output is being collected…" if record["active"] and record["job_id"] else
                                           "Open the running terminal to follow this session. No reply has been saved for this execution yet." if record["active"] else
                                           "No output was saved for this execution. Its session link is still available.")
        else:
            self.details.setText("No matching executions")
            self.output.setPlaceholderText("Start an agent from a todo or create a scheduled task. Its execution will appear here.")
        if text != self.output.toPlainText():
            self.output.setPlainText(text)
        linked = bool(record and record["session_id"])
        self.open_button.setEnabled(linked or bool(record and record["active"] and record["job_id"]))
        self.open_button.setText("View live output" if record and record["active"] and record["job_id"] else
                                 "Focus terminal" if record and record["active"] else "Resume session")
        self.details_button.setEnabled(linked)
        self.schedule_button.setEnabled(bool(record and record["job_id"]))
        self.copy_button.setEnabled(bool(text))

    def open_session(self):
        record = self.current_record()
        if record and record["job_id"] and record["active"]:
            self.scheduled_open.emit(record["job_id"], record["run_id"])
        elif record and record["session_id"]:
            self.session_open.emit(record["session_id"])

    def open_details(self):
        record = self.current_record()
        if record and record["session_id"]:
            self.session_details.emit(record["session_id"])

    def open_scheduled(self):
        record = self.current_record()
        if record and record["job_id"]:
            self.scheduled_open.emit(record["job_id"], record["run_id"])
