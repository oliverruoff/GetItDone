from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QMessageBox, QTextBrowser, QVBoxLayout, QWidget

POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="documents-context")


class Job:
    def __init__(self, function, callback, parent):
        self.callback = callback
        self.future = POOL.submit(function)
        self.timer = QTimer(parent)
        self.timer._job = self
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.collect)
        self.timer.start()

    def collect(self):
        # Only the GUI thread touches Qt objects. If the owner is destroyed,
        # its timer disappears while the plain Python future finishes safely.
        if not self.future.done():
            return
        self.timer.stop()
        try:
            result = self.future.result()
        except Exception as exc:
            self.callback(None, exc)
        else:
            self.callback(result, None)
        finally:
            self.timer._job = None
            self.timer.deleteLater()


class SafeBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.open_link)

    def loadResource(self, resource_type, url):
        # No remote images, local-file exfiltration, or automatic active resources.
        return None

    def open_link(self, url):
        if url.scheme() in ("https", "http", "mailto"):
            if (
                QMessageBox.question(self, "Open link", f"Open this link externally?\n{url.toString()}")
                == QMessageBox.Yes
            ):
                QDesktopServices.openUrl(url)


def error(parent, message):
    box = QMessageBox(QMessageBox.Warning, "GetItDone", str(message), QMessageBox.Ok, parent)
    box.setTextFormat(Qt.PlainText)
    box.exec()


def confirm(parent, title, message):
    box = QMessageBox(QMessageBox.Question, title, str(message), QMessageBox.Yes | QMessageBox.No, parent)
    box.setTextFormat(Qt.PlainText)
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes


class DismissibleDialog(QDialog):
    """Transient editors cancel when the user clicks outside them."""

    def __init__(self, parent=None):
        # Native popups dismiss on outside clicks without a Python application
        # event filter touching WebEngine's private Qt Quick objects.
        super().__init__(parent, Qt.Popup)


class TerminalPopout(QWidget):
    """Closing the window docks live terminals instead of stopping them."""

    def __init__(self, owner):
        super().__init__(owner, Qt.Window)
        self.owner = owner
        self.setWindowTitle("GetItDone · Terminals")
        self.resize(1100, 700)
        QVBoxLayout(self).setContentsMargins(4, 4, 4, 4)

    def closeEvent(self, event):
        self.owner.dock_terminals()
        event.accept()
