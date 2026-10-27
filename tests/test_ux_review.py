from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

from app.models import Notebook
from app.storage import Store
from app.ui.window import Window


def test_expanded_title_newline_and_cancel_empty_draft(qtbot, tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    item = book.add('Existing title')
    window = Window(store, book.data)
    qtbot.addWidget(window)
    window.show()
    try:
        window.tasks.toggle_title(window.tasks.rows[item['id']])
        window.tasks.tree.editItem(window.tasks.rows[item['id']], 0)
        editor = window.tasks.tree.findChild(QPlainTextEdit)
        editor.selectAll()
        qtbot.keyClicks(editor, 'First line')
        qtbot.keyClick(editor, Qt.Key_Return, Qt.ShiftModifier)
        qtbot.keyClicks(editor, 'Second line')
        assert item['text'] == 'First line\nSecond line'
        assert len(book.items) == 1
        qtbot.keyClick(editor, Qt.Key_Return)
        qtbot.waitUntil(lambda: len(book.items) == 2)
        next_editor = window.tasks.tree.findChild(QLineEdit)
        qtbot.keyClick(next_editor, Qt.Key_Escape)
        qtbot.waitUntil(lambda: len(book.items) == 1)
        assert len(Store(tmp_path).load()['items']) == 1
        # An existing blank task with notes must never be discarded.
        book.update(item['id'], text='', notes='Keep this')
        window.discard_empty_draft(item['id'])
        assert book.get(item['id']) is not None
        scheduled = window.scheduled
        assert not scheduled.actions['Run now'].isEnabled()
        assert not scheduled.actions['Stop running job'].isEnabled()
        assert not scheduled.pause.isEnabled()
    finally:
        window.timer.stop()
        window.scheduler.shutdown()
        window.saver.stop()
        window.tray.hide()
        window.quitting = True
        window.close()
