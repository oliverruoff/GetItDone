from app.agents.base import Agent


def adapter():
    return Agent("claude", "Claude Code", "claude", resume_args=("--resume", "{id}"))
