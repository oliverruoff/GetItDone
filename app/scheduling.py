"""Local, persisted agent jobs. A run is claimed on disk before starting a process."""

import calendar
import codecs
import json
import os
import signal
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import QObject, QProcess, QTimer, QTimeZone, Signal

from app.agents import agents
from app.models import now_iso, uid

OUTPUT_LIMIT = 1_000_000


def local_zone():
    try:
        return ZoneInfo(bytes(QTimeZone.systemTimeZoneId()).decode())
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().tzinfo


def next_occurrence(at, every, unit, now):
    if not every:
        return None
    # Calendar arithmetic uses the local zone, preserving wall time across DST.
    origin = at
    if unit == "months":
        steps = max(1, ((now.year - at.year) * 12 + now.month - at.month) // every)
        while True:
            month = origin.year * 12 + origin.month - 1 + every * steps
            year, month = divmod(month, 12)
            month += 1
            at = origin.replace(year=year, month=month,
                                day=min(origin.day, calendar.monthrange(year, month)[1]))
            if at > now:
                return at
            steps += 1
    period = timedelta(**{unit: every})
    return at + period * max(1, (now - at) // period + 1)


def run_command(agent, prompt, native_id):
    command = agent.command()
    if agent.id == "codex":
        return [*command, "exec", "--json", "--skip-git-repo-check", "--", prompt]
    if agent.id == "claude":
        return [*command, "--print", "--session-id", native_id, "--", prompt]
    if agent.id == "pi":
        return [*command, "--print", "--session-id", native_id, "--", prompt]
    if agent.id == "opencode":
        return [*command, "run", "--session", native_id, "--", prompt]
    # Custom profiles must provide a noninteractive CLI; the prompt is one argument.
    return [*command, prompt]


class Scheduler(QObject):
    changed = Signal()
    sessions_changed = Signal()

    def __init__(self, notebook, persist, parent=None):
        super().__init__(parent)
        self.notebook = notebook
        self.persist = persist
        self.jobs = notebook.data.setdefault("scheduled_jobs", [])
        self.active = {}
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self.save_output)
        interrupted = False
        for job in self.jobs:
            for run in job["runs"]:
                if run["status"] == "running":
                    run.update(status="interrupted", finished_at=now_iso())
                    run["output"] += "\nGetItDone closed before this run finished. Check the native session before rerunning."
                    interrupted = True
        if interrupted:
            self.persist()

    def save_output(self):
        self.persist()
        self.changed.emit()

    def tick(self, now=None):
        now = now or datetime.now(local_zone())
        for job in self.jobs:
            if (job["enabled"] and job["next_at"] and job["id"] not in self.active
                    and datetime.fromisoformat(job["next_at"]) <= now):
                self.start(job, now=now)

    def start(self, job, manual=False, now=None):
        if job["id"] in self.active:
            return False
        now = now or datetime.now(local_zone())
        run = dict(id=uid(), started_at=now_iso(), finished_at=None, status="running", output="",
                   session_id=None, prompt=job["prompt"], agent=job["agent"], workdir=job["workdir"])
        old_next, old_enabled = job["next_at"], job["enabled"]
        if not manual:
            following = next_occurrence(datetime.fromisoformat(job["next_at"]).astimezone(local_zone()),
                                        job["every"], job["unit"], now)
            job["next_at"] = following.isoformat() if following else None
            job["enabled"] = following is not None
        job["runs"].append(run)
        if not self.persist():
            job["runs"].remove(run)
            job["next_at"], job["enabled"] = old_next, old_enabled
            return False
        try:
            if not Path(job["workdir"]).is_dir():
                raise ValueError("Working folder is unavailable.")
            agent = agents(self.notebook.data["settings"]).get(job["agent"])
            if agent is None:
                raise ValueError("Agent profile no longer exists.")
            native = uid() if agent.id != "codex" and agent.resume_args else None
            if agent.id == "opencode":
                native = "ses_" + uid().replace("-", "")
            command = run_command(agent, job["prompt"], native)
            item = self.notebook.get(job.get("item_id"))
            if item is None:
                item = self.notebook.add("Scheduled · " + job["title"])
                job["item_id"] = item["id"]
            session = dict(id=uid(), item_id=item["id"], agent=agent.id, native_session_id=native,
                           workdir=job["workdir"], title=job["title"], created_at=run["started_at"])
            run["session_id"] = session["id"]
            self.notebook.data["sessions"].append(session)
            if not self.persist():
                raise ValueError("Session could not be saved; agent was not started.")
            process = QProcess(self)
            if os.name != "nt":
                parameters = QProcess.UnixProcessParameters()
                parameters.flags = QProcess.UnixProcessFlag.CreateNewSession
                process.setUnixProcessParameters(parameters)
            process.setWorkingDirectory(job["workdir"])
            process.setProcessChannelMode(QProcess.MergedChannels)
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            process.run_decoder = decoder
            process.run_session = session
            self.active[job["id"]] = (process, run)
            process.readyReadStandardOutput.connect(lambda: self.read_output(process, run, session, decoder))
            process.finished.connect(lambda code, status: self.finish(job, process, run, code))
            process.errorOccurred.connect(lambda err: self.failed(job, process, run, err))
            self.sessions_changed.emit()
            process.start(command[0], command[1:])
            process.closeWriteChannel()
        except (ValueError, OSError) as exc:
            run.update(status="failed", finished_at=now_iso(), output=str(exc))
            self.persist()
        self.changed.emit()
        return True

    def read_output(self, process, run, session, decoder):
        text = decoder.decode(bytes(process.readAllStandardOutput()))
        if session["agent"] == "codex" and not session["native_session_id"]:
            buffer = getattr(process, "event_buffer", "") + text
            lines = buffer.split("\n")
            process.event_buffer = lines.pop()
            for line in lines:
                try:
                    event = json.loads(line)
                    if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
                        session["native_session_id"] = event["thread_id"]
                except (ValueError, AttributeError):
                    pass
        raw = (run["output"] + text).encode("utf-8")
        run["output"] = raw[-OUTPUT_LIMIT:].decode("utf-8", errors="ignore")
        self.save_timer.start()

    def failed(self, job, process, run, err):
        if err == QProcess.FailedToStart:
            run["output"] += process.errorString()
            self.finish(job, process, run, -1)

    def finish(self, job, process, run, code):
        if job["id"] not in self.active:
            return
        self.read_output(process, run, process.run_session, process.run_decoder)
        run.update(status="completed" if code == 0 else "failed", finished_at=now_iso(), exit_code=code)
        self.active.pop(job["id"], None)
        self.persist()
        self.changed.emit()
        process.deleteLater()

    @staticmethod
    def kill_process(process):
        pid = process.processId()
        if pid:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, creationflags=0x08000000, timeout=5)
            else:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        process.kill()

    def stop(self, job):
        active = self.active.get(job["id"])
        if active:
            self.kill_process(active[0])

    def shutdown(self):
        for process, run in list(self.active.values()):
            self.kill_process(process)
            process.waitForFinished(3000)
        self.save_timer.stop()
        self.persist()
