import json
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QLocalSocket

from app.build_info import source_revision
from app.instance import InstanceServer, request, server_name


class TestWindow:
    __test__ = False

    def __init__(self):
        self.quitting = False
        self.restored = 0
        self.cancel = False

    def restore(self):
        self.restored += 1

    def quit_app(self):
        self.quitting = not self.cancel


def ask(qtbot, folder, action):
    # In-process tests use an async client so the server's Qt loop can run.
    # The blocking startup client is covered by the separate-process test below.
    socket = QLocalSocket()
    socket.connectToServer(server_name(folder))
    qtbot.waitUntil(lambda: socket.state() == QLocalSocket.ConnectedState)
    socket.write(json.dumps({"action": action}).encode() + b"\n")
    socket.flush()
    qtbot.waitUntil(lambda: socket.bytesAvailable() > 0, timeout=5000)
    return json.loads(bytes(socket.readAll()))


def test_second_launch_activation_replacement_and_cancel(qtbot, tmp_path):
    window = TestWindow()
    server = InstanceServer(tmp_path, window, "new-code")
    try:
        assert ask(qtbot, tmp_path, "status") == {"revision": "new-code", "status": "running"}
        assert ask(qtbot, tmp_path, "activate")["status"] == "activated"
        assert window.restored == 1 and not window.quitting
        window.cancel = True
        assert ask(qtbot, tmp_path, "replace")["status"] == "cancelled"
        assert not window.quitting
        window.cancel = False
        assert ask(qtbot, tmp_path, "replace")["status"] == "replacing"
        assert window.quitting
    finally:
        server.close()


def test_channels_are_specific_to_data_directory(tmp_path):
    assert server_name(tmp_path) == server_name(tmp_path / ".")
    assert server_name(tmp_path / "a") != server_name(tmp_path / "b")


def test_revision_changes_with_source_but_not_bytecode(tmp_path):
    path = tmp_path / "main.py"
    path.write_text("first")
    first = source_revision(tmp_path)
    path.write_text("second")
    assert source_revision(tmp_path) != first
    second = source_revision(tmp_path)
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "ignored.py").write_text("ignored")
    assert source_revision(tmp_path) == second


def test_launcher_hands_over_real_process_and_releases_lock(tmp_path):
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-B", "-m", "app", "--data-dir", str(tmp_path), "--smoke"]
    first = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    second = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if (tmp_path / "instance.lock").exists() and request(tmp_path, "status", timeout=1000):
                break
            if first.poll() is not None:
                raise AssertionError(first.communicate())
            time.sleep(0.05)
        else:
            raise AssertionError("First instance did not become ready")
        second = subprocess.Popen(
            [*command, "--replace-running"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        first_out, first_err = first.communicate(timeout=10)
        assert first.returncode == 0, (first_out, first_err)
        second_out, second_err = second.communicate(timeout=10)
        assert second.returncode == 0, (second_out, second_err)
        assert (tmp_path / "notebook.json").is_file()
        lock = QLockFile(str(tmp_path / "instance.lock"))
        assert lock.tryLock(0)
        lock.unlock()
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


def test_finder_reopen_detects_replaced_bundle(qtbot):
    from PySide6.QtWidgets import QApplication

    from app.instance import BuildActivationWatcher

    window = TestWindow()
    application = QApplication.instance()
    current = ["old"]
    watcher = BuildActivationWatcher(application, window, "old", lambda: current[0])
    try:
        watcher.check()
        assert not watcher.restart
        current[0] = "new"
        watcher.check()
        assert watcher.restart and window.quitting
    finally:
        watcher.deleteLater()


def test_finder_reopen_respects_cancelled_shutdown(qtbot):
    from PySide6.QtWidgets import QApplication

    from app.instance import BuildActivationWatcher

    window = TestWindow()
    window.cancel = True
    application = QApplication.instance()
    watcher = BuildActivationWatcher(application, window, "old", lambda: "new")
    try:
        watcher.check()
        assert not watcher.restart and not window.quitting
    finally:
        watcher.deleteLater()
