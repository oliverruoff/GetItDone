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
        assert ask(qtbot, tmp_path, "status")["status"] == "stopping"
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


def test_gid_launch_activates_other_revision_without_shutting_it_down(tmp_path):
    root = Path(__file__).resolve().parents[1]
    # Deliberately serve a different loaded revision, as after editing sources.
    bootstrap = '''
import sys
from pathlib import Path
from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication
from app.instance import InstanceServer
from app.storage import Store
from app.ui.window import Window
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
store = Store(Path(sys.argv[1]))
lock = QLockFile(str(store.folder / "instance.lock"))
assert lock.tryLock(0)
window = Window(store, store.load())
server = InstanceServer(store.folder, window, "previous-source-revision", app)
window.hide()
app.exec()
server.close()
lock.unlock()
'''
    first = subprocess.Popen(
        [sys.executable, "-c", bootstrap, str(tmp_path)], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if request(tmp_path, "status", timeout=500):
                break
            if first.poll() is not None:
                raise AssertionError(first.communicate())
            time.sleep(0.05)
        else:
            raise AssertionError("First instance did not become ready")
        result = subprocess.run(
            [sys.executable, "-m", "app.launcher", "--data-dir", str(tmp_path)],
            cwd=root, capture_output=True, timeout=10,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert first.poll() is None
        assert request(tmp_path, "status", timeout=1000) == {
            "revision": "previous-source-revision", "status": "running",
        }
        assert request(tmp_path, "replace", timeout=1000)["status"] == "replacing"
        out, err = first.communicate(timeout=10)
        assert first.returncode == 0, (out, err)
    finally:
        if first.poll() is None:
            first.terminate()
            first.wait(timeout=5)


def test_failed_shutdown_reenables_notebook(qtbot, tmp_path, monkeypatch):
    from app.storage import Store
    from app.ui.window import Window

    store = Store(tmp_path)
    window = Window(store, store.load())
    qtbot.addWidget(window)
    monkeypatch.setattr("app.ui.window.confirm", lambda *args: True)

    class StuckTerminal:
        running = True

        def stop(self):
            pass

        def force_stop(self):
            raise subprocess.TimeoutExpired("taskkill", 5)

    window.terminals["stuck"] = StuckTerminal()
    window.quit_app()
    assert window.quitting and not window.isEnabled()
    window.finish_quit()
    assert not window.quitting and window.isEnabled()
    assert window.timer.isActive()
    assert "Could not stop a session" in window.statusBar().currentMessage()
    window.terminals.clear()
    window.timer.stop()
    window.saver.stop()
    window.quitting = True
    window.tray.hide()


def test_shutdown_timeout_reenables_notebook(qtbot, tmp_path):
    from app.storage import Store
    from app.ui.window import Window

    store = Store(tmp_path)
    window = Window(store, store.load())
    qtbot.addWidget(window)
    window.quitting = True
    window.quit_deadline = time.monotonic() - 1
    window.setEnabled(False)
    window.finish_quit()
    assert not window.quitting and window.isEnabled()
    assert "Shutdown did not finish" in window.statusBar().currentMessage()
    window.timer.stop()
    window.saver.stop()
    window.quitting = True
    window.tray.hide()


def test_completed_shutdown_exits_despite_remaining_close_veto(tmp_path):
    root = Path(__file__).resolve().parents[1]
    bootstrap = '''
import sys
from pathlib import Path
from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QWidget
from app.storage import Store
from app.ui.window import Window
class RemainingWindow(QWidget):
    def closeEvent(self, event):
        event.ignore()
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
store = Store(Path(sys.argv[1]))
lock = QLockFile(str(store.folder / "instance.lock"))
assert lock.tryLock(0)
window = Window(store, store.load())
from app.terminal.bridge import Terminal
import app.ui.window as window_module
window_module.confirm = lambda *args: True
terminal = Terminal(window)
window.terminals["local-test"] = terminal
window.tabs.addTab(terminal, "Local test")
terminal.start([sys.executable, "-u", "-c", "import time; print('READY', flush=True); time.sleep(60)"], str(store.folder))
remaining = RemainingWindow()
window.show()
remaining.show()
QTimer.singleShot(100, window.quit_app)
result = app.exec()
lock.unlock()
sys.exit(result)
'''
    process = subprocess.Popen(
        [sys.executable, "-c", bootstrap, str(tmp_path)], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        out, err = process.communicate(timeout=10)
        assert process.returncode == 0, (out, err)
        lock = QLockFile(str(tmp_path / "instance.lock"))
        assert lock.tryLock(0)
        lock.unlock()
        assert (tmp_path / "notebook.json").is_file()
    finally:
        if process.poll() is None:
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
