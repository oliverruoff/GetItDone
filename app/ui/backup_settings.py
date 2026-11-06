from datetime import datetime

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QWidget,
)

from app.backups import backup_defaults, check_destination, configure_backup
from app.ui.common import error


class BackupSettings(QWidget):
    def __init__(self, settings, data_folder, scheduler=None):
        super().__init__()
        self.source = settings
        self.data_folder = data_folder
        self.scheduler = scheduler
        config = backup_defaults() | settings.get("backups", {})
        form = QFormLayout(self)
        self.enabled = QCheckBox("Enable automatic full backups")
        self.enabled.setChecked(config["enabled"])
        form.addRow(self.enabled)
        self.time = QTimeEdit(QTime.fromString(config["time"], "HH:mm"))
        self.time.setDisplayFormat("HH:mm")
        self.time.setAccessibleName("Backup time")
        form.addRow("Time · local time zone", self.time)
        interval = QHBoxLayout()
        self.every = QSpinBox()
        self.every.setRange(1, 999)
        self.every.setValue(config["every"])
        self.every.setAccessibleName("Backup interval")
        self.unit = QComboBox()
        for text, unit in [("day(s)", "days"), ("week(s)", "weeks"), ("month(s)", "months")]:
            self.unit.addItem(text, unit)
        self.unit.setCurrentIndex(self.unit.findData(config["unit"]))
        interval.addWidget(QLabel("Every"))
        interval.addWidget(self.every)
        interval.addWidget(self.unit)
        form.addRow("Interval", interval)
        destination = QHBoxLayout()
        self.folder = QLineEdit(config["folder"] or backup_defaults()["folder"])
        self.folder.setAccessibleName("Backup folder")
        self.choose = QPushButton("Choose folder …")
        self.choose.clicked.connect(self.choose_folder)
        destination.addWidget(self.folder, 1)
        destination.addWidget(self.choose)
        form.addRow("Destination folder", destination)
        self.backup_now_button = QPushButton("Backup now")
        self.backup_now_button.setAutoDefault(False)
        self.backup_now_button.clicked.connect(self.backup_now)
        self.backup_now_button.setToolTip("Back up now to the selected folder without changing the automatic schedule")
        form.addRow(self.backup_now_button)
        hint = QLabel(
            "Each backup is a new ZIP containing all tasks, subtasks, notes, reminders, categories, "
            "settings, session links, saved replies, scheduled jobs and the entire Knowledge folder.\n\n"
            "GetItDone must be running (the window can be hidden). Missed backups are caught up once "
            "on the next start or after sleep. The first backup is at the next selected time; "
            "the interval starts there. Scheduled backup errors are retried after 5 minutes.\n"
            "Backup now also works with automatic backups disabled. Missing destination folders are created.\n\n"
            "Older backups are kept; make sure there is enough free space. ZIP files are not encrypted. "
            "External agent projects and native chat histories are not included."
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("Saved schedule / status", self.status)
        self.enabled.toggled.connect(self.toggle)
        self.toggle(config["enabled"])
        if scheduler:
            scheduler.changed.connect(self.refresh_status)
        self.refresh_status()

    def toggle(self, enabled):
        for widget in (self.time, self.every, self.unit):
            widget.setEnabled(enabled)

    def backup_now(self):
        if self.scheduler:
            try:
                self.scheduler.backup_now(self.folder.text().strip())
            except (ValueError, OSError) as exc:
                error(self, exc)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Backup destination", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def value(self):
        folder = self.folder.text().strip()
        if self.enabled.isChecked():
            folder = str(check_destination(folder, self.data_folder, self.source.get("knowledge_folder", "")))
        return configure_backup(
            self.source.get("backups", {}), enabled=self.enabled.isChecked(),
            time=self.time.time().toString("HH:mm"), every=self.every.value(),
            unit=self.unit.currentData(), folder=folder,
        )

    def refresh_status(self):
        config = backup_defaults() | self.source.get("backups", {})
        self.backup_now_button.setEnabled(self.scheduler is not None and not self.scheduler.active)

        def date(value):
            return datetime.fromisoformat(value).astimezone().strftime("%d %b %Y, %H:%M") if value else "—"

        state = "In progress" if self.scheduler and self.scheduler.active else (
            "Enabled" if config["enabled"] else "Disabled")
        self.status.setText(
            f"{state}\nNext: {date(config['next_at'])}\nLast successful: {date(config['last_at'])}"
            + (f"\nFile: {config['last_file']}" if config["last_file"] else "")
            + (f"\nError: {config['last_error']}" if config["last_error"] else "")
        )
