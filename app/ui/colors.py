"""One-click row colors. Existing custom category names and IDs remain intact."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QToolButton, QVBoxLayout

PALETTE = (
    ("Red", "#f6cccc"),
    ("Orange", "#f8dcc4"),
    ("Amber", "#f7e5bc"),
    ("Yellow", "#faf0bd"),
    ("Lime", "#e6edc3"),
    ("Green", "#d1ead3"),
    ("Emerald", "#c6e6d9"),
    ("Teal", "#c9e8e3"),
    ("Cyan", "#ceeef3"),
    ("Sky", "#d3e7fa"),
    ("Blue", "#d1dcf5"),
    ("Indigo", "#dcd5f0"),
    ("Violet", "#e7d4f1"),
    ("Magenta", "#f0d0e5"),
    ("Rose", "#f6dce2"),
    ("Slate", "#dfe5ec"),
)


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
        self.setStyleSheet("QFrame#colorPalette { background: #ffffff; border: 1px solid #a6b3c2; }")
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
            button.setText("✓" if color.lower() == (current or "").lower() else "")
            button.setStyleSheet(
                f"QToolButton {{ background: {color}; color: {text_color(color)}; "
                "border: 1px solid #7b8898; border-radius: 3px; font-weight: bold; }"
                "QToolButton:hover, QToolButton:focus { border: 3px solid #17202b; }"
            )
            button.clicked.connect(lambda checked=False, value=(name, color): self.choose(value))
            grid.addWidget(button, n // 4, n % 4)
            self.swatches.append(button)
        layout.addLayout(grid)
        clear = QPushButton("No color")
        clear.clicked.connect(lambda: self.choose(None))
        layout.addWidget(clear)

    def choose(self, value):
        self.close()
        self.selected.emit(value)
