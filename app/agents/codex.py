from app.agents.base import Agent


def adapter():
    return Agent("codex", "Codex", "codex", resume_args=("resume", "{id}"))
