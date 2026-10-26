from app.agents.base import Agent


def adapter():
    return Agent("pi", "pi", "pi", resume_args=("--session", "{id}"))
