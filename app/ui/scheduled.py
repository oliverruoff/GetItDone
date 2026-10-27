"""Schedule editor and durable per-job output inbox."""
import json
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.agents import agents
from app.models import uid
from app.session_paths import session_folder
from app.ui.common import DismissibleDialog, confirm
from app.ui.icons import icon_button


def readable_output(run, raw=False):
    output = run["output"] if run else ""
    if run and run["agent"] == "codex" and not raw:
        messages = []
        for line in output.splitlines():
            try:
                event = json.loads(line)
                item = event.get("item", {})
                if item.get("type") == "agent_message" and item.get("text"):
                    messages.append(item["text"])
            except (ValueError, AttributeError):
                pass
        if messages:
            output = "\n\n".join(messages)
    if not raw:
        output = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", output)
        output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
    return output


class ScheduleDialog(DismissibleDialog):
    def __init__(self, settings, parent=None, job=None):
        super().__init__(parent)
        self.setWindowTitle("Scheduled task" if job else "New scheduled task")
        self.resize(650, 540)
        self.job = job
        form = QFormLayout(self)
        self.title = QLineEdit(job["title"] if job else "Agent run")
        self.prompt = QPlainTextEdit(job["prompt"] if job else "")
        self.prompt.setPlaceholderText("Prompt sent automatically to the agent …")
        self.agent = QComboBox()
        for agent in agents(settings).values():
            self.agent.addItem(agent.name, agent.id)
        self.agent.setCurrentIndex(max(0, self.agent.findData(job["agent"] if job else settings.get("default_agent"))))
        self.directory = QLineEdit(job["workdir"] if job else str(session_folder(settings)))
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory, 1)
        directory_row.addWidget(icon_button("folder", "Choose working folder", self.choose_folder))
        self.at = QDateTimeEdit()
        self.at.setCalendarPopup(True)
        self.at.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.at.setDateTime(QDateTime(datetime.fromisoformat(job["next_at"]).astimezone())
                            if job and job["next_at"] else QDateTime.currentDateTime().addSecs(300))
        self.repeat = QCheckBox("Repeat every")
        self.every = QSpinBox()
        self.every.setRange(1, 999)
        self.unit = QComboBox()
        self.unit.addItems(["minutes", "hours", "days", "weeks", "months"])
        self.repeat.setChecked(bool(job and job["every"]))
        self.every.setValue(job["every"] if job and job["every"] else 1)
        self.unit.setCurrentText(job["unit"] if job else "days")
        repeat_row = QHBoxLayout()
        for widget in (self.repeat, self.every, self.unit):
            repeat_row.addWidget(widget)
        self.every.setEnabled(self.repeat.isChecked())
        self.unit.setEnabled(self.repeat.isChecked())
        self.repeat.toggled.connect(self.every.setEnabled)
        self.repeat.toggled.connect(self.unit.setEnabled)
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(job["enabled"] if job else True)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        for label, widget in [("Title", self.title), ("Prompt", self.prompt), ("Agent", self.agent),
                              ("Working folder", directory_row), ("Next run (local time)", self.at),
                              ("Recurrence", repeat_row), ("", self.enabled), ("", self.problem)]:
            form.addRow(label, widget)
        hint = QLabel("Custom profiles must use noninteractive arguments. The prompt is appended as one argument.")
        hint.setWordWrap(True)
        form.addRow(hint)
        def show_profile_hint():
            hint.setVisible(self.agent.currentData() not in {"opencode", "codex", "claude", "pi"})
        self.agent.currentIndexChanged.connect(show_profile_hint)
        show_profile_hint()
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def choose_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Working folder", self.directory.text())
        if directory:
            self.directory.setText(directory)

    def save(self):
        if not self.title.text().strip() or not self.prompt.toPlainText().strip():
            self.problem.setText("Enter a title and a prompt.")
            return
        if not Path(self.directory.text()).is_dir():
            self.problem.setText("Choose an available working folder.")
            return
        self.values = dict(title=self.title.text().strip(), prompt=self.prompt.toPlainText(),
                           agent=self.agent.currentData(), workdir=str(Path(self.directory.text()).resolve()),
                           next_at=self.at.dateTime().toPython().astimezone().isoformat(),
                           every=self.every.value() if self.repeat.isChecked() else 0,
                           unit=self.unit.currentText(), enabled=self.enabled.isChecked())
        self.accept()


