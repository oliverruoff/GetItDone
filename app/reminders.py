from datetime import datetime, timedelta, timezone


class Reminders:
    def __init__(self, notebook, started=None):
        self.notebook = notebook
        self.started = started or datetime.now(timezone.utc)
        self.missed = set()
        self.retry_after = {}
        for item in notebook.items:
            r = item.get("reminder")
            if r and datetime.fromisoformat(r["at"]) <= self.started:
                self.missed.add((item["id"], r["at"]))

    def changed(self, ident):
        self.missed = {key for key in self.missed if key[0] != ident}
        self.retry_after.pop(ident, None)

    def failed(self, ident, at, now=None):
        item = self.notebook.get(ident)
        reminder = item.get("reminder") if item else None
        if reminder and reminder["at"] == at:
            reminder["notified_at"] = None
            self.retry_after[ident] = (now or datetime.now(timezone.utc)) + timedelta(minutes=1)
            return True
        return False

    def due(self, now=None):
        now = now or datetime.now(timezone.utc)
        result = []
        for item in self.notebook.items:
            r = item.get("reminder")
            if (
                r
                and not item["done"]
                and not r.get("notified_at")
                and (item["id"], r["at"]) not in self.missed
                and now >= self.retry_after.get(item["id"], self.started)
                and datetime.fromisoformat(r["at"]) <= now
            ):
                r["notified_at"] = now.isoformat()
                result.append(item)
        return result
