"""Small native-rendered line icons; accessible button names remain explicit."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton

PATHS = {
    "maximize": '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
    "restore": '<rect x="3" y="7" width="14" height="14"/><path d="M7 7V3h14v14h-4"/>',
    "dock": '<rect x="3" y="3" width="18" height="18"/><path d="M3 14h18m-9-9v7m-3-3 3 3 3-3"/>',
    "expand": '<path d="m7 8 5-5 5 5M12 3v18m-5-5 5 5 5-5"/>',
    "trash": '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    "note": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    "session": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m6 9 3 3-3 3m6 0h5"/>',
    "more": '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
    "bell": '<path d="M5 16h14l-2-3V9a5 5 0 0 0-10 0v4zM10 20h4M12 2v2"/>',
    "play": '<path d="m8 4 12 8-12 8z"/>',
    "folder": '<path d="M3 6h7l2 3h9v11H3zM3 6V4h7l2 2h8v3"/>',
    "refresh": '<path d="M20 7a9 9 0 1 0 1 8M20 2v6h-6"/>',
    "save": '<path d="M4 3h13l3 3v15H4zM8 3v6h8V3M8 21v-8h8v8"/>',
    "external": '<path d="M14 3h7v7M21 3l-11 11M10 4H3v17h17v-7"/>',
    "copy": '<rect x="8" y="8" width="13" height="13" rx="1"/><path d="M16 8V3H3v13h5"/>',
    "paste": '<path d="M8 5H4v16h16V5h-4M8 3h8v5H8z"/>',
}


def icon(name, color="#34445b"):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return QIcon(pixmap)


def icon_button(name, label, callback, color="#34445b"):
    button = QPushButton()
    button.setIcon(icon(name, color))
    button.setAccessibleName(label)
    button.setToolTip(label)
    button.setFixedSize(32, 28)
    button.clicked.connect(callback)
    return button
