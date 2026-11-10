"""Shared light / Everforest colors for native widgets and custom-painted UI."""

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = dict(
    window="#f6f8fc", panel="#edf0f4", base="#ffffff", alternate="#f7f9fb",
    text="#243247", muted="#64738b", border="#cbd4e0", strong_border="#9aaec7",
    accent="#355d84", accent_text="#23588b", selection="#dce9f7", selected_text="#172b43",
    hover="#eaf2fc", pressed="#d5e5f7", root="#e8edf5", success="#28765b",
    error="#b02c35", warning="#a44b26", success_bg="#edf7f2", success_border="#b4d6c6",
    icon="#34445b", toast="#243247", toast_text="#ffffff",
)

# Everforest's dark background, foreground and accent colors, as used by OpenCode.
EVERFOREST = dict(
    window="#2d353b", panel="#333c43", base="#2d353b", alternate="#343f44",
    text="#d3c6aa", muted="#9da9a0", border="#475258", strong_border="#7a8478",
    accent="#a7c080", accent_text="#a7c080", selection="#475b50", selected_text="#e4dccb",
    hover="#3d484d", pressed="#475258", root="#333c43", success="#a7c080",
    error="#e67e80", warning="#e69875", success_bg="#37463d", success_border="#637b60",
    icon="#d3c6aa", toast="#475b50", toast_text="#e4dccb",
)


def theme_name():
    app = QApplication.instance()
    return (app.property("appearanceTheme") or "light") if app else "light"


def is_dark():
    return theme_name() == "everforest"


def color(role):
    return (EVERFOREST if is_dark() else LIGHT)[role]


def styled(widget, template):
    """Keep local overrides synchronized when the application theme changes."""
    widget.setProperty("themeStyle", template)
    widget.setStyleSheet(Template(template).substitute(EVERFOREST if is_dark() else LIGHT))


def row_color(value):
    """Tint dark surfaces with category hue; never modify the saved category."""
    if not is_dark():
        return value
    source, surface = QColor(value), QColor(color("base"))
    if not source.isValid():
        return surface.name()
    hue, saturation, _, _ = source.getHslF()
    tint = QColor.fromHslF(max(0, hue), saturation, 0.52)
    return QColor(*(round(a * 0.20 + b * 0.80) for a, b in zip(
        (tint.red(), tint.green(), tint.blue()), (surface.red(), surface.green(), surface.blue())
    ))).name()