class Scheduled(QWidget):
    session_open = Signal(str)
    session_details = Signal(str)

    def __init__(self, scheduler, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler
        self.selected_runs = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        split = QSplitter()
        layout.addWidget(split, 1)

        sidebar = QWidget()
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(0, 0, 10, 0)
        heading = QLabel("Scheduled tasks")
        heading.setObjectName("documentTitle")
        left.addWidget(heading)
        self.jobs = QListWidget()
        self.jobs.setMinimumWidth(230)
        self.jobs.setWordWrap(False)
        self.jobs.setTextElideMode(Qt.ElideRight)
        self.jobs.currentItemChanged.connect(self.show_job)
        left.addWidget(self.jobs, 1)
        self.actions = {}
        new = QPushButton("+ New scheduled task")
        new.setObjectName("addTask")
        new.clicked.connect(self.create)
        self.actions["New scheduled task"] = new
        left.addWidget(new)
        hint = QLabel("Schedules run while GetItDone is open,\nincluding in the background. All times are local.")
        hint.setStyleSheet("color: #64738b; font-size: 11px;")
        hint.setWordWrap(True)
        left.addWidget(hint)
        split.addWidget(sidebar)

        content = QWidget()
        right = QVBoxLayout(content)
        right.setContentsMargins(10, 0, 0, 0)
        self.details = QLabel("Select a scheduled task")
        self.details.setObjectName("documentTitle")
        self.details.setTextFormat(Qt.PlainText)
        self.details.setWordWrap(True)
        right.addWidget(self.details)
        controls = QHBoxLayout()
        for key, text, callback in [
            ("Edit schedule", "Edit schedule", self.edit),
            ("Run now", "Run now", self.run_now),
            ("Stop running job", "Stop run", self.stop),
            ("Delete schedule and inbox", "Delete…", self.delete),
        ]:
            button = QPushButton(text)
            button.setToolTip(key)
            button.clicked.connect(callback)
            self.actions[key] = button
            controls.addWidget(button)
        self.pause = QPushButton("Pause")
        self.pause.clicked.connect(self.toggle)
        controls.insertWidget(2, self.pause)
        controls.addStretch()
        right.addLayout(controls)
        self.schedule_info = QLabel()
        self.schedule_info.setTextFormat(Qt.PlainText)
        self.schedule_info.setWordWrap(True)
        right.addWidget(self.schedule_info)
        self.task_toggle = QPushButton("Show task details")
        self.task_toggle.setCheckable(True)
        self.task_toggle.setMaximumWidth(180)
        right.addWidget(self.task_toggle)
        self.task_context = QPlainTextEdit()
        self.task_context.setReadOnly(True)
        self.task_context.setMaximumHeight(105)
        self.task_context.hide()
        self.task_toggle.toggled.connect(self.task_context.setVisible)
        self.task_toggle.toggled.connect(
            lambda checked: self.task_toggle.setText("Hide task details" if checked else "Show task details")
        )
        right.addWidget(self.task_context)

        history_header = QHBoxLayout()
        history_title = QLabel("Run history")
        history_title.setStyleSheet("font-weight: 600; padding-top: 8px;")
        history_header.addWidget(history_title)
        self.summary = QLabel()
        self.summary.setStyleSheet("color: #52647e; padding-top: 8px;")
        history_header.addWidget(self.summary)
        history_header.addStretch()
        right.addLayout(history_header)
        history = QSplitter(Qt.Vertical)
        self.runs = QTreeWidget()
        self.runs.setHeaderLabels(["Run", "Started", "Finished", "Duration", "Status"])
        self.runs.setRootIsDecorated(False)
        self.runs.setSelectionMode(QAbstractItemView.SingleSelection)
        self.runs.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.runs.setStyleSheet("QTreeWidget::item:selected { background: #dce9f7; color: #172b43; }")
        self.runs.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.runs.setAlternatingRowColors(True)
        self.runs.setMinimumHeight(110)
        self.runs.setColumnWidth(0, 48)
        self.runs.setColumnWidth(1, 170)
        self.runs.setColumnWidth(2, 170)
        self.runs.setColumnWidth(3, 80)
        self.runs.header().setSectionResizeMode(4, QHeaderView.Stretch)
        self.runs.currentItemChanged.connect(self.show_run)
        history.addWidget(self.runs)
        viewer = QWidget()
        output_layout = QVBoxLayout(viewer)
        output_layout.setContentsMargins(0, 4, 0, 0)
        output_bar = QHBoxLayout()
        self.output_title = QLabel("Output")
        self.output_title.setStyleSheet("font-weight: 600;")
        output_bar.addWidget(self.output_title)
        output_bar.addStretch()
        self.raw = QCheckBox("Raw process output")
        self.raw.toggled.connect(self.show_run)
        output_bar.addWidget(self.raw)
        self.copy_button = QPushButton("Copy output")
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.output.toPlainText()))
        output_bar.addWidget(self.copy_button)
        output_layout.addLayout(output_bar)
        self.run_info = QLabel()
        self.run_info.setTextFormat(Qt.PlainText)
        self.run_info.setWordWrap(True)
        self.run_info.setStyleSheet("color: #52647e;")
        output_layout.addWidget(self.run_info)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Select a run above to read its saved output.")
        output_layout.addWidget(self.output, 1)
        links = QHBoxLayout()
        self.run_toggle = QPushButton("Run details")
        self.run_toggle.setCheckable(True)
        links.addWidget(self.run_toggle)
        links.addStretch()
        self.open_button = QPushButton("Resume session")
        self.open_button.clicked.connect(self.open_session)
        self.details_button = QPushButton("Session details")
        self.details_button.clicked.connect(self.open_details)
        links.addWidget(self.open_button)
        links.addWidget(self.details_button)
        output_layout.addLayout(links)
        self.run_context = QPlainTextEdit()
        self.run_context.setReadOnly(True)
        self.run_context.setMaximumHeight(100)
        self.run_context.hide()
        self.run_toggle.toggled.connect(self.run_context.setVisible)
        output_layout.addWidget(self.run_context)
        history.addWidget(viewer)
        history.setSizes([170, 360])
        right.addWidget(history, 1)
        split.addWidget(content)
        split.setSizes([300, 1000])
        split.setStretchFactor(1, 1)
        scheduler.changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def local_time(value):
        if not value:
            return "—"
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%d %b %Y, %H:%M:%S")
        except (ValueError, TypeError, OverflowError, OSError):
            return "Unknown"

    @staticmethod
    def duration(run):
        if not run.get("finished_at"):
            return "—"
        seconds = max(0, int((datetime.fromisoformat(run["finished_at"]) -
                              datetime.fromisoformat(run["started_at"])).total_seconds()))
        if seconds < 60:
            return f"{seconds}s"
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes}m {seconds:02d}s"

    @staticmethod
    def job_state(job, active):
        if active:
            return "Running"
        if job["next_at"] is None:
            return "Finished"
        return "Enabled" if job["enabled"] else "Paused"

    def current_job(self):
        row = self.jobs.currentItem()
        return next((job for job in self.scheduler.jobs if row and job["id"] == row.data(Qt.UserRole)), None)

    def current_run(self):
        job, row = self.current_job(), self.runs.currentItem()
        return next((run for run in job["runs"] if row and run["id"] == row.data(0, Qt.UserRole)), None) if job else None

    def refresh(self):
        job = self.current_job()
        selected = job["id"] if job else None
        self.jobs.blockSignals(True)
        self.jobs.clear()
        for job in self.scheduler.jobs:
            state = self.job_state(job, job["id"] in self.scheduler.active)
            next_at = self.local_time(job["next_at"]) if job["next_at"] else "No further runs"
            count = len(job["runs"])
            date_label = "Next" if job["enabled"] else "Planned"
            row = QListWidgetItem(f"{job['title']}\n{state} · {count} {'run' if count == 1 else 'runs'}\n{date_label}: {next_at}")
            row.setToolTip(row.text())
            row.setSizeHint(QSize(230, 76))
            row.setData(Qt.UserRole, job["id"])
            self.jobs.addItem(row)
            if job["id"] == selected:
                self.jobs.setCurrentItem(row)
        if not self.jobs.currentItem() and self.jobs.count():
            self.jobs.setCurrentRow(0)
        self.jobs.blockSignals(False)
        self.show_job()

    def show_job(self, *args):
        job = self.current_job()
        selected = self.selected_runs.get(job["id"]) if job else None
        self.runs.blockSignals(True)
        self.runs.clear()
        active = bool(job and job["id"] in self.scheduler.active)
        if job:
            self.details.setText(job["title"])
            repeat = (f"Every {job['unit'].removesuffix('s')}" if job["every"] == 1 else
                      f"Every {job['every']} {job['unit']}" if job["every"] else "One-time schedule")
            state = self.job_state(job, active)
            next_label = self.local_time(job["next_at"]) if job["next_at"] else "No further runs scheduled"
            date_label = "Next run" if job["enabled"] else "Planned time (paused)" if job["next_at"] else "Next run"
            self.schedule_info.setText(f"{state} · {job['agent']} · {repeat}\n{date_label}: {next_label}")
            self.task_context.setPlainText(f"Working folder: {job['workdir']}\n\n{job['prompt']}")
            counts = {state: sum(r["status"] == state for r in job["runs"])
                      for state in ("completed", "failed", "interrupted", "running")}
            parts = [f"{len(job['runs'])} total"] + [f"{count} {state}" for state, count in counts.items() if count]
            self.summary.setText(" · ".join(parts))
            for number, run in reversed(list(enumerate(job["runs"], 1))):
                row = QTreeWidgetItem([f"#{number}", self.local_time(run["started_at"]),
                                       self.local_time(run.get("finished_at")), self.duration(run),
                                       run["status"].capitalize()])
                row.setData(0, Qt.UserRole, run["id"])
                color = {"completed": "#28714c", "failed": "#a63434", "running": "#23588b"}.get(run["status"], "#64738b")
                row.setForeground(4, QColor(color))
                self.runs.addTopLevelItem(row)
                if run["id"] == selected:
                    self.runs.setCurrentItem(row)
        else:
            self.details.setText("Create your first scheduled task")
            self.schedule_info.setText("Choose an agent, a prompt and a time using + New scheduled task.")
            self.task_context.clear()
            self.summary.setText("No runs yet")
        if not self.runs.currentItem() and self.runs.topLevelItemCount():
            self.runs.setCurrentItem(self.runs.topLevelItem(0))
        self.runs.blockSignals(False)
        for title in ("Edit schedule", "Run now", "Delete schedule and inbox"):
            self.actions[title].setEnabled(bool(job) and not active)
        self.actions["Stop running job"].setEnabled(active)
        self.actions["Stop running job"].setVisible(active)
        self.pause.setEnabled(bool(job))
        self.pause.setText("Pause" if job and job["enabled"] else "Schedule again" if job and not job["next_at"] else "Enable")
        self.task_toggle.setEnabled(bool(job))
        self.show_run()

    def show_run(self, *args):
        job, run = self.current_job(), self.current_run()
        if job and run:
            self.selected_runs[job["id"]] = run["id"]
        output = readable_output(run, self.raw.isChecked())
        if self.output.toPlainText() != output:
            self.output.setPlainText(output)
        self.output.setPlaceholderText("Waiting for output…" if run and run["status"] == "running" else
                                       "This run produced no output." if run else
                                       "No runs yet. Output will appear here after the first run.")
        if run:
            number = next(i for i, r in enumerate(job["runs"], 1) if r["id"] == run["id"])
            self.output_title.setText(f"Output · Run #{number}")
            exit_code = f" · Exit code {run['exit_code']}" if run.get("exit_code") is not None else ""
            self.run_info.setText(f"{run['status'].capitalize()} · {self.local_time(run['started_at'])} · "
                                  f"{self.duration(run)}{exit_code}")
            self.run_context.setPlainText(f"Agent: {run['agent']}\nWorking folder: {run['workdir']}\n\n{run['prompt']}")
        else:
            self.output_title.setText("Output")
            self.run_info.setText("Select a run to view its saved output. No agent needs to be started.")
            self.run_context.clear()
        self.copy_button.setEnabled(bool(output))
        self.raw.setEnabled(bool(run))
        self.run_toggle.setEnabled(bool(run))
        linked = bool(run and run.get("session_id") and any(
            s["id"] == run["session_id"] for s in self.scheduler.notebook.data["sessions"]))
        self.open_button.setEnabled(linked and run["status"] != "running")
        self.details_button.setEnabled(linked)

    def create(self):
        dialog = ScheduleDialog(self.scheduler.notebook.data["settings"], self)
        if dialog.exec():
            self.scheduler.jobs.append(dict(id=uid(), runs=[], **dialog.values))
            self.scheduler.persist()
            self.refresh()
            self.jobs.setCurrentRow(self.jobs.count() - 1)

    def edit(self):
        job = self.current_job()
        if job:
            dialog = ScheduleDialog(self.scheduler.notebook.data["settings"], self, job)
            if job["next_at"] is None:
                dialog.enabled.setChecked(True)
            if dialog.exec():
                job.update(dialog.values)
                self.scheduler.persist()
                self.refresh()

    def toggle(self):
        job = self.current_job()
        if job and job["next_at"] is None:
            self.edit()
            return
        if job:
            job["enabled"] = not job["enabled"]
            self.scheduler.persist()
            self.refresh()

    def run_now(self):
        if self.current_job():
            self.scheduler.start(self.current_job(), manual=True)
            if self.runs.topLevelItemCount():
                self.runs.setCurrentItem(self.runs.topLevelItem(0))

    def stop(self):
        if self.current_job():
            self.scheduler.stop(self.current_job())

    def delete(self):
        job = self.current_job()
        if job and job["id"] not in self.scheduler.active and confirm(
                self, "Delete schedule", "Delete this schedule and its saved inbox? Session links remain in Tasks."):
            self.scheduler.jobs.remove(job)
            self.scheduler.persist()
            self.refresh()

    def open_session(self):
        run = self.current_run()
        if run and run.get("session_id"):
            self.session_open.emit(run["session_id"])

    def open_details(self):
        run = self.current_run()
        if run and run.get("session_id"):
            self.session_details.emit(run["session_id"])
