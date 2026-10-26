"""Unix PTY backend, also usable on Linux for development."""

import errno
import fcntl
import os
import pty
import signal
import struct
import subprocess
import sys
import termios
from pathlib import Path


class Process:
    def __init__(self, command, cwd, cols=100, rows=28):
        self.master, slave = pty.openpty()
        self.process = None
        self.cleaned = False
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
            env["PATH"] = os.pathsep.join(
                dict.fromkeys(
                    [
                        str(Path(command[0]).parent),
                        env.get("PATH", ""),
                        str(Path.home() / ".local/bin"),
                        "/opt/homebrew/bin",
                        "/usr/local/bin",
                    ]
                )
            )
            # Frozen application re-enters via main's --pty-child dispatch.
            helper = (
                [sys.executable, "--pty-child"]
                if getattr(sys, "frozen", False)
                else [sys.executable, str(Path(__file__).with_name("child.py"))]
            )
            self.process = subprocess.Popen(
                [*helper, *command],
                cwd=cwd,
                env=env,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                start_new_session=True,
                close_fds=True,
            )
        except Exception:
            os.close(self.master)
            raise
        finally:
            os.close(slave)

    def read(self):
        try:
            return os.read(self.master, 65536)
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.EBADF):
                return b""
            raise

    def write(self, data):
        view = memoryview(data.encode("utf-8"))
        while view:
            count = os.write(self.master, view)
            view = view[count:]

    def resize(self, cols, rows):
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def alive(self):
        return self.process.poll() is None

    def terminate(self, force=False):
        if self.cleaned:
            return
        # Reap an exited leader before signalling its process group (macOS can
        # otherwise return EPERM for a group containing only the zombie).
        self.process.poll()
        try:
            os.killpg(self.process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            if self.process.returncode is None:
                raise

    def wait(self):
        code = self.process.wait()
        try:
            os.close(self.master)
        except OSError:
            pass
        # Any descendants left after the main agent exits belong to this session too.
        self.terminate(force=True)
        self.cleaned = True
        return code
