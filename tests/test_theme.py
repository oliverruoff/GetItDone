import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
)

from app.main import configure_style
from app.models import Notebook
from app.storage import Store
from app.ui.colors import PALETTE, ColorPalette
from app.ui.dialogs import ReminderDialog, SettingsDialog
from app.ui.icons import icon_button
from app.ui.tasks import ROLE, Tasks
from app.ui.theme import EVERFOREST, apply_theme, color, row_color, styled
from app.ui.window import Window


@pytest.fixture
def theme_app(qapp):
    configure_style(qapp)
    yield qapp
    configure_style(qapp)


def test_everforest_styles_existing_controls_popups_and_icons(theme_app, qtbot, tmp_path):
    button = icon_button("plus", "Add", lambda: None)
    qtbot.addWidget(button)
    light_icon = button.icon().cacheKey()
    styled(button, "color: $success;")
    picker = ColorPalette(PALETTE[0][1])
    qtbot.addWidget(picker)
    apply_theme(theme_app, "everforest")
    assert theme_app.palette().color(QPalette.Window).name() == EVERFOREST["window"]
    assert theme_app.palette().color(QPalette.Text).name() == EVERFOREST["text"]
    assert button.icon().cacheKey() != light_icon
    assert EVERFOREST["success"] in button.styleSheet()
    assert row_color(PALETTE[0][1]) in picker.swatches[0].styleSheet()
    assert picker.swatches[0].text() == "✓"
    assert picker.swatches[0].property("color") == PALETTE[0][1]
    widgets = [QMenu(), QComboBox(), QMessageBox(), QFileDialog(directory=str(tmp_path)), QPlainTextEdit()]
    for widget in widgets:
        qtbot.addWidget(widget)
        widget.ensurePolished()
        assert widget.palette().color(QPalette.WindowText).name() == EVERFOREST["text"]
        assert widget.palette().color(QPalette.Base).lightnessF() < 0.3
    assert theme_app.testAttribute(Qt.AA_DontUseNativeDialogs)
    apply_theme(theme_app, "light")
    assert button.icon().cacheKey() == light_icon
    assert PALETTE[0][1] in picker.swatches[0].styleSheet()
    assert color("success") in button.styleSheet()
    apply_theme(theme_app, "unknown-future-theme")
    assert theme_app.property("appearanceTheme") == "light"


def test_dark_task_rows_notes_checkboxes_and_custom_colors(theme_app, qtbot):
    apply_theme(theme_app, "everforest")
    book = Notebook()
    parent = book.add("Forest task https://example.org")
    child = book.add("A child", parent=parent["id"])
    category = dict(id="custom", name="Keep this name", color=PALETTE[0][1])
    book.data["categories"].append(category)
    book.update(parent["id"], category_id=category["id"], notes="Inline note")
    tasks = Tasks(book, {})
    qtbot.addWidget(tasks)
    tasks.resize(1100, 500)
    tasks.show()
    tasks.rows[parent["id"]].setExpanded(True)
    for ident in (parent["id"], child["id"]):
        row = tasks.rows[ident]
        assert row.data(0, ROLE + 2).lightnessF() < 0.3
        assert row.foreground(0).color().name() == EVERFOREST["text"]
    assert category["color"] == PALETTE[0][1]
    assert category["name"] == "Keep this name"
    for _, source in PALETTE:
        assert QColor(row_color(source)).lightnessF() < 0.3
    # Neutral custom categories must stay neutral, not acquire a red hue.
    neutral = QColor(row_color("#cccccc"))
    assert max(neutral.red(), neutral.green(), neutral.blue()) - min(neutral.red(), neutral.green(), neutral.blue()) <= 15
    assert not tasks.tree.viewport().grab().isNull()
    tasks.show_undo(parent["id"])
    assert EVERFOREST["success_bg"] in tasks.undo_notices[parent["id"]].styleSheet()
    reminder = ReminderDialog(parent, tasks)
    qtbot.addWidget(reminder)
    reminder.ensurePolished()
    assert reminder.palette().color(QPalette.Window).name() == EVERFOREST["window"]


