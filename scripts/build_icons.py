"""Render the shared SVG into native installer/bundle icons (no extra dependencies)."""

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1] / "app/ui/assets"


def png(size):
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    QSvgRenderer(str(ROOT / "getitdone.svg")).render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def main():
    sizes = [16, 32, 48, 64, 128, 256]
    images = [png(size) for size in sizes]
    offset = 6 + 16 * len(sizes)
    entries = []
    for size, image in zip(sizes, images):
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(image), offset))
        offset += len(image)
    (ROOT / "getitdone.ico").write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries + images))
    chunks = []
    for tag, size in [
        (b"icp4", 16),
        (b"icp5", 32),
        (b"icp6", 64),
        (b"ic07", 128),
        (b"ic08", 256),
        (b"ic09", 512),
        (b"ic10", 1024),
    ]:
        image = png(size)
        chunks.append(tag + struct.pack(">I", 8 + len(image)) + image)
    content = b"".join(chunks)
    (ROOT / "getitdone.icns").write_bytes(b"icns" + struct.pack(">I", len(content) + 8) + content)


if __name__ == "__main__":
    main()
