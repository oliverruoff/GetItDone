import subprocess
import sys
import threading

import pytest
from PySide6.QtCore import Qt

from app.storage import Store
from app.ui.window import Window


@pytest.fixture
def window(qtbot, tmp_path):
    store = Store(tmp_path)
    widget = Window(store, store.load())
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    widget.timer.stop()
    widget.scheduler.shutdown()
    widget.notifier.close()
    widget.tray.hide()
    widget.quitting = True
    widget.close()


def test_cold_start_and_shutdown_never_import_browser_or_pdf(tmp_path):
    code = """
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.storage import Store
from app.ui.window import Window
app = QApplication([])
store = Store(Path(sys.argv[1]))
window = Window(store, store.load())
window.show()
app.processEvents()
assert not any(page['widget'] for page in window.optional_pages.values())
assert window.save_all()
assert window.prepare_backup()
window.quit_app()
window.finish_quit()
assert not any(name.startswith(('PySide6.QtWebEngine', 'PySide6.QtPdf')) for name in sys.modules)
assert not window.all_terminals()
print('TASKS_ONLY_OK')
"""
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TASKS_ONLY_OK" in result.stdout


@pytest.mark.parametrize("maximized", [False, True])
def test_first_canvas_open_keeps_native_window_alive(tmp_path, maximized):
    # A fresh process is essential: an earlier WebEngine view can hide the bug.
    code = """
import sys
from pathlib import Path
from PySide6.QtCore import QEvent, QEventLoop, QObject, QTimer
from PySide6.QtWidgets import QApplication
from app.storage import Store
from app.ui.window import Window

app = QApplication([])
store = Store(Path(sys.argv[1]))
window = Window(store, store.load())
window.showMaximized() if sys.argv[2] == 'True' else window.show()
app.processEvents()
native_id = int(window.winId())
geometry = window.geometry()
state = window.windowState()
events = []

class Watcher(QObject):
    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Hide, QEvent.WinIdChange):
            events.append(event.type())
        return False

watcher = Watcher()
window.installEventFilter(watcher)
assert not any(name.startswith('PySide6.QtWebEngine') for name in sys.modules)
window.workspace.setCurrentIndex(window.optional_pages['canvas']['index'])
loop = QEventLoop()
QTimer.singleShot(1500, loop.quit)
loop.exec()
canvas = window.optional_pages['canvas']['widget']
assert canvas is not None
assert canvas.view.title() == 'GetItDone Canvas'
assert not events, events
assert int(window.winId()) == native_id
assert window.isVisible()
assert window.geometry() == geometry
assert window.windowState() == state
window.workspace.setCurrentIndex(0)
app.processEvents()
window.workspace.setCurrentIndex(window.optional_pages['canvas']['index'])
app.processEvents()
assert window.optional_pages['canvas']['widget'] is canvas
assert not events, events
window.quit_app()
window.finish_quit()
print('CANVAS_WINDOW_STABLE_OK')
"""
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path), str(maximized)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CANVAS_WINDOW_STABLE_OK" in result.stdout


def test_todos_edit_and_persist_before_optional_tabs_load(window, qtbot):
    window.append_item()
    editor = window.tasks.tree.focusWidget()
    qtbot.keyClicks(editor, "Ready immediately")
    qtbot.keyClick(editor, Qt.Key_Return)
    assert window.save_all()
    assert window.store.load()["items"][0]["text"] == "Ready immediately"
    window.tick()
    assert all(page["widget"] is None for page in window.optional_pages.values())
    assert not (window.store.folder / "canvas").exists()


@pytest.mark.parametrize("state", [Qt.WindowNoState, Qt.WindowMaximized, Qt.WindowFullScreen])
@pytest.mark.parametrize("shortcut", ["Ctrl+T", "Ctrl+N"])
def test_quick_shortcuts_preserve_window_state_and_geometry(window, qtbot, monkeypatch, state, shortcut):
    notes = []
    if shortcut == "Ctrl+N":
        monkeypatch.setattr(window.knowledge, "new_note", lambda: notes.append(True))
    window.setWindowState(state)
    qtbot.wait(100)
    geometry = window.geometry()
    previous_state = window.windowState()
    count = len(window.notebook.items)

    action = next(action for action in window.actions() if action.shortcut().toString() == shortcut)
    action.trigger()
    qtbot.wait(100)

    assert window.windowState() == previous_state
    assert window.geometry() == geometry
    if shortcut == "Ctrl+T":
        assert len(window.notebook.items) == count + 1
    else:
        assert notes == [True]
        assert window.workspace.currentWidget() is window.knowledge


@pytest.mark.parametrize("state", [Qt.WindowNoState, Qt.WindowMaximized, Qt.WindowFullScreen])
@pytest.mark.parametrize("hidden", [False, True])
def test_restore_reveals_window_and_preserves_mode(window, qtbot, state, hidden):
    window.setWindowState(state)
    qtbot.wait(100)
    if hidden:
        window.hide()
    else:
        window.showMinimized()
    qtbot.wait(100)

    window.restore()
    qtbot.wait(100)

    assert window.isVisible()
    assert not window.isMinimized()
    assert window.windowState() & (Qt.WindowMaximized | Qt.WindowFullScreen) == state


