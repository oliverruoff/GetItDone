import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

from PySide6.QtCore import Qt

from app.executions import execution_records, recover_process_runs
from app.models import Notebook, now_iso, uid
from app.storage import Store
from app.ui.executions import Executions
from app.ui.window import Window


def session(book, tmp_path, **extra):
    item = book.add("Manual agent task")
    result = dict(id=uid(), item_id=item["id"], agent="test", native_session_id=None,
                  title=item["text"], workdir=str(tmp_path), created_at=now_iso(), **extra)
    return result


def test_legacy_and_resumed_scheduled_sessions_are_not_double_counted(qtbot, tmp_path):
    book = Notebook()
    saved = session(book, tmp_path)
    saved["created_at"] = "old metadata"
    scheduled = session(book, tmp_path)
    resumed = dict(id=uid(), started_at=now_iso(), finished_at=None, status="running", resumed=True)
    scheduled["process_runs"] = [resumed]
    book.data["sessions"] = [saved, scheduled]
    run = dict(id=uid(), session_id=scheduled["id"], started_at=now_iso(), finished_at=now_iso(),
               status="completed", agent="test", output="Scheduled result", workdir=str(tmp_path), prompt="Original")
    book.data["scheduled_jobs"] = [dict(id=uid(), title="Schedule", runs=[run])]
    terminals = {scheduled["id"]: SimpleNamespace(running=True, agent_state="Ready")}
    records = execution_records(book, terminals)
    assert len(records) == 3  # One scheduled run, one resumed process, one old session.
    assert sum(r["active"] for r in records) == 1
    assert records[0]["origin"] == "Resumed"
    panel = Executions()
    qtbot.addWidget(panel)
    panel.refresh(records)
    assert "1 running" in panel.summary.text()
    panel.filter.setCurrentIndex(1)
    assert panel.table.topLevelItemCount() == 1
    panel.filter.setCurrentIndex(2)
    assert panel.table.topLevelItemCount() == 2
    assert recover_process_runs(book)
    assert resumed["status"] == "interrupted"
    assert not recover_process_runs(book)


def test_real_manual_and_scheduled_processes_indicator_history_and_reopen(qtbot, tmp_path):
    store = Store(tmp_path)
    window = Window(store, store.load())
    qtbot.addWidget(window)
    window.timer.stop()
    window.notebook.data["settings"]["profiles"] = [dict(
        id="test", name="Test", executable=sys.executable,
        args=["-c", "import time; print('SCHEDULED_RESULT', flush=True); time.sleep(1.5)"])]
    manual = session(window.notebook, tmp_path)
    assert window.launch(manual, [sys.executable, "-c", "import time; time.sleep(1.5)"])
    window.notebook.data["sessions"].append(manual)
    window.tasks.rebuild()
    window.refresh_executions()
    assert "1 running" in window.execution_indicator.text()
    window.apply_agent_snapshot(manual["id"], dict(busy=False, failed=False, message="reply", output="MANUAL_REPLY"))
    job = dict(id=uid(), title="Scheduled test", prompt="Test", agent="test", workdir=str(tmp_path),
               next_at=(datetime.now().astimezone()-timedelta(seconds=1)).isoformat(), every=0,
               unit="days", enabled=True, runs=[])
    window.scheduler.jobs.append(job)
    window.scheduler.tick()
    assert window.execution_indicator.text() == "2 running · 1 scheduled"
    window.tasks.rebuild()
    scheduled_session = job["runs"][0]["session_id"]
    assert "Scheduled run running" in window.tasks.session_rows[scheduled_session].text(0)
    # The same link in Tasks must show the active run, never launch a second CLI.
    window.resume_session(scheduled_session)
    assert window.workspace.currentWidget() is window.scheduled
    assert len(window.terminals) == 1
    qtbot.mouseClick(window.execution_indicator, Qt.LeftButton)
    assert window.workspace.currentWidget() is window.executions
    window.executions.filter.setCurrentIndex(1)
    assert window.executions.table.topLevelItemCount() == 2
    # Follow the selected scheduled run into its exact saved inbox entry.
    scheduled_row = next(window.executions.table.topLevelItem(i) for i in range(2)
                         if window.executions.table.topLevelItem(i).text(2) == "Scheduled")
    window.executions.table.setCurrentItem(scheduled_row)
    qtbot.mouseClick(window.executions.schedule_button, Qt.LeftButton)
    assert window.workspace.currentWidget() is window.scheduled
    assert window.scheduled.current_run()["id"] == job["runs"][0]["id"]
    qtbot.waitUntil(lambda: manual["process_runs"][0]["status"] != "running" and not window.scheduler.active,
                    timeout=8000)
    assert window.execution_indicator.text() == "No agents running"
    assert window.executions.table.topLevelItemCount() == 0
    window.executions.filter.setCurrentIndex(2)
    assert window.executions.table.topLevelItemCount() == 2
    window.executions.table.setCurrentItem(next(window.executions.table.topLevelItem(i) for i in range(2)
                                               if window.executions.table.topLevelItem(i).text(2) == "Todo"))
    assert window.executions.output.toPlainText() == "MANUAL_REPLY"
    assert window.flush()
    disk = Store(tmp_path).load()
    assert disk["sessions"][0]["process_runs"][0]["last_reply"]["text"] == "MANUAL_REPLY"
    assert disk["scheduled_jobs"][0]["runs"][0]["output"].strip() == "SCHEDULED_RESULT"
    assert len(execution_records(Notebook(disk), {})) == 2
    assert not any(r["active"] for r in execution_records(Notebook(disk), {}))
    terminal = window.terminals[manual["id"]]
    qtbot.waitUntil(lambda: not terminal.reader.is_alive())
    window.quitting = True
    window.tray.hide()
    window.close()


def test_execution_selection_survives_output_update(qtbot, tmp_path):
    book = Notebook()
    first = session(book, tmp_path)
    second = session(book, tmp_path)
    book.data["sessions"] = [first, second]
    panel = Executions()
    qtbot.addWidget(panel)
    panel.refresh(execution_records(book, {}))
    selected = panel.table.topLevelItem(1)
    panel.table.setCurrentItem(selected)
    ident = panel.current_record()["session_id"]
    target = next(s for s in book.data["sessions"] if s["id"] == ident)
    target["last_reply"] = dict(text="New saved output")
    panel.refresh(execution_records(book, {}))
    assert panel.current_record()["session_id"] == ident
    assert panel.output.toPlainText() == "New saved output"
