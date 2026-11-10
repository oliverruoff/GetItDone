"""One-click row colors. Existing custom category names and IDs remain intact."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QToolButton, QVBoxLayout

from app.ui.theme import color as theme_color
from app.ui.theme import row_color, styled

PALETTE = (
    ("Red", "#f4c2c2"),
    ("Orange", "#f7d5b8"),
    ("Amber", "#f5e0af"),
    ("Yellow", "#f9edb0"),
    ("Lime", "#e1e9b7"),
    ("Green", "#c8e6ca"),
    ("Emerald", "#bbe1d1"),
    ("Teal", "#bee3dd"),
    ("Cyan", "#c4ebf1"),
    ("Sky", "#cae2f9"),
    ("Blue", "#c8d5f3"),
    ("Indigo", "#d5cded"),
    ("Violet", "#e2cbee"),
    ("Magenta", "#edc7e0"),
    ("Rose", "#f4d5dc"),
    ("Slate", "#d9e0e8"),
)

# Display older palette assignments consistently without rewriting saved categories.
PREVIOUS_COLORS = (
    "#f6cccc", "#f8dcc4", "#f7e5bc", "#faf0bd", "#e6edc3", "#d1ead3", "#c6e6d9", "#c9e8e3",
    "#ceeef3", "#d3e7fa", "#d1dcf5", "#dcd5f0", "#e7d4f1", "#f0d0e5", "#f6dce2", "#dfe5ec",
)
_DISPLAY_COLORS = dict(zip(PREVIOUS_COLORS, (color for _, color in PALETTE), strict=True))


def display_color(color):
    return _DISPLAY_COLORS.get(color.lower(), color)


def text_color(background):
    color = QColor(background)
    # WCAG relative luminance: use the higher-contrast of black and white.
    channels = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in (color.redF(), color.greenF(), color.blueF())
    ]
    luminance = sum(a * b for a, b in zip(channels, (0.2126, 0.7152, 0.0722)))
    return "#ffffff" if (luminance + 0.05) ** 2 < 0.0525 else "#17202b"


class ColorPalette(QFrame):
    selected = Signal(object)

    def __init__(self, current=None, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("colorPalette")
        self.setWindowTitle("Row color")
        styled(self, "QFrame#colorPalette { background: $panel; border: 1px solid $strong_border; }")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Row color"))
        grid = QGridLayout()
        grid.setSpacing(6)
        self.swatches = []
        for n, (name, color) in enumerate(PALETTE):
            button = QToolButton()
            button.setFixedSize(34, 34)
            button.setAccessibleName(name)
            button.setToolTip(name)
            button.setProperty("color", color)
            button.setText("✓" if color.lower() == display_color(current or "").lower() else "")
            button.clicked.connect(lambda checked=False, value=(name, color): self.choose(value))
            grid.addWidget(button, n // 4, n % 4)
            self.swatches.append(button)
        layout.addLayout(grid)
        clear = QPushButton("No color")
        clear.clicked.connect(lambda: self.choose(None))
        layout.addWidget(clear)
        self.apply_theme()

    def apply_theme(self):
        for button in self.swatches:
            tint = row_color(button.property("color"))
            button.setStyleSheet(
                f"QToolButton {{ background: {tint}; color: {text_color(tint)}; "
                f"border: 1px solid {theme_color('strong_border')}; border-radius: 3px; font-weight: bold; }}"
                f"QToolButton:hover, QToolButton:focus {{ border: 3px solid {theme_color('accent')}; }}"
            )

    def choose(self, value):
        self.close()
        self.selected.emit(value)
