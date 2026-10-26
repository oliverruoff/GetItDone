"""Bounded in-memory output queue and strict local-only WebEngine bridge."""

import codecs
import os
import queue
import threading
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


class Activity:
    """Streaming ECMA-48 control stripping, including split CSI/OSC sequences."""

    def __init__(self):
        self.state = "text"

    def feed(self, text):
        visible = False
        for c in text:
            if self.state == "text":
                if c == "\x1b":
                    self.state = "esc"
                elif c.isprintable() and not c.isspace():
                    visible = True
            elif self.state == "esc":
                self.state = {"[": "csi", "]": "string", "P": "string", "^": "string", "_": "string"}.get(
                    c, "text"
                )
            elif self.state == "csi":
                if "@" <= c <= "~":
                    self.state = "text"
            elif self.state == "string":
                if c == "\x07":
                    self.state = "text"
                elif c == "\x1b":
                    self.state = "string_esc"
            elif self.state == "string_esc":
                self.state = "text" if c == "\\" else "string"
        return visible


class LocalRequests(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in ("file", "qrc", "data"):
            info.block(True)


class Page(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main):
        return url.scheme() in ("file", "qrc")

    def javaScriptConsoleMessage(self, level, message, line, source):
        # Terminal output is deliberately not persisted or logged.
        pass


class Bridge(QObject):
    """Expose only the three terminal operations, never QWidget's public slots."""

    output_ready = Signal(str)

    def __init__(self, terminal):
        super().__init__(terminal)
        self.terminal = terminal
        terminal.output_ready.connect(self.output_ready.emit)

    @Slot()
    def ready(self):
        self.terminal.ready()

    @Slot(str)
    def input(self, text):
        self.terminal.input(text)

    @Slot(int, int)
    def resize_terminal(self, cols, rows):
        self.terminal.resize_terminal(cols, rows)


class Terminal(QWebEngineView):
    changed = Signal()
    output_ready = Signal(str)
    ended = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.unread = False
        self.seen = False
        self.ready_state = False
        self.ending = False
        self.disposed = False
        self.activity = Activity()
        self.pending = deque()
        self.pending_size = 0
        self.incoming = queue.Queue(maxsize=128)
        self.exited = None
        self.input_queue = queue.Queue(maxsize=128)
        # An off-the-record profile shared by terminals outlives every page.
        # Parent it to QApplication rather than a view (Qt destroys children in creation order).
        from PySide6.QtWidgets import QApplication

        application = QApplication.instance()
        if not hasattr(application, "_terminal_profile"):
            application._terminal_profile = QWebEngineProfile(application)
            application._terminal_interceptor = LocalRequests(application._terminal_profile)
            application._terminal_profile.setUrlRequestInterceptor(application._terminal_interceptor)
        self.profile = application._terminal_profile
        self.setPage(Page(self.profile, self))
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        self.channel = QWebChannel(self.page())
        self.bridge = Bridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.page().setWebChannel(self.channel)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.drain)
        self.timer.start(25)
        self.ended.connect(self.on_end)
        self.setUrl(QUrl.fromLocalFile(str(Path(__file__).parent / "web/index.html")))

    @Slot()
    def ready(self):
        self.ready_state = True
        while self.pending:
            self.output_ready.emit(self.pending.popleft())
        self.pending_size = 0

    @Slot(str)
    def input(self, text):
        if self.running:
            try:
                self.input_queue.put_nowait(text)
            except queue.Full:
                pass

    @Slot(int, int)
    def resize_terminal(self, cols, rows):
        if self.running and 1 <= cols <= 1000 and 1 <= rows <= 1000:
            try:
                self.process.resize(cols, rows)
            except OSError:
                pass

    @property
    def running(self):
        return self.process is not None and self.process.alive()

    def start(self, command, cwd):
        if not Path(cwd).is_dir():
            raise ValueError("The working directory is unavailable.")
        if os.name == "nt":
            from app.terminal.windows import Process
        else:
            from app.terminal.macos import Process
        self.process = Process(command, cwd)
        self.ending = False
        self.exited = None
        self.reader = threading.Thread(target=self.read_loop, daemon=True)
        self.writer = threading.Thread(target=self.write_loop, daemon=True)
        self.reader.start()
        self.writer.start()
        self.changed.emit()

    def read_loop(self):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                chunk = self.process.read()
                if not chunk:
                    break
                self.incoming.put(decoder.decode(chunk))
            tail = decoder.decode(b"", final=True)
            if tail:
                self.incoming.put(tail)
        except (OSError, EOFError):
            pass
        finally:
            self.exited = self.process.wait()
            self.ended.emit(self.exited)

    def write_loop(self):
        while self.running:
            try:
                text = self.input_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.process.write(text)
            except (OSError, EOFError):
                return

    def drain(self):
        chunks = []
        for _ in range(32):
            try:
                chunks.append(self.incoming.get_nowait())
            except queue.Empty:
                break
        if not chunks:
            return
        text = "".join(chunks)
        if self.activity.feed(text) and not self.seen and not self.unread:
            self.unread = True
            self.changed.emit()
        if self.ready_state:
            self.output_ready.emit(text)
        else:
            self.pending.append(text)
            self.pending_size += len(text)
            while self.pending_size > 2 * 1024 * 1024:
                self.pending_size -= len(self.pending.popleft())

    def mark_visible(self, visible):
        self.seen = visible
        if visible and self.unread:
            self.unread = False
            self.changed.emit()

    def on_end(self, code):
        self.drain()
        self.display(f"\r\n[Process ended · Exit {code}]\r\n")
        self.changed.emit()

    def display(self, text):
        if self.ready_state:
            self.output_ready.emit(text)
        else:
            self.pending.append(text)
            self.pending_size += len(text)

    def stop(self):
        if self.running and not self.ending:
            self.ending = True
            self.process.terminate()
            QTimer.singleShot(1600, self.force_stop)

    def force_stop(self):
        if self.process:
            self.process.terminate(force=True)

    def closeEvent(self, event):
        if self.running:
            event.ignore()
            return
        self.timer.stop()
        if not self.disposed:
            self.disposed = True
            self.page().deleteLater()
        event.accept()
