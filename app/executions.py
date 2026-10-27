"""One notebook-wide view of scheduled runs and interactive process launches."""

from datetime import datetime

from app.models import now_iso


def recover_process_runs(notebook):
    changed = False
    for session in notebook.data["sessions"]:
        for run in session.get("process_runs", []):
            if run["status"] == "running":
                run.update(status="interrupted", finished_at=now_iso())
                changed = True
    return changed


def execution_records(notebook, terminals):
    records = []
    sessions = {s["id"]: s for s in notebook.data["sessions"]}
    scheduled_sessions = set()
    for job in notebook.data.get("scheduled_jobs", []):
        for index, run in enumerate(job["runs"], 1):
            ident = run.get("session_id")
            scheduled_sessions.add(ident)
            records.append(dict(
                id=run["id"], title=f"{job['title']} · Run #{index}", agent=run["agent"],
                origin="Scheduled", status=run["status"].capitalize(), active=run["status"] == "running",
                started_at=run["started_at"], finished_at=run.get("finished_at"),
                session_id=ident if ident in sessions else None, job_id=job["id"], run_id=run["id"],
                output=run["output"], output_agent=run["agent"], workdir=run["workdir"], prompt=run["prompt"]))
    for session in sessions.values():
        runs = session.get("process_runs", [])
        terminal = terminals.get(session["id"])
        for index, run in enumerate(runs, 1):
            active = bool(terminal and terminal.running and run["status"] == "running")
            state = getattr(terminal, "agent_state", None) if active else None
            state = state or ("Terminal open" if active else {
                "completed": "Terminal closed", "failed": "Failed", "stopped": "Stopped",
                "interrupted": "Interrupted", "running": "Status unavailable"}.get(run["status"], "Saved"))
            reply = run.get("last_reply") or {}
            records.append(dict(
                id=run["id"], title=f"{session['title']} · Session #{index}", agent=session["agent"],
                origin="Resumed" if run.get("resumed") else "Todo", status=state, active=active,
                started_at=run["started_at"], finished_at=run.get("finished_at"), session_id=session["id"],
                job_id=None, run_id=None, output=reply.get("text", ""), output_agent=None,
                workdir=session["workdir"], prompt=""))
        # Preserve existing session links without inventing a historic process outcome.
        if not runs and session["id"] not in scheduled_sessions:
            records.append(dict(
                id="saved:" + session["id"], title=session["title"], agent=session["agent"], origin="Saved session",
                status="Terminal open" if terminal and terminal.running else "Saved session",
                active=bool(terminal and terminal.running), started_at=session["created_at"], finished_at=None,
                session_id=session["id"], job_id=None, run_id=None,
                output=(session.get("last_reply") or {}).get("text", ""), output_agent=None,
                workdir=session["workdir"], prompt=""))
    def order(record):
        try:
            started = datetime.fromisoformat(record["started_at"]).timestamp()
        except (ValueError, TypeError, OverflowError, OSError):
            started = 0
        return record["active"], started

    records.sort(key=order, reverse=True)
    return records
