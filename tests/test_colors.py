from PySide6.QtGui import QColor

from app.models import Notebook
from app.storage import Store
from app.ui.colors import PALETTE, PREVIOUS_COLORS, ColorPalette, display_color, text_color
from app.ui.tasks import ROLE, Tasks
from app.ui.window import Window


def test_palette_is_modestly_stronger_and_keeps_readable_text():
    for previous, (_, current) in zip(PREVIOUS_COLORS, PALETTE, strict=True):
        old, new = QColor(previous), QColor(current)
        assert new.lightnessF() < old.lightnessF()
        assert old.lightnessF() - new.lightnessF() < 0.04
        assert abs(new.hueF() - old.hueF()) < 0.01
        assert text_color(current) == "#17202b"
        assert display_color(previous.upper()) == current
        assert display_color(current) == current
    assert display_color("#3565c7") == "#3565c7"


def test_existing_colors_render_stronger_without_changing_saved_categories(qtbot):
    book = Notebook()
    category = dict(id="custom-name", name="Keep my category name", color=PREVIOUS_COLORS[0])
    book.data["categories"].append(category)
    item = book.add("Already colored")
    book.update(item["id"], category_id=category["id"])
    tasks = Tasks(book, {})
    qtbot.addWidget(tasks)
    tasks.show()
    row = tasks.rows[item["id"]]
    assert row.data(0, ROLE + 2).name() == PALETTE[0][1]
    assert category["color"] == PREVIOUS_COLORS[0]
    assert category["name"] == "Keep my category name"
    assert not tasks.tree.viewport().grab().isNull()
    palette = ColorPalette(category["color"])
    qtbot.addWidget(palette)
    assert palette.swatches[0].text() == "✓"


def test_selecting_updated_palette_reuses_existing_category(qtbot, tmp_path):
    store = Store(tmp_path)
    book = Notebook(store.load())
    category = dict(id="existing", name="Existing custom name", color=PREVIOUS_COLORS[0])
    book.data["categories"].append(category)
    item = book.add("Todo")
    window = Window(store, book.data)
    qtbot.addWidget(window)
    try:
        window.set_row_color(item["id"], PALETTE[0])
        assert item["category_id"] == category["id"]
        assert book.data["categories"] == [category]
        assert category["name"] == "Existing custom name"
    finally:
        window.timer.stop()
        window.tray.hide()
        window.quitting = True
