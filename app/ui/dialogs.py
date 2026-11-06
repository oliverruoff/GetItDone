import copy
import json
from datetime import datetime, timezone

from PySide6.QtCore import QDateTime, QLocale, Qt, QTime
from PySide6.QtGui import QColor, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.agents import agents
from app.models import uid
from app.session_paths import prepare_session_folder, session_folder
from app.ui.backup_settings import BackupSettings
from app.ui.common import DismissibleDialog, Job, confirm, error


class SessionDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New agent session")
        self.resize(570, 260)
        self.registry = agents(settings)
        self.session_settings = settings
        self.supports_status = False
        self.native_session_id = None
        layout = QFormLayout(self)
        self.agent = QComboBox()
        for ident, agent in self.registry.items():
            self.agent.addItem(agent.name, ident)
        self.agent.setCurrentIndex(max(0, self.agent.findData(settings.get("default_agent"))))
        layout.addRow("Agent", self.agent)
        line = QHBoxLayout()
        self.workdir = QLineEdit(str(session_folder(settings)))
        choose = QPushButton("Choose …")
        choose.clicked.connect(self.choose)
        line.addWidget(self.workdir, 1)
        line.addWidget(choose)
        layout.addRow("Working directory", line)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.PlainText)
        layout.addRow(self.info)
        hint = QLabel("Only the item text is copied. Paste and submit it yourself in the terminal.")
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.start_button = buttons.button(QDialogButtonBox.Ok)
        self.start_button.setText("New session")
        buttons.accepted.connect(self.check)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.agent.currentIndexChanged.connect(self.probe)
        self.probe()

    def choose(self):
        path = QFileDialog.getExistingDirectory(self, "Working directory", self.workdir.text())
        if path:
            self.workdir.setText(path)

    def probe(self):
        self.start_button.setEnabled(False)
        self.supports_status = False
        ident = self.agent.currentData()
        agent = self.registry[ident]
        self.info.setText("Checking installation …")

        def finished(result, exc):
            if self.agent.currentData() == ident:
                self.start_button.setEnabled(True)
                self.supports_status = (
                    ident == "opencode"
                    and isinstance(result, str)
                    and result.lower().startswith(("opencode v2.", "2."))
                )
                self.info.setText(f"{result or exc}\n{agent.capabilities}")

        Job(agent.probe, finished, self)

    def check(self):
        try:
            self.native_session_id = "ses_" + uid().replace("-", "") if self.supports_status else None
            agent = self.registry[self.agent.currentData()]
            if agent.id in ("claude", "pi"):
                self.native_session_id = uid()
                self.command = agent.command() + ["--session-id", self.native_session_id]
            else:
                self.command = agent.command(self.native_session_id)
            self.directory = prepare_session_folder(self.session_settings, self.workdir.text())
            self.accept()
        except (ValueError, OSError) as exc:
            error(self, exc)


