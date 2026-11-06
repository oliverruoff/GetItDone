from copy import deepcopy
from datetime import datetime

import pytest
from PySide6.QtCore import QDateTime, Qt, QTime
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton

from app.main import configure_style
from app.models import Notebook
from app.ui.dialogs import ReminderDialog


@pytest.fixture
def reminder(qtbot):
    configure_style(QApplication.instance())
    item = Notebook().add("Task")
    dialog = ReminderDialog(item)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_separate_date_and_time_controls_show_local_schedule(reminder):
    assert "HH" not in reminder.when.displayFormat()
    assert reminder.when.calendarPopup()
    assert reminder.hour.isEditable() and reminder.minute.isEditable()
    assert reminder.hour.count() == 24
    assert reminder.minute.count() == 12
    assert reminder.hour.currentText() == reminder.when.time().toString("HH")
    assert reminder.minute.currentText() == reminder.when.time().toString("mm")
    assert reminder.when.time().second() == 0
    assert reminder.when.dateTime().toString("HH:mm") in reminder.preview.text()
    assert reminder.save_button.isEnabled()


def test_new_reminder_defaults_to_current_local_time(qtbot):
    before = QDateTime.currentDateTime()
    dialog = ReminderDialog(Notebook().add("Task"))
    qtbot.addWidget(dialog)
    after = QDateTime.currentDateTime()
    for value in (before, after):
        value.setTime(QTime(value.time().hour(), value.time().minute()))
    assert before.toSecsSinceEpoch() <= dialog.when.dateTime().toSecsSinceEpoch() <= after.toSecsSinceEpoch()
    assert dialog.when.time().second() == 0


@pytest.mark.parametrize("minutes", [15, 60, None])
def test_quick_picks_choose_correct_day_and_time(reminder, qtbot, minutes):
    title = "Tomorrow 09:00" if minutes is None else "In 15 min" if minutes == 15 else "In 1 hour"
    button = next(button for button in reminder.findChildren(QPushButton) if button.text() == title)
    before = QDateTime.currentDateTime()
    qtbot.mouseClick(button, Qt.LeftButton)
    when = reminder.when.dateTime()
    if minutes is None:
        assert when.date() == before.date().addDays(1)
        assert when.time() == QTime(9, 0)
        assert reminder.preview.text().startswith("Tomorrow at 09:00")
    else:
        elapsed = before.secsTo(when)
        assert minutes * 60 - 60 <= elapsed <= minutes * 60 + 1
    assert reminder.hour.currentText() == when.toString("HH")
    assert reminder.minute.currentText() == when.toString("mm")
    assert when.time().second() == 0


def test_dropdown_and_exact_minute_typing_update_schedule(reminder, qtbot):
    reminder.hour.setCurrentIndex(reminder.hour.findText("14"))
    reminder.minute.setCurrentIndex(reminder.minute.findText("30"))
    assert reminder.when.time() == QTime(14, 30)
    editor = reminder.minute.lineEdit()
    editor.selectAll()
    qtbot.keyClicks(editor, "17")
    assert reminder.when.time() == QTime(14, 17)
    assert "14:17" in reminder.preview.text()
    assert reminder.save_button.isEnabled()
    reminder.when.setDate(reminder.when.date().addDays(2))
    assert reminder.when.time() == QTime(14, 17)
    assert reminder.minute.currentText() == "17"
    assert datetime.fromisoformat(reminder.value()["at"]).timestamp() == reminder.when.dateTime().toSecsSinceEpoch()


def test_time_dropdown_does_not_dismiss_reminder(reminder, qtbot):
    picker = reminder.hour
    picker.showPopup()
    qtbot.waitUntil(lambda: picker.view().isVisible())
    index = picker.model().index(picker.findText("10"), 0)
    picker.view().scrollTo(index)
    qtbot.mouseClick(picker.view().viewport(), Qt.LeftButton, pos=picker.view().visualRect(index).center())
    assert reminder.isVisible()
    assert reminder.when.time().hour() == 10


@pytest.mark.parametrize("field,text", [("hour", ""), ("minute", ""), ("hour", "24"), ("minute", "60")])
def test_incomplete_or_invalid_time_disables_save_and_preset_restores_it(reminder, field, text):
    getattr(reminder, field).setEditText(text)
    assert not reminder.save_button.isEnabled()
    assert "Choose an hour" in reminder.preview.text()
    reminder.set_preset(60)
    assert reminder.save_button.isEnabled()
    assert "local time" in reminder.preview.text()


@pytest.mark.parametrize("stamp", ["2027-03-14T01:17:23+00:00", "2027-07-19T22:43:00+05:30"])
def test_existing_reminder_preserves_exact_timestamp_and_arbitrary_minutes(qtbot, stamp):
    item = Notebook().add("Task")
    item["reminder"] = {"at": stamp, "notified_at": None}
    original = deepcopy(item)
    dialog = ReminderDialog(item)
    qtbot.addWidget(dialog)
    local = QDateTime.fromString(stamp, Qt.ISODate).toLocalTime()
    assert dialog.hour.currentText() == local.toString("HH")
    assert dialog.minute.currentText() == local.toString("mm")
    assert datetime.fromisoformat(dialog.value()["at"]).timestamp() == datetime.fromisoformat(stamp).timestamp()
    dialog.reject()
    assert item == original


def test_remove_reminder_and_cancel_remain_available(qtbot):
    item = Notebook().add("Task")
    item["reminder"] = {"at": "2027-04-01T12:00:00+00:00", "notified_at": None}
    dialog = ReminderDialog(item)
    qtbot.addWidget(dialog)
    dialog.show()
    button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Remove reminder")
    qtbot.mouseClick(button, Qt.LeftButton)
    assert dialog.value() is None
    assert item["reminder"] is not None
    assert dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel) is not None
