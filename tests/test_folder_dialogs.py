import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLineEdit, QPushButton, QTabWidget

from app.models import Notebook
from app.storage import Store
from app.ui.dialogs import SessionDialog, SettingsDialog
from app.ui.scheduled import ScheduleDialog
from app.ui.window import Window


@pytest.mark.parametrize("kind", ["settings", "backup", "session", "scheduled"])
@pytest.mark.parametrize("accept", [True, False])
def test_folder_picker_opens_without_dismissing_owner(qtbot, tmp_path, monkeypatch, kind, accept):
    monkeypatch.setattr("app.autostart.enabled", lambda: False)
    monkeypatch.setattr(SessionDialog, "probe", lambda self: None)
    settings = {"default_workdir": str(tmp_path)}
    if kind in ("settings", "backup"):
        data = Notebook().data
        data["settings"].update(settings)
        dialog = SettingsDialog(data, tmp_path / "data" / "notebook.json", "Test")
        if kind == "backup":
            dialog.findChild(QTabWidget).setCurrentIndex(1)
            dialog.backups.enabled.setChecked(True)
            button = dialog.backups.choose
            field = dialog.backups.folder
        else:
            general = dialog.findChild(QTabWidget).widget(0)
            button = next(b for b in general.findChildren(QPushButton) if b.text() == "Choose folder …")
            field = dialog.workdir
    elif kind == "session":
        dialog = SessionDialog(settings)
        button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Choose …")
        field = dialog.workdir
    else:
        dialog = ScheduleDialog(settings)
        button = next(b for b in dialog.findChildren(QPushButton) if b.toolTip() == "Choose working folder")
        field = dialog.directory
    qtbot.addWidget(dialog)
    assert dialog.windowType() == Qt.Dialog  # Qt.Popup is dismissed when the native picker takes focus.
    original = field.text()
    selected = tmp_path / "selected"
    selected.mkdir()
    real_picker = QFileDialog.getExistingDirectory
    observed = []

    def choose(parent, caption, directory):
        def respond():
            picker = next((w for w in QApplication.topLevelWidgets()
                           if isinstance(w, QFileDialog) and w.isVisible()), None)
            if picker is None:
                QTimer.singleShot(25, respond)
                return
            observed.append((dialog.isVisible(), picker.isVisible(), picker.parentWidget() is parent))
            if accept:
                picker.setDirectory(str(selected))
                picker.findChild(QLineEdit, "fileNameEdit").clear()
                picker.accept()
            else:
                picker.reject()

        QTimer.singleShot(25, respond)
        # Exercise a real modal QFileDialog without requiring manual interaction with OS-owned UI.
        return real_picker(parent, caption, directory, QFileDialog.DontUseNativeDialog)

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    assert button.isVisible() and button.isEnabled()
    qtbot.mouseClick(button, Qt.LeftButton)
    assert observed == [(True, True, True)]
    assert dialog.isVisible()
    assert field.text().replace("\\", "/") == (str(selected).replace("\\", "/") if accept
                                               else original.replace("\\", "/"))
    dialog.reject()


def test_settings_menu_and_title_have_no_ellipsis(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("app.autostart.enabled", lambda: False)
    store = Store(tmp_path)
    window = Window(store, store.load())
    qtbot.addWidget(window)
    window.timer.stop()
    window.tray.hide()
    window.quitting = True
    file_menu = window.menuBar().actions()[0].menu()
    action = next(action for action in file_menu.actions() if action.text().startswith("Settings"))
    assert action.text() == "Settings"
    dialog = SettingsDialog(window.notebook.data, store.path, "Test", window)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Settings"
    assert isinstance(dialog, QDialog)