class ReminderDialog(DismissibleDialog):
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reminder · local time zone")
        self.setMinimumWidth(440)
        layout = QFormLayout(self)
        self.removed = False
        quick = QHBoxLayout()
        for title, minutes in [("In 15 min", 15), ("In 1 hour", 60), ("Tomorrow 09:00", None)]:
            button = QPushButton(title)
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, value=minutes: self.set_preset(value))
            quick.addWidget(button)
        layout.addRow("Quick pick", quick)
        self.when = QDateTimeEdit()
        self.when.setAccessibleName("Reminder date")
        self.when.setLocale(QLocale(QLocale.English, QLocale.UnitedKingdom))
        self.when.setDisplayFormat("ddd, dd MMM yyyy")
        self.when.setCalendarPopup(True)
        value = (
            QDateTime.fromString(item["reminder"]["at"], Qt.ISODate)
            if item["reminder"]
            else QDateTime.currentDateTime()
        )
        if not item["reminder"]:
            value.setTime(QTime(value.time().hour(), value.time().minute()))
        self.when.setDateTime(value.toLocalTime())
        layout.addRow("Date", self.when)
        time_row = QHBoxLayout()
        time_row.setSpacing(6)
        self.hour = self.time_picker("Hour", range(24), 23)
        self.minute = self.time_picker("Minute", range(0, 60, 5), 59)
        time_row.addWidget(self.hour)
        separator = QLabel(":")
        separator.setFixedWidth(8)
        separator.setAlignment(Qt.AlignCenter)
        time_row.addWidget(separator)
        time_row.addWidget(self.minute)
        time_row.addWidget(QLabel("24-hour clock"))
        time_row.addStretch()
        layout.addRow("Time", time_row)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setTextFormat(Qt.PlainText)
        layout.addRow(self.preview)
        hint = QLabel("One-time reminder. The app must be running to deliver notifications.")
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if item["reminder"]:
            remove = buttons.addButton("Remove reminder", QDialogButtonBox.DestructiveRole)
            remove.clicked.connect(self.remove_reminder)
        layout.addRow(buttons)
        self.when.dateTimeChanged.connect(self.sync_time)
        self.hour.currentTextChanged.connect(self.time_changed)
        self.minute.currentTextChanged.connect(self.time_changed)
        self.sync_time()

    def time_picker(self, name, values, maximum):
        picker = QComboBox()
        picker.setEditable(True)
        picker.setInsertPolicy(QComboBox.NoInsert)
        picker.addItems([f"{value:02d}" for value in values])
        picker.setAccessibleName("Reminder " + name.lower())
        picker.setToolTip(f"{name}: choose a value or type 00–{maximum:02d}")
        picker.lineEdit().setValidator(QIntValidator(0, maximum, picker))
        picker.lineEdit().setMaxLength(2)
        picker.setFixedWidth(88)
        picker.setMaxVisibleItems(12)
        return picker

    def sync_time(self, *args):
        time = self.when.time()
        for picker, value in [(self.hour, time.hour()), (self.minute, time.minute())]:
            blocked = picker.blockSignals(True)
            text = f"{value:02d}"
            picker.setCurrentIndex(picker.findText(text))
            picker.setEditText(text)
            picker.blockSignals(blocked)
        self.update_preview()

    def time_changed(self, *args):
        if not self.hour.lineEdit().hasAcceptableInput() or not self.minute.lineEdit().hasAcceptableInput():
            self.save_button.setEnabled(False)
            self.preview.setText("Choose an hour (00–23) and minute (00–59).")
            return
        time = QTime(int(self.hour.currentText()), int(self.minute.currentText()))
        blocked = self.when.blockSignals(True)
        self.when.setTime(time)
        self.when.blockSignals(blocked)
        self.update_preview()

    def update_preview(self):
        self.save_button.setEnabled(True)
        when = self.when.dateTime()
        today = QDateTime.currentDateTime().date()
        if when.date() == today:
            day = "Today"
        elif when.date() == today.addDays(1):
            day = "Tomorrow"
        else:
            day = self.when.locale().toString(when.date(), "ddd, dd MMM yyyy")
        self.preview.setText(f"{day} at {when.toString('HH:mm')} · local time")

    def set_preset(self, minutes):
        now = QDateTime.currentDateTime()
        if minutes is None:
            when = now.addDays(1)
            when.setTime(QTime(9, 0))
        else:
            when = now.addSecs(minutes * 60)
            when.setTime(QTime(when.time().hour(), when.time().minute()))
        self.when.setDateTime(when)
        # Also restore incomplete time input if the chosen timestamp is unchanged.
        self.sync_time()

    def remove_reminder(self):
        self.removed = True
        self.accept()

    def value(self):
        if self.removed:
            return None
        when = datetime.fromtimestamp(self.when.dateTime().toSecsSinceEpoch(), timezone.utc)
        return {"at": when.isoformat(), "notified_at": None}