def test_appearance_saves_applies_roundtrips_and_cancel_preserves(theme_app, qtbot, tmp_path, monkeypatch):
    from app import autostart

    monkeypatch.setattr(autostart, "enabled", lambda: False)
    store = Store(tmp_path)
    book = Notebook(store.load())
    book.data["settings"]["default_workdir"] = str(tmp_path)
    item = book.add("Appearance roundtrip")
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.show()

    def save_dark(dialog):
        tabs = dialog.findChild(QTabWidget)
        assert "Appearance" in [tabs.tabText(i) for i in range(tabs.count())]
        dialog.theme.setCurrentIndex(dialog.theme.findData("everforest"))
        dialog.check()
        return dialog.result()

    try:
        monkeypatch.setattr(SettingsDialog, "exec", save_dark)
        window.settings_dialog()
        assert window.notebook.data["settings"]["theme"] == "everforest"
        assert theme_app.property("appearanceTheme") == "everforest"
        assert window.tasks.rows[item["id"]].data(0, ROLE + 2).name() == EVERFOREST["root"]
        assert window.flush()
        data = Store(tmp_path).load()
        assert data["settings"]["theme"] == "everforest"
        configure_style(theme_app, data["settings"]["theme"])
        dialog = SettingsDialog(data, store.path, "Notifications", window)
        qtbot.addWidget(dialog)
        assert dialog.theme.currentData() == "everforest"

        def cancel_light(dialog):
            dialog.theme.setCurrentIndex(dialog.theme.findData("light"))
            dialog.reject()
            return dialog.result()

        monkeypatch.setattr(SettingsDialog, "exec", cancel_light)
        window.settings_dialog()
        assert window.notebook.data["settings"]["theme"] == "everforest"
        assert theme_app.property("appearanceTheme") == "everforest"

        # Already-loaded optional tabs switch too, without being recreated.
        pages = {name: window.load_page(name) for name in window.optional_pages}
        for page in pages.values():
            page.ensurePolished()
            assert page.palette().color(QPalette.WindowText).name() == EVERFOREST["text"]
        canvas_html = (tmp_path / "canvas" / "canvas.html").read_bytes()

        def save_light(dialog):
            dialog.theme.setCurrentIndex(dialog.theme.findData("light"))
            dialog.check()
            return dialog.result()

        monkeypatch.setattr(SettingsDialog, "exec", save_light)
        window.settings_dialog()
        assert theme_app.property("appearanceTheme") == "light"
        assert window.tasks.rows[item["id"]].data(0, ROLE + 2).name() == color("root")
        assert all(window.optional_pages[name]["widget"] is page for name, page in pages.items())
        assert (tmp_path / "canvas" / "canvas.html").read_bytes() == canvas_html
    finally:
        window.timer.stop()
        window.scheduler.shutdown()
        window.notifier.close()
        canvas = window.optional_pages["canvas"]["widget"]
        if canvas is not None:
            canvas.timer.stop()
        window.tray.hide()
        window.quitting = True


def test_terminal_theme_changes_without_reloading_or_clearing_output(theme_app, qtbot):
    from app.terminal.bridge import Terminal

    terminal = Terminal()
    qtbot.addWidget(terminal)
    terminal.show()
    qtbot.waitUntil(lambda: terminal.ready_state, timeout=15000)
    terminal.output_ready.emit("KEEP THIS OUTPUT")
    output = []

    def output_rendered():
        terminal.page().runJavaScript("terminal.buffer.active.getLine(0).translateToString()", output.append)
        return bool(output and "KEEP THIS OUTPUT" in output[-1])

    qtbot.waitUntil(output_rendered)
    apply_theme(theme_app, "everforest")
    results = []
    terminal.page().runJavaScript(
        "JSON.stringify([terminal.options.theme.background, document.body.style.background, terminal.buffer.active.getLine(0).translateToString()])",
        results.append,
    )
    qtbot.waitUntil(lambda: bool(results))
    result = json.loads(results[0])
    assert result[0] == EVERFOREST["base"]
    assert "KEEP THIS OUTPUT" in result[2]
    assert terminal.page().backgroundColor().name() == EVERFOREST["base"]
    apply_theme(theme_app, "light")
    assert terminal.page().backgroundColor().name() == "#18202b"
    terminal.timer.stop()
