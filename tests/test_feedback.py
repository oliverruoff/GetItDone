import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QPushButton

from app.main import configure_style
from app.models import Notebook
from app.notifications import Notifier
from app.storage import Store
from app.ui.window import Window


@pytest.fixture
def window(qtbot, tmp_path):
    configure_style(QApplication.instance())
    store = Store(tmp_path)
    notebook = Notebook(store.load())
    notebook.add("A visible task title")
    widget = Window(store, notebook.data)
    widget.timer.stop()
    qtbot.addWidget(widget)
    widget.show()
    QApplication.processEvents()
    yield widget
    widget.timer.stop()
    widget.saver.stop()
    widget.tray.hide()
    widget.quitting = True


def test_single_click_preserves_rendered_text_and_double_click_edits(window, qtbot, monkeypatch):
    item = window.notebook.items[0]
    window.set_row_color(item["id"], ("Blue", "#3565c7"))
    row = window.tasks.rows[item["id"]]
    tree = window.tasks.tree
    rect = tree.visualItemRect(row)
    tree.clearSelection()
    tree.setCurrentItem(None)
    QApplication.processEvents()
    before = tree.viewport().grab().toImage()
    writes = []
    original_save = window.store.save
    monkeypatch.setattr(window.store, "save", lambda data: (writes.append(True), original_save(data)))
    qtbot.mouseClick(tree.viewport(), Qt.LeftButton, pos=rect.topLeft() + QPoint(100, rect.height() // 2))
    assert not tree.findChildren(QLineEdit)
    assert row.text(0) == item["text"]
    assert not writes  # Selecting an item is not an edit.
    after = tree.viewport().grab().toImage()
    # Sample empty text-cell background, independent of the inspector width / action icons.
    assert after.pixelColor(rect.left() + 300, rect.center().y()).name() == "#3565c7"

    def text_pixels(image):
        return sum(
            image.pixelColor(x, y).lightness() > 220
            for x in range(rect.left() + 40, min(rect.right() - 20, rect.left() + 280))
            for y in range(rect.top() + 9, rect.bottom() - 7)
        )

    assert text_pixels(before) > 20
    assert text_pixels(after) >= text_pixels(before) * 0.9
    qtbot.mouseDClick(tree.viewport(), Qt.LeftButton, pos=rect.topLeft() + QPoint(100, rect.height() // 2))
    qtbot.waitUntil(lambda: bool(tree.findChildren(QLineEdit)))
    assert tree.findChild(QLineEdit).text() == item["text"]


def test_text_and_actions_are_already_on_disk_without_manual_save(window, qtbot):
    window.append_item()
    editor = window.tasks.tree.findChild(QLineEdit)
    editor.selectAll()
    qtbot.keyClicks(editor, "Saved while typing")
    data = Store(window.store.folder).load()
    item = window.notebook.items[-1]
    assert next(i for i in data["items"] if i["id"] == item["id"])["text"] == "Saved while typing"
    qtbot.keyClick(editor, Qt.Key_Escape)
    window.set_row_color(item["id"], ("Green", "#3d9e50"))
    assert Store(window.store.folder).load()["items"][-1]["category_id"] == item["category_id"]
    assert window.save_status.text() == "All changes saved"


def test_notes_span_the_row_delete_without_confirmation_and_undo(window, qtbot, monkeypatch):
    item = window.notebook.items[0]
    window.tasks.toggle_note(item["id"])
    row = window.tasks.rows[item["id"]].child(0)
    assert row.isFirstColumnSpanned()
    container = window.tasks.tree.itemWidget(row, 0)
    editor = container.findChild(QPlainTextEdit)
    editor.setPlainText("A long note\nwith multiple lines")
    QApplication.processEvents()
    assert editor.width() > window.tasks.tree.columnWidth(0)
    assert Store(window.store.folder).load()["items"][0]["notes"] == editor.toPlainText()

    def unexpected(*args):
        raise AssertionError("Note deletion must not prompt")

    monkeypatch.setattr("app.ui.window.confirm", unexpected)
    trash = next(b for b in container.findChildren(QPushButton) if b.accessibleName() == "Delete note")
    qtbot.mouseClick(trash, Qt.LeftButton)
    assert not item["notes"]
    assert Store(window.store.folder).load()["items"][0]["notes"] == ""
    notice = window.tasks.undo_notices["note:" + item["id"]]
    qtbot.mouseClick(notice.findChild(QPushButton), Qt.LeftButton)
    assert item["notes"] == "A long note\nwith multiple lines"
    assert Store(window.store.folder).load()["items"][0]["notes"] == item["notes"]


def test_parent_undo_restores_mixed_descendants_and_preserves_later_text(window):
    book = window.notebook
    parent = book.items[0]
    child = book.add("Open child", parent=parent["id"])
    grandchild = book.add("Previously completed", parent=child["id"])
    book.complete(grandchild["id"], True)
    window.tasks.rebuild()
    window.complete(parent["id"], True)
    assert all(i["done"] for i in book.items)
    book.update(child["id"], text="A later edit")
    window.undo_completion(parent["id"])
    assert not parent["done"] and not child["done"] and grandchild["done"]
    assert child["text"] == "A later edit"
    stored = Store(window.store.folder).load()
    assert [i["done"] for i in stored["items"]] == [False, False, True]


def test_native_permission_state_distinguishes_banners_and_denial():
    def settings(auth, alert):
        return SimpleNamespace(authorizationStatus=lambda: auth, alertSetting=lambda: alert)

    assert Notifier.permission_message(settings(2, 2)) == (True, "Notifications allowed.")
    assert Notifier.permission_message(settings(1, 2))[0] is False
    assert "not been requested" in Notifier.permission_message(settings(0, 2))[1]
    assert "banners are disabled" in Notifier.permission_message(settings(2, 1))[1]


def test_launcher_detects_stale_bundle(tmp_path):
    from app.build_info import source_revision
    from app.launcher import bundle_current

    root = tmp_path
    (root / "app").mkdir()
    code = root / "app/main.py"
    code.write_text("first version")
    exe = root / "dist/GetItDone.app/Contents/MacOS/GetItDone"
    exe.parent.mkdir(parents=True)
    exe.write_text("executable")
    metadata = root / "dist/GetItDone.app/Contents/Frameworks/app/build-info.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({"revision": source_revision(root / "app")}))
    assert bundle_current(root)
    code.write_text("updated version")
    assert not bundle_current(root)


def test_full_title_expands_and_collapses_in_place(window, qtbot):
    item = window.notebook.items[0]
    window.notebook.update(item["id"], text="A very long task with detail " * 50)
    window.tasks.rebuild()
    tree = window.tasks.tree
    row = window.tasks.rows[item["id"]]
    collapsed = tree.visualItemRect(row).height()
    actions = tree.itemWidget(row, 4)
    expand = next(
        b for b in actions.findChildren(QPushButton) if b.accessibleName() == "Expand or collapse full title"
    )
    qtbot.mouseClick(expand, Qt.LeftButton)
    qtbot.waitUntil(lambda: tree.visualItemRect(row).height() > collapsed * 2)
    qtbot.mouseClick(expand, Qt.LeftButton)
    qtbot.waitUntil(lambda: tree.visualItemRect(row).height() == collapsed)
    assert not hasattr(window.tasks, "category")
    assert not hasattr(window.tasks, "legend")


def test_title_links_open_exact_url_and_escape_html(window, qtbot, monkeypatch):
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    from app.ui.tasks import ROLE

    item = window.notebook.items[0]
    window.notebook.update(item["id"], text="[Open task](https://example.com/task?a=1&b=2) <b>literal</b>")
    window.tasks.rebuild()
    tree = window.tasks.tree
    row = window.tasks.rows[item["id"]]
    index = tree.indexFromItem(row)
    delegate = tree.itemDelegate()
    doc = delegate.title_document(index, 600)
    assert "<b>literal</b>" in doc.toPlainText()
    opened = []
    monkeypatch.setattr("app.ui.tasks.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    option = QStyleOptionViewItem()
    option.rect = tree.visualItemRect(row)
    delegate.initStyleOption(option, index)
    rect = delegate.cell_style.subElementRect(QStyle.SE_ItemViewItemText, option, tree)
    qtbot.mouseClick(tree.viewport(), Qt.LeftButton, pos=rect.topLeft() + QPoint(12, 12))
    assert opened == ["https://example.com/task?a=1&b=2"]
    assert row.data(0, ROLE) == item["id"]


@pytest.mark.parametrize("agent", ["claude", "pi"])
def test_new_session_has_exact_native_id(agent, qtbot, tmp_path, monkeypatch):
    from uuid import UUID

    from app.ui.dialogs import SessionDialog

    monkeypatch.setattr(SessionDialog, "probe", lambda self: None)
    monkeypatch.setattr("app.agents.base.executable_path", lambda name: "/bin/" + name)
    dialog = SessionDialog({"default_agent": agent, "default_workdir": str(tmp_path)})
    qtbot.addWidget(dialog)
    dialog.check()
    assert str(UUID(dialog.native_session_id)) == dialog.native_session_id
    assert dialog.command == ["/bin/" + agent, "--session-id", dialog.native_session_id]
    assert dialog.registry[agent].command(dialog.native_session_id)[-1] == dialog.native_session_id


def test_codex_id_discovery_uses_directory_source_and_start_time(tmp_path, monkeypatch):
    from app.agents.sessions import codex_sessions

    home = tmp_path / "codex"
    logs = home / "sessions" / "2026" / "10" / "26"
    logs.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(home))
    for ident, cwd, source, timestamp in [
        ("correct", str(tmp_path), "cli", "2026-10-26T10:00:01Z"),
        ("old", str(tmp_path), "cli", "2026-10-25T10:00:01Z"),
        ("desktop", str(tmp_path), "vscode", "2026-10-26T10:00:01Z"),
        ("elsewhere", "/other/project", "cli", "2026-10-26T10:00:01Z"),
    ]:
        (logs / (ident + ".jsonl")).write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {"id": ident, "cwd": cwd, "source": source, "timestamp": timestamp},
                }
            )
            + "\n"
        )
    assert codex_sessions(tmp_path, "2026-10-26T10:00:00+00:00") == {"correct"}


def test_expanded_title_uses_multiline_editor_and_preserves_expansion(window, qtbot):
    item = window.notebook.items[0]
    window.notebook.update(item["id"], text="Long title " * 80)
    window.tasks.rebuild()
    window.tasks.toggle_title(window.tasks.rows[item["id"]])
    window.tasks.rebuild()
    row = window.tasks.rows[item["id"]]
    tree = window.tasks.tree
    tree.editItem(row, 0)
    editor = tree.findChild(QPlainTextEdit, "itemTextEditor")
    assert editor is not None
    editor.setPlainText("Updated title\nwith another line")
    assert item["text"] == editor.toPlainText()
    assert tree.visualItemRect(row).contains(editor.geometry())
    qtbot.keyClick(editor, Qt.Key_Escape)
    assert row.text(0) == "Updated title\nwith another line"


def test_codex_database_discovery(tmp_path, monkeypatch):
    import sqlite3

    from app.agents.sessions import codex_sessions

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    connection = sqlite3.connect(tmp_path / "state_5.sqlite")
    connection.execute("CREATE TABLE threads (id TEXT, created_at INTEGER, cwd TEXT, source TEXT)")
    connection.executemany(
        "INSERT INTO threads VALUES (?, ?, ?, ?)",
        [
            ("cli-id", 1793008801, str(tmp_path), "cli"),
            ("desktop-id", 1793008801, str(tmp_path), "vscode"),
        ],
    )
    connection.commit()
    connection.close()
    assert codex_sessions(tmp_path) == {"cli-id"}


def test_discovery_refuses_ambiguous_session_ownership(window, monkeypatch):
    from app.models import now_iso, uid

    sessions = [
        dict(
            id=uid(),
            item_id=window.notebook.items[0]["id"],
            agent="codex",
            native_session_id=None,
            workdir="/example",
            title="Session",
            created_at=now_iso(),
        )
        for _ in range(2)
    ]
    window.notebook.data["sessions"].extend(sessions)
    monkeypatch.setattr("app.ui.window.native_sessions", lambda *args: {"native-id"})
    window.discover_session_ids()
    assert all(s["native_session_id"] is None for s in sessions)
    window.notebook.data["sessions"].remove(sessions[1])
    window.discover_session_ids()
    assert sessions[0]["native_session_id"] == "native-id"
    assert Store(window.store.folder).load()["sessions"][0]["native_session_id"] == "native-id"


@pytest.mark.parametrize("agent", ["claude", "pi"])
def test_existing_session_id_recovery(tmp_path, monkeypatch, agent):
    from app.agents.sessions import native_sessions

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "pi"))
    root = tmp_path / agent / ("projects" if agent == "claude" else "sessions") / "project"
    root.mkdir(parents=True)
    entry = dict(
        type="session", id="pi-id", sessionId="claude-id", cwd=str(tmp_path), timestamp="2026-10-26T10:00:01Z"
    )
    (root / "example.jsonl").write_text(json.dumps(entry) + "\n")
    assert native_sessions(agent, tmp_path, "2026-10-26T10:00:00Z") == {agent + "-id"}
    assert native_sessions(agent, tmp_path, "2026-10-25T10:00:00Z") == set()
