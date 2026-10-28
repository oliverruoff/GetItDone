"""Entry point; --data-dir allows an isolated test notebook."""

import argparse
import sys
from pathlib import Path


def configure_style(app):
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in (
        (QPalette.Window, "#f4f5f7"),
        (QPalette.WindowText, "#243247"),
        (QPalette.Base, "#ffffff"),
        (QPalette.AlternateBase, "#f7f9fb"),
        (QPalette.Text, "#243247"),
        (QPalette.Button, "#edf0f4"),
        (QPalette.ButtonText, "#243247"),
        (QPalette.Highlight, "#dce9f7"),
        (QPalette.HighlightedText, "#172b43"),
        (QPalette.ToolTipBase, "#ffffff"),
        (QPalette.ToolTipText, "#243247"),
        (QPalette.PlaceholderText, "#6e7b8e"),
        (QPalette.Light, "#ffffff"),
        (QPalette.Midlight, "#e5e9ef"),
        (QPalette.Mid, "#9ba7b5"),
        (QPalette.Dark, "#687789"),
        (QPalette.Shadow, "#4a5869"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet("""
        QMainWindow, QWidget { font-size: 13px; }
        QMainWindow { background: #f6f8fc; }
        QToolBar { background: #edf0f4; border-bottom: 1px solid #c8ced6; spacing: 3px; padding: 5px; }
        QToolButton { padding: 6px 7px; }
        QTreeWidget, QListWidget, QPlainTextEdit, QTextBrowser { background: white; alternate-background-color: #f7f9fb; border: 1px solid #cbd1d9; selection-background-color: #dce9f7; selection-color: #172b43; }
        QTreeWidget::item { min-height: 24px; border-bottom: 1px solid #e5e9ee; }
        QHeaderView::section { background: #ffffff; color: #52647e; border: none; border-bottom: 1px solid #dce3ed; padding: 6px; font-weight: 500; }
        QPushButton { padding: 6px 10px; background: #ffffff; border: 1px solid #d3dce8; border-radius: 6px; color: #294662; }
        QPushButton:hover { background: #eaf2fc; border-color: #4b78a6; }
        QPushButton:pressed { background: #d5e5f7; }
        QPushButton:focus { border: 2px solid #355d84; }
        QTreeWidget#taskTree::item { min-height: 24px; }
        QTreeWidget#taskTree QPushButton { padding: 2px 8px; }
        QPushButton#addTask { text-align: left; padding-left: 18px; background: #edf5ff; color: #224f80; border: 1px solid #90afd0; font-weight: 600; }
        QPushButton#addTask:hover { background: #dcecff; }
        QLabel#taskHint { color: #526276; padding: 5px 2px; }
        QMenu { background: white; border: 1px solid #bbc8d7; padding: 5px; }
        QMenu::item { padding: 8px 20px; }
        QMenu::item:selected { background: #eaf2fc; }
        QLineEdit, QComboBox { padding: 7px; border: 1px solid #d6dfeb; border-radius: 6px; background: #ffffff; }
        QLineEdit#itemTextEditor { border: 1px solid #769bc7; border-radius: 0px; color: #172b43; background: #ffffff; padding: 0px; }
        QTabBar::tab { padding: 9px 20px; border: none; color: #64738b; background: transparent; }
        QTabBar::tab:selected { color: #23588b; border-bottom: 3px solid #3b75b0; font-weight: 600; }
        QWidget#inlineNote { background: #f8faff; border-bottom: 1px solid #dfe6f0; }
        QWidget#inlineNote QPlainTextEdit { border: 1px solid #dfe6f0; border-radius: 6px; padding: 5px; background: #ffffff; }
        QFrame#undoNotice { background: #edf7f2; border: 1px solid #b4d6c6; border-radius: 7px; }
        QSplitter::handle { background: #e0e4e9; }
        QLabel#documentTitle { font-size: 17px; font-weight: 600; padding: 5px 0; }
        QStatusBar { color: #526276; }
    """)
    assets = Path(__file__).parent / "ui/assets"
    app.setStyleSheet(
        app.styleSheet()
        + f'''
        QTreeWidget::indicator {{ width: 20px; height: 20px; }}
        QTreeWidget::indicator:unchecked {{ image: url("{(assets / "unchecked.svg").as_posix()}"); }}
        QTreeWidget::indicator:checked {{ image: url("{(assets / "checked.svg").as_posix()}"); }}
    '''
    )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--terminal-probe":
        import os

        print("PTY_READY", os.isatty(0), flush=True)
        value = input()
        print("PTY_ECHO:" + value, flush=True)
        return 0
    # Frozen PTY helper must dispatch before Qt or WebEngine are imported.
    if len(sys.argv) > 1 and sys.argv[1] == "--pty-child":
        sys.argv.pop(1)
        from app.terminal.child import main as child_main

        child_main()
        return
    from PySide6.QtCore import QLocale, QLockFile, QStandardPaths, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.storage import StorageError, Store

    parser = argparse.ArgumentParser(description="GetItDone · Local notebook")
    from app.build_info import revision

    loaded_revision = revision()
    parser.add_argument("--version", action="version", version="GetItDone 0.1.0 · Build " + loaded_revision)
    parser.add_argument(
        "--replace-running",
        action="store_true",
        help="Save and replace the running instance with this version",
    )
    parser.add_argument("--data-dir", type=Path, help="Use a different local data directory")
    parser.add_argument("--smoke", action="store_true", help="Start and quit safely after 3 seconds")
    parser.add_argument(
        "--test-notification",
        action="store_true",
        help="Send a real system notification, report the OS result and quit",
    )
    parser.add_argument(
        "--smoke-terminal",
        action="store_true",
        help="Also test the integrated terminal using a local test process",
    )
    args = parser.parse_args()
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedKingdom))
    QApplication.setOrganizationName("GetItDone")
    QApplication.setApplicationName("GetItDone")
    app = QApplication(sys.argv[:1])
    from PySide6.QtGui import QIcon

    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui/assets/getitdone.svg")))
    app.setQuitOnLastWindowClosed(False)
    folder = args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    try:
        store = Store(folder)
        lock = QLockFile(str(store.folder / "instance.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            from app.instance import request

            status = request(folder, "status")
            if status and not args.replace_running and status.get("revision") == loaded_revision:
                request(folder, "activate")
                return 0
            response = request(folder, "replace") if status else None
            if response and response.get("status") == "cancelled":
                return 0
            if not response or response.get("status") != "replacing":
                raise StorageError(
                    f"An older instance is running without restart support. Please quit it using its Quit action.\n{folder}"
                )
            if not lock.tryLock(15000):
                raise StorageError(
                    "The previous instance has not finished shutting down. No second instance was opened."
                )
        data = store.load()
    except (StorageError, OSError) as exc:
        box = QMessageBox(QMessageBox.Critical, "GetItDone · Unable to start", str(exc))
        box.setTextFormat(Qt.PlainText)
        box.exec()
        return 1
    if store.recovery_notice:
        box = QMessageBox(QMessageBox.Warning, "GetItDone · Notebook recovered", store.recovery_notice)
        box.setTextFormat(Qt.PlainText)
        box.exec()
    from app.ui.window import Window

    configure_style(app)
    window = Window(store, data)
    from app.instance import InstanceServer

    instance = InstanceServer(folder, window, loaded_revision, app)
    watcher = None
    if getattr(sys, "frozen", False):
        from app.instance import BuildActivationWatcher

        watcher = BuildActivationWatcher(app, window, loaded_revision, revision)
    window.setWindowTitle(window.windowTitle() + " · Build " + loaded_revision[:8])
    window.show()
    if args.test_notification:
        import json

        from PySide6.QtCore import QTimer

        def reported(ident, accepted, detail):
            print("NOTIFICATION_RESULT " + json.dumps({"accepted": accepted, "detail": detail}), flush=True)
            if accepted and window.notifier.center:

                def inspect_delivered():
                    window.notifier.center.getDeliveredNotificationsWithCompletionHandler_(
                        lambda notifications: print(
                            "NOTIFICATION_IN_SYSTEM_CENTER "
                            + str(
                                any(str(n.request().identifier()) == "getitdone-test" for n in notifications)
                            ),
                            flush=True,
                        )
                    )

                QTimer.singleShot(800, inspect_delivered)
            QTimer.singleShot(1500, window.quit_app)

        window.notifier.native_result.connect(reported)
        permission_wait = QTimer(window)
        permission_wait.setInterval(300)

        def test_ready():
            if window.notifier.status.startswith("Checking"):
                return
            permission_wait.stop()
            window.test_notification()

        permission_wait.timeout.connect(test_ready)
        permission_wait.start()
        QTimer.singleShot(45000, window.quit_app)
    terminal_smoke = {"ok": False, "sent": False, "output": ""}
    if args.smoke_terminal:
        from app.terminal.bridge import Terminal

        terminal = Terminal(window)
        window.terminals["smoke"] = terminal
        window.tabs.addTab(terminal, "Terminal check")

        def probe_output(text):
            terminal_smoke["output"] += text
            if "PTY_READY True" in terminal_smoke["output"] and not terminal_smoke["sent"]:
                terminal_smoke["sent"] = True
                terminal.input("smoke\r")
            if "PTY_ECHO:smoke" in terminal_smoke["output"]:
                terminal_smoke["ok"] = True

        terminal.output_ready.connect(probe_output)
        command = (
            [sys.executable, "--terminal-probe"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "app", "--terminal-probe"]
        )
        terminal.start(command, str(Path.cwd()))
    if args.smoke or args.smoke_terminal:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(8000 if args.smoke_terminal else 3000, window.quit_app)
    result = app.exec()
    instance.close()
    lock.unlock()
    if watcher and watcher.restart:
        import os
        import subprocess

        subprocess.Popen(
            [sys.executable, *sys.argv[1:]], env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        )
    if args.smoke_terminal:
        print("TERMINAL_SMOKE_OK" if terminal_smoke["ok"] else "TERMINAL_SMOKE_FAILED")
        return 0 if terminal_smoke["ok"] else 2
    return result


if __name__ == "__main__":
    sys.exit(main())
