from app.agents.base import Agent


class OpenCodeAgent(Agent):
    @property
    def capabilities(self):
        return (
            "OpenCode v2: new sessions receive an explicit native ID; "
            "activity and new replies are reported by the local API. "
            "Older versions: enter the native session ID in Details."
        )


def adapter():
    return OpenCodeAgent("opencode", "OpenCode", "opencode", resume_args=("--session", "{id}"))
