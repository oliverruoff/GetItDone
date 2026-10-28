from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.knowledge import (
    DOCUMENT_LIMIT,
    DocumentError,
    TextDocument,
    create_note,
    docx_html,
    list_documents,
)
from app.ui.common import Job, SafeBrowser, error
from app.ui.icons import icon, icon_button


class NewNote(QDialog):
    def __init__(self, parent, content=""):
        super().__init__(parent)
        self.setWindowTitle("New note · UTF-8 text file")
        self.resize(600, 420)
        layout = QFormLayout(self)
        self.title = QLineEdit(datetime.now().strftime("Note_%Y-%m-%d_%H-%M"))
        self.extension = QComboBox()
        self.extension.addItems([".txt", ".md"])
        self.title.setPlaceholderText("Title = filename without extension")
        self.content = QPlainTextEdit(content)
        self.content.installEventFilter(self)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        title_row = QHBoxLayout()
        title_row.addWidget(self.title, 1)
        title_row.addWidget(self.extension)
        layout.addRow("Title", title_row)
        layout.addRow("Text", self.content)
        layout.addRow(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.document = None
        self.content.setPlaceholderText("Write a note · Enter: save · Shift+Enter: new line")
        self.content.setFocus()

    def eventFilter(self, watched, event):
        if (watched is self.content and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and not event.modifiers() & Qt.ShiftModifier):
            self.save()
            return True
        return super().eventFilter(watched, event)

    def save(self):
        try:
            self.document = create_note(self.parent().folder, self.title.text(), self.content.toPlainText(),
                                        self.extension.currentText())
            self.accept()
        except (DocumentError, OSError) as exc:
            self.problem.setText(str(exc))


class Knowledge(QWidget):
    settings_changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.folder = settings.get("knowledge_folder", "")
        self.document = None
        self.current_path = None
        self.dirty = False
        self.loading = False
        self.generation = 0
        self.auto_error = False
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.toolbar_buttons = []
        for name, title, handler in [
            ("folder", "Choose folder", self.choose_folder),
            ("note", "New note", self.new_note),
            ("refresh", "Refresh", self.refresh),
            ("save", "Save", self.save_clicked),
            ("copy", "Save as new note", self.save_copy),
            ("external", "Open externally", self.open_external),
            ("trash", "Delete file", self.delete_file),
        ]:
            if name in ("folder", "note", "copy", "external"):
                button = QPushButton(icon(name), title)
                button.clicked.connect(handler)
            else:
                button = icon_button(name, title, handler)
            toolbar.addWidget(button)
            self.toolbar_buttons.append(button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search filenames …")
        self.search.textChanged.connect(self.filter_list)
        toolbar.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.addItem("Name · A–Z", "name")
        self.sort.addItem("Modified · newest first", "modified")
        self.sort.setCurrentIndex(max(0, self.sort.findData(settings.get("knowledge_sort", "name"))))
        self.sort.currentIndexChanged.connect(self.sort_changed)
        toolbar.addWidget(self.sort)
        layout.addLayout(toolbar)
        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)
        self.empty_folder = QPushButton(icon("folder"), "Choose your knowledge folder …")
        self.empty_folder.clicked.connect(self.choose_folder)
        self.empty_panel = QWidget()
        empty_layout = QVBoxLayout(self.empty_panel)
        empty_layout.addStretch()
        empty_title = QLabel("Keep your knowledge close at hand")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_hint = QLabel("Choose a local folder for notes and reference documents.")
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_hint)
        empty_layout.addWidget(self.empty_folder, 0, Qt.AlignCenter)
        empty_layout.addStretch()
        layout.addWidget(self.empty_panel, 1)
        self.splitter = QSplitter()
        self.files = QListWidget()
        self.files.setMinimumWidth(140)
        self.files.currentItemChanged.connect(self.select_file)
        self.splitter.addWidget(self.files)
        content = QWidget()
        right = QVBoxLayout(content)
        self.title = QLineEdit("Knowledge · Local documents")
        self.title.setReadOnly(True)
        self.title.editingFinished.connect(self.rename_note)
        self.title.setObjectName("documentTitle")
        right.addWidget(self.title)
        self.status = QLabel("Please select a local folder.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        right.addWidget(self.status)
        self.stack = QStackedWidget()
        self.placeholder = QLabel("Select a document or create a new text note.")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Note text …")
        self.editor.textChanged.connect(self.edited)
        self.browser = SafeBrowser()
        self.pdf_document = QPdfDocument(self)
        self.pdf = QPdfView()
        self.pdf.setDocument(self.pdf_document)
        self.pdf.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.pdf_document.statusChanged.connect(self.pdf_status)
        self.pdf.pageNavigator().currentPageChanged.connect(self.pdf_page)
        for widget in (self.placeholder, self.editor, self.browser, self.pdf):
            self.stack.addWidget(widget)
        right.addWidget(self.stack, 1)
        self.splitter.addWidget(content)
        self.splitter.setSizes([240, 900])
        layout.addWidget(self.splitter, 1)
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(700)
        self.autosave.timeout.connect(self.save_auto)
        self.refresh(initial=True)

    def choose_folder(self):
        if not self.guard():
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose knowledge folder", self.folder)
        if folder:
            self.folder = folder
            self.settings["knowledge_folder"] = folder
            self.settings["knowledge_last_file"] = ""
            self.settings_changed.emit()
            self.clear_document()
            self.refresh()

    def clear_document(self):
        self.generation += 1
        self.document = None
        self.current_path = None
        self.dirty = False
        self.autosave.stop()
        self.pdf_document.close()
        self.stack.setCurrentWidget(self.placeholder)
        self.title.setText("Knowledge · Local documents")
        self.title.setReadOnly(True)

    def sort_changed(self):
        self.settings["knowledge_sort"] = self.sort.currentData()
        self.settings_changed.emit()
        self.refresh()

    def rename_note(self):
        if not self.document or self.title.isReadOnly():
            return
        if self.title.text() == self.document.path.stem:
            return
        try:
            if not self.save(interactive=True):
                return
            self.document.rename(self.title.text())
            self.current_path = self.document.path
            self.settings["knowledge_last_file"] = self.current_path.name
            self.settings_changed.emit()
            self.refresh(preserve_document=True)
        except DocumentError as exc:
            error(self, exc)
            self.title.setText(self.document.path.stem)

    def delete_file(self):
        path = self.current_path
        if path is None or not self.guard():
            return
        box = QMessageBox(QMessageBox.Warning, "Delete file",
                          f'Permanently delete "{path.name}" from disk? This cannot be undone.',
                          QMessageBox.Yes | QMessageBox.Cancel, self)
        box.setTextFormat(Qt.PlainText)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return
        self.pdf_document.close()
        try:
            path.unlink()
        except OSError as exc:
            error(self, exc)
            return
        self.settings["knowledge_last_file"] = ""
        self.settings_changed.emit()
        self.clear_document()
        self.refresh()

    def refresh(self, checked=False, initial=False, preserve_document=False):
        if not initial and not self.guard():
            return
        selected = (
            self.current_path.name if self.current_path else self.settings.get("knowledge_last_file", "")
        )
        self.empty_panel.setVisible(not bool(self.folder))
        self.path_label.setVisible(bool(self.folder))
        self.search.setVisible(bool(self.folder))
        for button in self.toolbar_buttons:
            button.setVisible(bool(self.folder))
        self.splitter.setVisible(bool(self.folder))
        self.path_label.setText(f"Folder: {self.folder}" if self.folder else "No knowledge folder selected")
        try:
            paths = list_documents(self.folder, self.sort.currentData()) if self.folder else []
        except DocumentError as exc:
            self.files.blockSignals(True)
            self.files.clear()
            self.files.blockSignals(False)
            self.clear_document()
            self.status.setText(str(exc))
            return
        self.files.blockSignals(True)
        self.files.clear()
        chosen = None
        for path in paths:
            row = QListWidgetItem(f"{path.stem}   {path.suffix.upper().lstrip('.')}")
            row.setData(Qt.UserRole, str(path))
            row.setToolTip(path.name)
            self.files.addItem(row)
            if path.name == selected:
                chosen = row
        self.files.blockSignals(False)
        self.filter_list()
        if chosen:
            self.files.blockSignals(preserve_document)
            self.files.setCurrentItem(chosen)
            self.files.blockSignals(False)
        else:
            self.clear_document()
            self.status.setText(
                "No supported documents in this folder."
                if self.folder and not paths
                else "Select a document."
                if self.folder
                else "Please select a local folder."
            )

    def filter_list(self):
        query = self.search.text().casefold()
        for n in range(self.files.count()):
            row = self.files.item(n)
            row.setHidden(query not in Path(row.data(Qt.UserRole)).name.casefold())

    def select_file(self, row, previous):
        if not row:
            return
        path = Path(row.data(Qt.UserRole))
        if not self.guard():
            self.files.blockSignals(True)
            self.files.setCurrentItem(previous)
            self.files.blockSignals(False)
            return
        self.clear_document()
        self.current_path = path
        self.settings["knowledge_last_file"] = path.name
        self.settings_changed.emit()
        self.title.setText(f"{path.stem} · {path.suffix.upper().lstrip('.')}")
        self.status.setText("Loading document …")
        generation = self.generation
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                if path.stat().st_size > DOCUMENT_LIMIT:
                    raise DocumentError("The PDF is too large (150 MB maximum). Please open it externally.")
                result = self.pdf_document.load(str(path))
                if result != QPdfDocument.Error.None_:
                    raise DocumentError(
                        "The PDF is protected, damaged or unreadable. You can open it externally."
                    )
                self.stack.setCurrentWidget(self.pdf)
                self.pdf_page(0)
            except (OSError, DocumentError) as exc:
                self.status.setText(str(exc))
        elif suffix == ".doc":
            self.status.setText(
                "The older DOC format has no reliable integrated preview. Please use Open externally."
            )
        else:

            def load():
                if suffix == ".docx":
                    return docx_html(path)
                return TextDocument.open(path)

            def loaded(result, exc):
                if generation != self.generation:
                    return
                if exc:
                    self.status.setText(str(exc))
                    return
                if suffix in (".txt", ".md", ".markdown"):
                    self.document = result
                    self.title.setText(path.stem)
                    self.title.setReadOnly(False)
                    self.loading = True
                    self.editor.setPlainText(result.text)
                    self.loading = False
                    self.stack.setCurrentWidget(self.editor)
                    self.status.setText("Saved · Title and text are editable; text saves automatically")
                else:
                    self.browser.setHtml(result)
                    self.stack.setCurrentWidget(self.browser)
                    self.status.setText("Read-only preview · The local file is unchanged")

            Job(load, loaded, self)

    def pdf_status(self, status):
        if self.current_path and self.current_path.suffix.lower() == ".pdf":
            if status == QPdfDocument.Status.Error:
                self.status.setText("Unable to display the PDF (it may be password-protected or damaged).")
            elif status == QPdfDocument.Status.Ready:
                self.pdf_page(0)

    def pdf_page(self, page):
        if self.pdf_document.pageCount():
            self.status.setText(f"Page {page + 1} of {self.pdf_document.pageCount()} · read-only")

    def edited(self):
        if self.loading or not self.document:
            return
        self.dirty = self.editor.toPlainText() != self.document.text
        self.auto_error = False
        self.status.setText("Unsaved changes" if self.dirty else "Saved")
        self.autosave.start()

    def save(self, interactive=False):
        self.autosave.stop()
        if not self.dirty or not self.document:
            return True
        try:
            self.document.save(self.editor.toPlainText())
            self.dirty = False
            self.status.setText("Saved")
            return True
        except DocumentError as exc:
            self.status.setText(f"NOT SAVED · {exc}")
            if interactive:
                error(self, exc)
            return False

    def save_auto(self):
        self.save()

    def save_clicked(self):
        self.save(interactive=True)

    def guard(self):
        if self.save():
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText("Saving failed. Your text remains in the editor. How would you like to proceed?")
        copy = box.addButton("Save as new note", QMessageBox.AcceptRole)
        discard = box.addButton("Discard changes", QMessageBox.DestructiveRole)
        cancel = box.addButton("Back to editor", QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() == copy:
            return self.save_copy()
        if box.clickedButton() == discard:
            self.dirty = False
            return True
        return False

    def new_note(self):
        if not self.guard():
            return
        if not self.folder or not Path(self.folder).is_dir():
            error(self, "Please select an available knowledge folder first.")
            return
        self.search.clear()
        dialog = NewNote(self)
        if dialog.exec():
            self.settings["knowledge_last_file"] = dialog.document.path.name
            self.clear_document()
            self.refresh()

    def save_copy(self):
        dialog = NewNote(self, self.editor.toPlainText() if self.document else "")
        if dialog.exec():
            self.dirty = False
            self.settings["knowledge_last_file"] = dialog.document.path.name
            self.clear_document()
            self.refresh()
            return True
        return False

    def open_external(self):
        if self.current_path and self.guard():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_path)))