@pytest.mark.parametrize("name", ["knowledge", "canvas", "inspector", "scheduled", "executions"])
def test_selected_tab_loads_once_without_loading_other_tabs(window, qtbot, name):
    page = window.optional_pages[name]
    window.workspace.setCurrentIndex(page["index"])
    qtbot.waitUntil(lambda: page["widget"] is not None)
    assert window.workspace.currentWidget() is page["widget"]
    first = page["widget"]
    window.workspace.setCurrentIndex(0)
    window.workspace.setCurrentIndex(page["index"])
    qtbot.wait(50)
    assert page["widget"] is first
    assert all(other["widget"] is None for key, other in window.optional_pages.items() if key != name)


def test_slow_knowledge_listing_runs_in_worker_and_does_not_block_todos(window, qtbot, monkeypatch):
    from app.ui import knowledge

    started, release = threading.Event(), threading.Event()
    threads = []
    path = window.store.folder / "Reference.txt"
    path.write_text("Reference", encoding="utf-8")
    window.notebook.data["settings"]["knowledge_folder"] = str(window.store.folder)

    def slow_list(folder, sort):
        threads.append(threading.get_ident())
        started.set()
        release.wait(5)
        return [path]

    monkeypatch.setattr(knowledge, "list_documents", slow_list)
    try:
        panel = window.knowledge
        qtbot.waitUntil(started.is_set)
        assert len(threads) == 1 and threads[0] != threading.get_ident()
        window.append_item()
        editor = window.tasks.tree.focusWidget()
        qtbot.keyClicks(editor, "Typing during loading")
        qtbot.keyClick(editor, Qt.Key_Return)
        assert window.store.load()["items"][0]["text"] == "Typing during loading"
        assert panel.files.count() == 0
    finally:
        release.set()
    qtbot.waitUntil(lambda: panel.files.count() == 1)


def test_notification_setup_can_be_cancelled_before_first_paint(window):
    assert not window.notifier.initialized
    window.notifier.close()
    window.notifier.initialize()
    assert not window.notifier.initialized


def test_tab_selection_cancelled_by_quit_does_not_load_browser(window):
    index = window.optional_pages["canvas"]["index"]
    window.workspace.setCurrentIndex(index)
    window.quitting = True
    window.load_current_page(index)
    assert window.optional_pages["canvas"]["widget"] is None


def test_failed_optional_tab_keeps_todos_usable(window, qtbot, monkeypatch):
    from PySide6.QtWidgets import QLabel

    def fail(name):
        raise OSError("Folder unavailable")

    monkeypatch.setattr(window, "load_page", fail)
    window.workspace.setCurrentIndex(window.optional_pages["canvas"]["index"])
    qtbot.waitUntil(lambda: "Folder unavailable" in window.workspace.currentWidget().findChild(QLabel).text())
    window.append_item()
    editor = window.tasks.tree.focusWidget()
    qtbot.keyClicks(editor, "Still usable")
    qtbot.keyClick(editor, Qt.Key_Return)
    assert window.store.load()["items"][0]["text"] == "Still usable"


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows taskbar identity and icons")
def test_windows_identity_precedes_qt_and_native_icon_exists_before_notifications(tmp_path):
    code = """
import ctypes
import sys
from PySide6 import QtWidgets
from PySide6.QtCore import QTimer
from app.ui.window import Window, app_icon
from app.notifications.windows import APP_ID

def check_identity():
    value = ctypes.c_wchar_p()
    shell = ctypes.windll.shell32
    shell.GetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.POINTER(ctypes.c_wchar_p)]
    assert shell.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(value)) == 0
    try:
        assert value.value == APP_ID
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(value, ctypes.c_void_p))

class CheckedApplication(QtWidgets.QApplication):
    def __init__(self, *args):
        check_identity()
        print('IDENTITY_BEFORE_QT_OK', flush=True)
        super().__init__(*args)

QtWidgets.QApplication = CheckedApplication
original_show = Window.show
def checked_show(window):
    assert not window.notifier.initialized
    assert 'windows_toasts' not in sys.modules
    assert not any(name.startswith('winrt') for name in sys.modules)
    expected = app_icon()
    assert not expected.isNull()
    assert len(expected.availableSizes()) > 1
    assert not window.windowIcon().isNull()
    assert not QtWidgets.QApplication.instance().windowIcon().isNull()
    original_show(window)
    user = ctypes.windll.user32
    user.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user.SendMessageW.restype = ctypes.c_ssize_t
    assert user.SendMessageW(int(window.winId()), 0x007F, 1, 0)  # WM_GETICON / ICON_BIG
    print('NATIVE_WINDOW_ICON_OK', flush=True)
    QTimer.singleShot(250, window.quit_app)

Window.show = checked_show
sys.argv = ['getitdone', '--data-dir', sys.argv[1], '--smoke']
from app.main import main
raise SystemExit(main())
"""
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "IDENTITY_BEFORE_QT_OK" in result.stdout
    assert "NATIVE_WINDOW_ICON_OK" in result.stdout
