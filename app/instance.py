"""A second launch activates the current app or requests a safe version handover.

The existing window owns save/conflict/session confirmations. Never kill a process
or remove its lock to make a second copy appear to have started successfully.
"""

import hashlib
import json
import time
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name(folder):
    key = str(Path(folder).resolve()).encode("utf-8")
    return "getitdone-" + hashlib.sha256(key).hexdigest()[:24]


def request(folder, action, timeout=30000):
    socket = QLocalSocket()
    socket.connectToServer(server_name(folder))
    if not socket.waitForConnected(1000):
        return None
    socket.write(json.dumps({"action": action}).encode() + b"\n")
    socket.flush()
    deadline = time.monotonic() + timeout / 1000
    response = bytearray()
    while time.monotonic() < deadline:
        if socket.bytesAvailable() or socket.waitForReadyRead(
            max(1, int((deadline - time.monotonic()) * 1000))
        ):
            response.extend(bytes(socket.readAll()))
            if b"\n" in response:
                socket.disconnectFromServer()
                return json.loads(response.split(b"\n")[0])
        if socket.state() == QLocalSocket.UnconnectedState:
            break
    socket.abort()
    return None


class InstanceServer(QObject):
    def __init__(self, folder, window, revision, parent=None):
        super().__init__(parent)
        self.window = window
        self.revision = revision
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        name = server_name(folder)
        # Only construct this after acquiring the data-directory lock.
        QLocalServer.removeServer(name)
        if not self.server.listen(name):
            raise OSError("Could not open the application startup channel: " + self.server.errorString())
        self.server.newConnection.connect(self.connected)

    def connected(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.setParent(self)
            socket.disconnected.connect(socket.deleteLater)
            socket.readyRead.connect(lambda s=socket: self.receive(s))
            socket.setProperty("buffer", b"")
            if socket.bytesAvailable():
                self.receive(socket)

    def receive(self, socket):
        data = socket.property("buffer") + bytes(socket.readAll())
        if len(data) > 1024:
            socket.abort()
            return
        if b"\n" not in data:
            socket.setProperty("buffer", data)
            return
        try:
            action = json.loads(data.split(b"\n")[0]).get("action")
        except (ValueError, AttributeError):
            socket.abort()
            return
        result = {"revision": self.revision}
        if action == "status":
            result["status"] = "running"
        elif action == "activate":
            self.window.restore()
            result["status"] = "activated"
        elif action == "replace":
            self.window.restore()
            self.window.quit_app()
            result["status"] = "replacing" if self.window.quitting else "cancelled"
        else:
            result["status"] = "invalid"
        socket.write(json.dumps(result).encode() + b"\n")
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()

    def close(self):
        self.server.close()


class BuildActivationWatcher(QObject):
    """Finder reuses running app processes: check the on-disk build on activation."""

    def __init__(self, application, window, loaded_revision, current_revision):
        super().__init__(application)
        self.window = window
        self.loaded_revision = loaded_revision
        self.current_revision = current_revision
        self.restart = False
        # A global Python event filter sees partially constructed WebEngine
        # QObjects and can crash Shiboken. Use Qt's activation signal instead.
        application.applicationStateChanged.connect(self.state_changed)

    def state_changed(self, state):
        from PySide6.QtCore import Qt, QTimer

        if state == Qt.ApplicationActive and not self.restart:
            QTimer.singleShot(0, self.check)

    def check(self):
        if self.restart or self.window.quitting:
            return
        try:
            changed = self.current_revision() != self.loaded_revision
        except (OSError, ValueError, KeyError):
            # The bundle may be in the middle of being replaced by a build.
            return
        if changed:
            self.window.quit_app()
            self.restart = self.window.quitting
