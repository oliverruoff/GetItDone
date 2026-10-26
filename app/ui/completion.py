"""Short completion transition using viewport snapshots, independent of tree row widgets."""

from PySide6.QtCore import QEasingCurve, QRect, Qt, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget


class CompletionOverlay(QWidget):
    def __init__(self, viewport, before, after, top, height, finished):
        super().__init__(viewport)
        self.before = before
        self.after = after
        self.top = top
        self.block_height = height
        self.progress = 0.0
        self.setGeometry(viewport.rect())
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(340)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(finished)
        self.show()
        self.raise_()
        self.animation.start()

    def advance(self, value):
        self.progress = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.after)
        # First fade the checked block, then close its gap and slide following rows up.
        fade = min(1.0, self.progress / 0.45)
        collapse = max(0.0, (self.progress - 0.25) / 0.75)
        remaining = round(self.block_height * (1 - collapse))
        painter.save()
        painter.setClipRect(QRect(0, 0, self.width(), self.top))
        painter.drawPixmap(0, 0, self.before)
        painter.restore()
        painter.save()
        painter.setClipRect(QRect(0, self.top, self.width(), remaining))
        painter.fillRect(QRect(0, self.top, self.width(), remaining), self.palette().base())
        painter.setOpacity(1 - fade)
        painter.drawPixmap(0, 0, self.before)
        painter.restore()
        painter.save()
        painter.setClipRect(QRect(0, self.top + remaining, self.width(), self.height()))
        painter.drawPixmap(0, -(self.block_height - remaining), self.before)
        painter.restore()

    def mousePressEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def dispose(self):
        self.animation.stop()
        self.hide()
        self.deleteLater()
