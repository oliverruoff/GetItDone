import sys
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.agents.base import Agent
from app.models import Notebook, now_iso, uid
from app.scheduling import Scheduler, next_occurrence, run_command
from app.storage import StorageError, Store, validate


def make_job(tmp_path, **values):
    return dict(id=uid(), title="Daily check", prompt="Report a result", agent="test",
                workdir=str(tmp_path), enabled=True,
                next_at=(datetime.now().astimezone() - timedelta(minutes=1)).isoformat(),
                every=0, unit="days", runs=[], **values)


def test_real_process_output_inbox_and_persistence(qtbot, tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    book.data["settings"]["profiles"] = [dict(id="test", name="Test", executable=sys.executable,
        args=["-c", "import sys; print('Result ä: ' + sys.argv[1])"])]
    scheduler = Scheduler(book, lambda: (store.save(book.data), True)[1])
    job = make_job(tmp_path)
    scheduler.jobs.append(job)
    scheduler.tick()
    scheduler.tick()  # Claimed jobs cannot launch a second time.
    assert len(job["runs"]) == 1
    qtbot.waitUntil(lambda: not scheduler.active, timeout=5000)
    run = job["runs"][0]
    assert run["status"] == "completed"
    assert "Result ä: Report a result" in unicodedata.normalize("NFC", run["output"])
    assert not job["enabled"] and job["next_at"] is None
    disk = Store(tmp_path).load()
    assert disk["scheduled_jobs"][0]["runs"][0]["output"] == run["output"]
    assert disk["sessions"][0]["id"] == run["session_id"]
    assert disk["sessions"][0]["item_id"] == disk["items"][0]["id"]
    scheduler.shutdown()


def test_recurring_and_manual_run_preserve_schedule(qtbot, tmp_path):
    book = Notebook()
    book.data["settings"]["profiles"] = [dict(id="test", name="Test", executable=sys.executable,
                                              args=["-c", "print('done')"])]
    scheduler = Scheduler(book, lambda: True)
    job = make_job(tmp_path)
    job.update(every=2, unit="hours")
    scheduler.jobs.append(job)
    scheduler.tick()
    next_at = job["next_at"]
    assert datetime.fromisoformat(next_at) > datetime.now().astimezone()
    assert job["enabled"]
    qtbot.waitUntil(lambda: not scheduler.active)
    scheduler.start(job, manual=True)
    qtbot.waitUntil(lambda: not scheduler.active)
    assert job["next_at"] == next_at and len(job["runs"]) == 2
    assert len(book.items) == 1  # Each job reuses its own task/session group.
    scheduler.shutdown()


def test_failed_claim_never_launches(tmp_path):
    book = Notebook()
    scheduler = Scheduler(book, lambda: False)
    job = make_job(tmp_path)
    scheduler.jobs.append(job)
    old = job.copy()
    assert not scheduler.start(job)
    assert job == old and not scheduler.active and not book.items


def test_missing_executable_is_saved_failure(tmp_path):
    book = Notebook()
    book.data["settings"]["profiles"] = [dict(id="test", name="Missing", executable="/missing/agent", args=[])]
    scheduler = Scheduler(book, lambda: True)
    job = make_job(tmp_path)
    scheduler.start(job)
    assert job["runs"][0]["status"] == "failed"
    assert "not found" in job["runs"][0]["output"]
    assert not scheduler.active


def test_stop_running_process(qtbot, tmp_path):
    book = Notebook()
    book.data["settings"]["profiles"] = [dict(id="test", name="Test", executable=sys.executable,
        args=["-c", "import time; print('started', flush=True); time.sleep(30)"])]
    scheduler = Scheduler(book, lambda: True)
    job = make_job(tmp_path)
    scheduler.start(job)
    qtbot.waitUntil(lambda: "started" in job["runs"][0]["output"])
    scheduler.stop(job)
    qtbot.waitUntil(lambda: not scheduler.active)
    assert job["runs"][0]["status"] == "failed"
    scheduler.shutdown()


def test_restart_marks_interrupted_without_duplicate(tmp_path):
    book = Notebook()
    job = make_job(tmp_path)
    job.update(enabled=False, next_at=None)
    job["runs"].append(dict(id=uid(), started_at=now_iso(), finished_at=None,
        status="running", output="Partial", prompt="p", agent="test", workdir=str(tmp_path), session_id=None))
    book.data["scheduled_jobs"] = [job]
    writes = []
    scheduler = Scheduler(book, lambda: writes.append(True))
    scheduler.tick()
    assert job["runs"][0]["status"] == "interrupted"
    assert job["runs"][0]["output"].startswith("Partial")
    assert len(job["runs"]) == 1 and writes


def test_recurrence_local_time_and_month_end():
    tz = ZoneInfo("Europe/Berlin")
    before = datetime(2026, 10, 24, 10, tzinfo=tz)
    after = next_occurrence(before, 1, "days", datetime(2026, 10, 25, 9, tzinfo=tz))
    assert after.hour == 10 and after.day == 25 and after.utcoffset() == timedelta(hours=1)
    assert next_occurrence(datetime(2026, 1, 31, tzinfo=tz), 1, "months",
                           datetime(2026, 2, 1, tzinfo=tz)).day == 28
    assert next_occurrence(before, 0, "days", before) is None


@pytest.mark.parametrize("agent,expected", [
    ("codex", ["exec", "--json", "--skip-git-repo-check", "--", "-prompt"]),
    ("claude", ["--print", "--session-id", "native", "--", "-prompt"]),
    ("pi", ["--print", "--session-id", "native", "--", "-prompt"]),
    ("opencode", ["run", "--session", "native", "--", "-prompt"]),
])
def test_command_prompt_is_single_argument(agent, expected):
    adapter = Agent(agent, agent, sys.executable)
    assert run_command(adapter, "-prompt", "native")[1:] == expected


def test_storage_rejects_malformed_schedule_and_view(tmp_path):
    book = Notebook()
    book.data["scheduled_jobs"] = [make_job(tmp_path)]
    validate(book.data)
    book.data["scheduled_jobs"][0]["every"] = -1
    with pytest.raises(StorageError):
        validate(book.data)
    book.data["scheduled_jobs"] = []
    book.data["settings"]["task_view"] = {"expanded": {"id": "yes"}}
    with pytest.raises(StorageError):
        validate(book.data)


def test_inbox_hides_terminal_codes_but_preserves_raw_output(qtbot, tmp_path):
    from app.ui.scheduled import Scheduled

    book = Notebook()
    scheduler = Scheduler(book, lambda: True)
    job = make_job(tmp_path)
    raw = "\x1b[0m> build\x1b[0m\n\x1b]0;Terminal title\x07Result: 5017\n"
    run = dict(id=uid(), started_at=now_iso(), status="completed", agent="opencode",
               workdir=str(tmp_path), prompt="Calculate", output=raw, session_id=None)
    job["runs"].append(run)
    scheduler.jobs.append(job)
    panel = Scheduled(scheduler)
    qtbot.addWidget(panel)
    assert "Result: 5017" in panel.output.toPlainText()
    assert "\x1b" not in panel.output.toPlainText()
    assert "Terminal title" not in panel.output.toPlainText()
    panel.raw.setChecked(True)
    assert raw in panel.output.toPlainText()
    assert run["output"] == raw


def test_run_history_selection_isolated_and_preserved_on_refresh(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    from app.ui.scheduled import Scheduled

    book = Notebook()
    scheduler = Scheduler(book, lambda: True)
    for title in ("First schedule", "Second schedule"):
        job = make_job(tmp_path)
        job["title"] = title
        for number in range(3):
            at = datetime.now().astimezone() - timedelta(hours=3-number)
            job["runs"].append(dict(
                id=uid(), started_at=at.isoformat(), finished_at=(at + timedelta(seconds=5)).isoformat(),
                status="failed" if number == 2 else "completed", output=f"{title} output {number}",
                prompt=f"Original prompt {number}", agent="opencode", workdir=str(tmp_path), session_id=None))
        scheduler.jobs.append(job)
    panel = Scheduled(scheduler)
    qtbot.addWidget(panel)
    panel.resize(1100, 760)
    panel.show()
    assert panel.runs.topLevelItemCount() == 3
    assert panel.summary.text() == "3 total · 2 completed · 1 failed"
    assert panel.runs.topLevelItem(0).text(0) == "#3"
    assert panel.runs.topLevelItem(0).text(3) == "5s"
    assert panel.output.toPlainText() == "First schedule output 2"
    older = panel.runs.topLevelItem(2)
    qtbot.mouseClick(panel.runs.viewport(), Qt.LeftButton,
                     pos=panel.runs.visualItemRect(older).center())
    assert panel.output.toPlainText() == "First schedule output 0"
    assert "Original prompt 0" in panel.run_context.toPlainText()
    # Editing the current schedule must not rewrite a historical run's prompt.
    scheduler.jobs[0]["prompt"] = "Edited prompt"
    scheduler.changed.emit()
    assert panel.output.toPlainText() == "First schedule output 0"
    assert "Original prompt 0" in panel.run_context.toPlainText()
    assert panel.output_title.text() == "Output · Run #1"
    panel.jobs.setCurrentRow(1)
    assert panel.output.toPlainText() == "Second schedule output 2"
    panel.jobs.setCurrentRow(0)
    assert panel.output.toPlainText() == "First schedule output 0"


def test_empty_history_and_finished_schedule_can_be_scheduled_again(qtbot, tmp_path):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app.ui.scheduled import Scheduled, ScheduleDialog

    book = Notebook()
    scheduler = Scheduler(book, lambda: True)
    job = make_job(tmp_path)
    job.update(enabled=False, next_at=None)
    scheduler.jobs.append(job)
    panel = Scheduled(scheduler)
    qtbot.addWidget(panel)
    assert panel.summary.text() == "0 total"
    assert panel.output.toPlainText() == ""
    assert "No runs yet" in panel.output.placeholderText()
    assert not panel.copy_button.isEnabled()
    assert not panel.open_button.isEnabled()
    assert panel.pause.text() == "Schedule again"

    def save_again():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ScheduleDialog)
        assert dialog.enabled.isChecked()
        dialog.save()

    QTimer.singleShot(0, save_again)
    panel.toggle()
    assert job["enabled"] and job["next_at"]
    assert not job["runs"]  # Saving the new date must not trigger Run now.
