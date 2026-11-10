"""Entry point; --data-dir allows an isolated test notebook."""

import argparse
import sys
from pathlib import Path


def configure_style(app, theme="light"):
    from app.ui.theme import apply_theme

    apply_theme(app, theme)


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
    if sys.platform == "win32":
        from app.notifications.windows import set_process_identity

        try:
            set_process_identity()
        except OSError:
            import logging

            logging.exception("Could not configure Windows taskbar identity")
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedKingdom))
    QApplication.setOrganizationName("GetItDone")
    QApplication.setApplicationName("GetItDone")
    app = QApplication(sys.argv[:1])
    from PySide6.QtGui import QIcon

    icon_name = "getitdone.ico" if sys.platform == "win32" else "getitdone.svg"
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui/assets" / icon_name)))
    app.setQuitOnLastWindowClosed(False)
    folder = args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    try:
        store = Store(folder)
        lock = QLockFile(str(store.folder / "instance.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            from app.instance import request

            status = request(folder, "status")
            # A normal launch only opens the existing notebook. Source edits
            # must not silently stop its agents or initiate a version handover.
            if status and not args.replace_running:
                if status.get("status") == "stopping":
                    raise StorageError("GetItDone is still stopping its sessions. Please wait before reopening it.")
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
    configure_style(app, data["settings"].get("theme", "light"))
    if store.recovery_notice:
        box = QMessageBox(QMessageBox.Warning, "GetItDone · Notebook recovered", store.recovery_notice)
        box.setTextFormat(Qt.PlainText)
        box.exec()
    from app.ui.window import Window

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
