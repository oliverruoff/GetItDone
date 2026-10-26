from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QTextBrowser

POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="documents-context")


class Job(QObject):
    finished = Signal(object, object)

    def __init__(self, function, callback, parent):
        super().__init__(parent)
        self.finished.connect(callback)
        self.finished.connect(self.deleteLater)
        self.future = POOL.submit(function)
        self.future.add_done_callback(self.done)

    def done(self, future):
        try:
            result = future.result()
        except Exception as exc:
            try:
                self.finished.emit(None, exc)
            except RuntimeError:
                pass  # The owning dialog was closed while the worker finished.
        else:
            try:
                self.finished.emit(result, None)
            except RuntimeError:
                pass


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