STYLESHEET = """
    QMainWindow, QWidget { font-size: 13px; }
    QMainWindow, QDialog { background: $window; color: $text; }
    QToolBar { background: $panel; border-bottom: 1px solid $border; spacing: 3px; padding: 5px; }
    QToolButton { padding: 6px 7px; color: $text; }
    QToolButton:hover { background: $hover; }
    QTreeWidget, QListWidget, QPlainTextEdit, QTextEdit, QTextBrowser, QAbstractItemView {
        background: $base; color: $text; alternate-background-color: $alternate;
        border: 1px solid $border; selection-background-color: $selection; selection-color: $selected_text;
    }
    QTreeWidget::item { min-height: 24px; border-bottom: 1px solid $border; }
    QTreeWidget::item:selected, QListWidget::item:selected { background: $selection; color: $selected_text; }
    QHeaderView::section { background: $panel; color: $muted; border: none;
        border-bottom: 1px solid $border; padding: 6px; font-weight: 500; }
    QPushButton { padding: 6px 10px; background: $base; border: 1px solid $border;
        border-radius: 6px; color: $text; }
    QPushButton:hover { background: $hover; border-color: $accent; }
    QPushButton:pressed { background: $pressed; }
    QPushButton:focus { border: 2px solid $accent; }
    QPushButton:disabled, QToolButton:disabled { color: $muted; background: $panel; }
    QTreeWidget#taskTree::item { min-height: 24px; }
    QTreeWidget#taskTree QPushButton { padding: 2px 8px; }
    QPushButton#addTask { text-align: left; padding-left: 18px; background: $panel;
        color: $accent_text; border: 1px solid $accent; font-weight: 600; }
    QPushButton#addTask:hover { background: $hover; }
    QLabel#taskHint, QLabel[muted="true"] { color: $muted; padding: 5px 2px; }
    QMenuBar { background: $window; color: $text; }
    QMenuBar::item:selected, QMenuBar::item:pressed { background: $hover; }
    QMenu { background: $panel; color: $text; border: 1px solid $strong_border; padding: 5px; }
    QMenu::item { padding: 8px 20px; }
    QMenu::item:selected { background: $selection; color: $selected_text; }
    QMenu::item:disabled { color: $muted; }
    QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }
    QToolTip { background: $panel; color: $text; border: 1px solid $strong_border; padding: 5px; }
    QLineEdit, QComboBox, QAbstractSpinBox { padding: 7px; border: 1px solid $border;
        border-radius: 6px; background: $base; color: $text; selection-background-color: $selection; }
    QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus { border-color: $accent; }
    QComboBox QAbstractItemView { background: $panel; color: $text;
        selection-background-color: $selection; selection-color: $selected_text; }
    QLineEdit#itemTextEditor { border: 1px solid $accent; border-radius: 0;
        color: $text; background: $base; padding: 0; }
    QTabWidget::pane { border: 1px solid $border; }
    QTabBar::tab { padding: 9px 20px; border: none; color: $muted; background: transparent; }
    QTabBar::tab:selected { color: $accent_text; border-bottom: 3px solid $accent; font-weight: 600; }
    QTabBar::tab:hover { background: $hover; }
    QWidget#inlineNote { background: $alternate; border-bottom: 1px solid $border; }
    QWidget#inlineNote QPlainTextEdit { border: 1px solid $border; border-radius: 6px; padding: 5px; background: $base; }
    QFrame#undoNotice { background: $success_bg; border: 1px solid $success_border; border-radius: 7px; }
    QFrame#colorPalette { background: $panel; border: 1px solid $strong_border; }
    QSplitter::handle { background: $border; }
    QLabel#documentTitle { font-size: 17px; font-weight: 600; padding: 5px 0; }
    QStatusBar { background: $window; color: $muted; }
    QScrollBar:vertical { background: $panel; width: 12px; margin: 0; }
    QScrollBar:horizontal { background: $panel; height: 12px; margin: 0; }
    QScrollBar::handle { background: $strong_border; border-radius: 5px; min-width: 20px; min-height: 20px; }
    QScrollBar::handle:hover { background: $muted; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QGroupBox { border: 1px solid $border; border-radius: 6px; margin-top: 12px; padding-top: 10px; }
    QGroupBox::title { color: $muted; subcontrol-origin: margin; left: 10px; }
    QProgressBar { background: $base; color: $text; border: 1px solid $border; border-radius: 4px; text-align: center; }
    QProgressBar::chunk { background: $accent; }
"""


def apply_theme(app, name="light"):
    name = name if name in ("light", "everforest") else "light"
    app.setProperty("appearanceTheme", name)
    app.setStyle("Fusion")
    # Use Qt dialogs rather than OS dialogs, whose colors are outside our control.
    app.setAttribute(Qt.AA_DontUseNativeDialogs)
    colors = EVERFOREST if name == "everforest" else LIGHT
    palette = QPalette()
    for role, token in (
        (QPalette.Window, "window"), (QPalette.WindowText, "text"), (QPalette.Base, "base"),
        (QPalette.AlternateBase, "alternate"), (QPalette.Text, "text"), (QPalette.Button, "panel"),
        (QPalette.ButtonText, "text"), (QPalette.Highlight, "selection"),
        (QPalette.HighlightedText, "selected_text"), (QPalette.ToolTipBase, "panel"),
        (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "muted"), (QPalette.Link, "accent"),
        (QPalette.LinkVisited, "accent_text"), (QPalette.Light, "hover"), (QPalette.Midlight, "panel"),
        (QPalette.Mid, "strong_border"), (QPalette.Dark, "border"), (QPalette.Shadow, "base"),
    ):
        palette.setColor(role, QColor(colors[token]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(colors["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(Template(STYLESHEET).substitute(colors))
    from app.ui.icons import refresh_icons

    for widget in app.allWidgets():
        template = widget.property("themeStyle")
        if template:
            styled(widget, template)
        refresh_icons(widget)
        if hasattr(widget, "apply_theme"):
            widget.apply_theme()
        widget.update()
