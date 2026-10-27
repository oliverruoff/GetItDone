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