class SettingsDialog(QDialog):
    def __init__(self, data, data_path, notification_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(700, 530)
        self.settings = copy.deepcopy(data["settings"])
        self.categories = copy.deepcopy(data["categories"])
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        general = QWidget()
        form = QFormLayout(general)
        self.workdir = QLineEdit(str(session_folder(self.settings)))
        folder = QPushButton("Choose folder …")
        folder.clicked.connect(self.choose)
        row = QHBoxLayout()
        row.addWidget(self.workdir)
        row.addWidget(folder)
        form.addRow("Default working directory", row)
        self.agent = QComboBox()
        for ident, agent in agents(self.settings).items():
            self.agent.addItem(agent.name, ident)
        self.agent.setCurrentIndex(max(0, self.agent.findData(self.settings.get("default_agent"))))
        form.addRow("Default agent", self.agent)
        from app import autostart

        self.autostart = QCheckBox("Start GetItDone when I sign in")
        try:
            self.autostart.setChecked(autostart.enabled())
        except OSError:
            self.autostart.setEnabled(False)
        self.initial_autostart = self.autostart.isChecked()
        form.addRow("Startup", self.autostart)
        path = QLineEdit(str(data_path))
        path.setReadOnly(True)
        form.addRow("Task data file", path)
        notice = QLabel(notification_text)
        notice.setWordWrap(True)
        form.addRow("Notifications", notice)
        info = QLabel(
            "Closing the window hides it in the system tray / menu bar.\nUse File → Quit to exit.\nSession output and document contents are not saved in JSON."
        )
        info.setWordWrap(True)
        form.addRow(info)
        tabs.addTab(general, "General")
        self.backups = BackupSettings(data["settings"], data_path.parent, getattr(parent, "backups", None))
        tabs.addTab(self.backups, "Backups")
        cats = QWidget()
        catlayout = QVBoxLayout(cats)
        self.catlist = QListWidget()
        catlayout.addWidget(self.catlist)
        actions = QHBoxLayout()
        for title, callback in [
            ("Add", self.add_cat),
            ("Edit", self.edit_cat),
            ("Delete", self.delete_cat),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        catlayout.addLayout(actions)
        tabs.addTab(cats, "Categories")
        profiles = QWidget()
        profilelayout = QVBoxLayout(profiles)
        info = QLabel(
            'Custom profiles as a JSON list. List arguments separately; no shell syntax.\nExample: [{"name":"My agent","executable":"/path/agent","args":[]}]\nDo not enter tokens or passwords. The CLI handles authentication.'
        )
        info.setWordWrap(True)
        profilelayout.addWidget(info)
        self.profiles = QPlainTextEdit(
            json.dumps(self.settings.get("profiles", []), ensure_ascii=False, indent=2)
        )
        profilelayout.addWidget(self.profiles)
        tabs.addTab(profiles, "Agent profiles")
        layout.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.check)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_cats()

    def choose(self):
        folder = QFileDialog.getExistingDirectory(self, "Default working directory", self.workdir.text())
        if folder:
            self.workdir.setText(folder)

    def refresh_cats(self):
        self.catlist.clear()
        for cat in self.categories:
            self.catlist.addItem(f"● {cat['name']} · {cat['color']}")
            self.catlist.item(self.catlist.count() - 1).setForeground(QColor(cat["color"]))

    def category_values(self, category=None):
        name, ok = QInputDialog.getText(self, "Category", "Name", text=category["name"] if category else "")
        if not ok or not name.strip():
            return None
        color = QColorDialog.getColor(
            QColor(category["color"] if category else "#3974ad"), self, "Category color"
        )
        if not color.isValid():
            return None
        return {"id": category["id"] if category else uid(), "name": name.strip(), "color": color.name()}

    def add_cat(self):
        cat = self.category_values()
        if cat:
            self.categories.append(cat)
            self.refresh_cats()

    def edit_cat(self):
        index = self.catlist.currentRow()
        if index >= 0:
            cat = self.category_values(self.categories[index])
            if cat:
                self.categories[index] = cat
                self.refresh_cats()

    def delete_cat(self):
        index = self.catlist.currentRow()
        if index >= 0 and confirm(
            self,
            "Delete category",
            "Remove this category? Tasks are preserved and only their category is cleared.",
        ):
            self.categories.pop(index)
            self.refresh_cats()

    def check(self):
        try:
            profiles = json.loads(self.profiles.toPlainText())
            if not isinstance(profiles, list):
                raise ValueError("Profiles must be a JSON list.")
            seen = {"opencode", "codex", "claude", "pi"}
            for profile in profiles:
                if (
                    not isinstance(profile, dict)
                    or not isinstance(profile.get("name"), str)
                    or not profile["name"].strip()
                    or not isinstance(profile.get("executable"), str)
                    or not profile["executable"].strip()
                    or not isinstance(profile.get("args"), list)
                    or not all(isinstance(a, str) for a in profile["args"])
                ):
                    raise ValueError("Each profile requires name, executable and args (a list of strings).")
                profile.setdefault("id", "custom-" + uid())
                if not isinstance(profile["id"], str) or profile["id"] in seen:
                    raise ValueError("Profile IDs must be unique and cannot replace built-in agents.")
                seen.add(profile["id"])
            backup_settings = self.backups.value()
            directory = prepare_session_folder(self.settings, self.workdir.text())
            if self.autostart.isChecked() != self.initial_autostart:
                from app import autostart

                autostart.set_enabled(self.autostart.isChecked())
            self.settings.update(
                default_workdir=directory, default_agent=self.agent.currentData(), profiles=profiles,
                backups=backup_settings,
            )
            self.accept()
        except (ValueError, TypeError, OSError) as exc:
            error(self, exc)
