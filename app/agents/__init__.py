from app.agents import claude_code, codex, opencode, pi
from app.agents.base import Agent


def agents(settings):
    result = {a.id: a for a in (m.adapter() for m in (opencode, codex, claude_code, pi))}
    for profile in settings.get("profiles", []):
        a = Agent(profile["id"], profile["name"], profile["executable"], tuple(profile["args"]))
        result[a.id] = a
    return result
