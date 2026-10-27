"""Schedule editor and durable per-job output inbox."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.agents import agents
from app.models import uid
from app.session_paths import session_folder
from app.ui.common import DismissibleDialog, confirm
from app.ui.icons import icon_button


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
        self.at.setDisplayFormat("yyyy-MM-dd HH:mm")
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
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(job["enabled"] if job else True)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        for label, widget in [("Title", self.title), ("Prompt", self.prompt), ("Agent", self.agent),
                              ("Working folder", directory_row), ("Date and time (local)", self.at),
                              ("Recurrence", repeat_row), ("", self.enabled), ("", self.problem)]:
            form.addRow(label, widget)
        hint = QLabel("Custom profiles must use noninteractive arguments. The prompt is appended as one argument.")
        hint.setWordWrap(True)
        form.addRow(hint)
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
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.actions = {}
        for name, title, callback in [("plus", "New scheduled task", self.create),
                                      ("note", "Edit schedule", self.edit),
                                      ("play", "Run now", self.run_now),
                                      ("stop", "Stop running job", self.stop),
                                      ("trash", "Delete schedule and inbox", self.delete)]:
            button = icon_button(name, title, callback)
            if name == "plus":
                button.setText("New scheduled task")
                button.setMinimumWidth(175)
                button.setMaximumWidth(220)
            self.actions[title] = button
            toolbar.addWidget(button)
        self.pause = QPushButton("Pause / enable")
        self.pause.clicked.connect(self.toggle)
        toolbar.addWidget(self.pause)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        hint = QLabel("Runs while GetItDone is open, including in the background. Missed dates run once on reopening; "
                      "recurring jobs then continue at the next date. Inbox saves the last 1 MB per run.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        split = QSplitter()
        self.jobs = QListWidget()
        self.jobs.currentItemChanged.connect(self.show_job)
        split.addWidget(self.jobs)
        inbox = QWidget()
        right = QVBoxLayout(inbox)
        self.details = QLabel("Select a scheduled task")
        self.details.setTextFormat(Qt.PlainText)
        self.details.setWordWrap(True)
        right.addWidget(self.details)
        self.runs = QListWidget()
        self.runs.currentItemChanged.connect(self.show_run)
        right.addWidget(self.runs, 1)
        self.raw = QCheckBox("Raw process output")
        self.raw.toggled.connect(self.show_run)
        right.addWidget(self.raw)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        right.addWidget(self.output, 3)
        links = QHBoxLayout()
        self.open_button = QPushButton("Open / resume session")
        self.open_button.clicked.connect(self.open_session)
        self.details_button = QPushButton("Session details")
        self.details_button.clicked.connect(self.open_details)
        links.addWidget(self.open_button)
        links.addWidget(self.details_button)
        right.addLayout(links)
        split.addWidget(inbox)
        split.setSizes([280, 800])
        layout.addWidget(split, 1)
        scheduler.changed.connect(self.refresh)
        self.refresh()

    def current_job(self):
        row = self.jobs.currentItem()
        return next((job for job in self.scheduler.jobs if row and job["id"] == row.data(Qt.UserRole)), None)

    def current_run(self):
        job, row = self.current_job(), self.runs.currentItem()
        return next((run for run in job["runs"] if row and run["id"] == row.data(Qt.UserRole)), None) if job else None

    def refresh(self):
        job = self.current_job()
        selected = job["id"] if job else None
        self.jobs.blockSignals(True)
        self.jobs.clear()
        for job in self.scheduler.jobs:
            state = "Enabled" if job["enabled"] else "Finished" if job["next_at"] is None else "Paused"
            row = QListWidgetItem(f"{job['title']} · {state} · {len(job['runs'])} runs")
            row.setData(Qt.UserRole, job["id"])
            self.jobs.addItem(row)
            if job["id"] == selected:
                self.jobs.setCurrentItem(row)
        self.jobs.blockSignals(False)
        if not self.jobs.currentItem() and self.jobs.count():
            self.jobs.setCurrentRow(0)
        else:
            self.show_job()

    def show_job(self, *args):
        job, run = self.current_job(), self.current_run()
        selected = run["id"] if run else None
        self.runs.blockSignals(True)
        self.runs.clear()
        if job:
            repeat = f"Every {job['every']} {job['unit']}" if job["every"] else "Once"
            self.details.setText(f"{job['title']} · {job['agent']} · {repeat}\nNext: {job['next_at'] or '—'}\n"
                                 f"{job['workdir']}\n\n{job['prompt']}")
            for run in reversed(job["runs"]):
                row = QListWidgetItem(f"{datetime.fromisoformat(run['started_at']).astimezone():%Y-%m-%d %H:%M:%S} · {run['status']}")
                row.setData(Qt.UserRole, run["id"])
                self.runs.addItem(row)
                if run["id"] == selected:
                    self.runs.setCurrentItem(row)
        else:
            self.details.setText("Create a scheduled task with +")
        self.runs.blockSignals(False)
        if not self.runs.currentItem() and self.runs.count():
            self.runs.setCurrentRow(0)
        active = bool(job and job["id"] in self.scheduler.active)
        for title in ("Edit schedule", "Run now", "Delete schedule and inbox"):
            self.actions[title].setEnabled(bool(job) and not active)
        self.actions["Stop running job"].setEnabled(active)
        self.pause.setEnabled(bool(job))
        self.pause.setText("Pause" if job and job["enabled"] else "Enable")
        self.show_run()

    def show_run(self, *args):
        run = self.current_run()
        output = run["output"] if run else ""
        if run and run["agent"] == "codex" and not self.raw.isChecked():
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
        text = (f"{run['agent']} · {run['workdir']}\nPrompt: {run['prompt']}\n\n{output}" if run else "")
        if self.output.toPlainText() != text:
            self.output.setPlainText(text)
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
            if dialog.exec():
                job.update(dialog.values)
                self.scheduler.persist()
                self.refresh()

    def toggle(self):
        job = self.current_job()
        if job:
            job["enabled"] = not job["enabled"]
            if job["enabled"] and job["next_at"] is None:
                job["next_at"] = (datetime.now().astimezone() + timedelta(minutes=5)).isoformat()
            self.scheduler.persist()
            self.refresh()

    def run_now(self):
        if self.current_job():
            self.scheduler.start(self.current_job(), manual=True)

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
