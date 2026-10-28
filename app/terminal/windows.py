"""Windows 10 1809+: pywinpty's ConPTY backend."""

import os
import subprocess


class Process:
    def __init__(self, command, cwd, cols=100, rows=28):
        from winpty import PtyProcess
        from winpty.enums import Backend

        env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
        self.process = PtyProcess.spawn(command, cwd=cwd, env=env, dimensions=(rows, cols), backend=Backend.ConPTY)
        self.pid = self.process.pid

    def read(self):
        try:
            return self.process.read(65536).encode("utf-8")
        except EOFError:
            return b""

    def write(self, data):
        self.process.write(data)

    def resize(self, cols, rows):
        self.process.setwinsize(rows, cols)

    def alive(self):
        return self.process.isalive()

    def terminate(self, force=False):
        if force:
            subprocess.run(
                ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                capture_output=True,
                creationflags=0x08000000,
                timeout=5,
            )
        else:
            self.write("\x03")

    def wait(self):
        self.process.close()
        return self.process.exitstatus
