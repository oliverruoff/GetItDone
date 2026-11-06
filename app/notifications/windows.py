"""Native Windows toasts with a stable, per-user application identity."""

from pathlib import Path

APP_ID = "de.getitdone.notebook"


def register():
    import ctypes
    import winreg

    icon = Path(__file__).resolve().parents[1] / "ui/assets/getitdone.ico"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "GetItDone")
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon))
    result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    if result:
        raise OSError("Windows could not set the GetItDone application identity.")


class WindowsNotifications:
    def __init__(self):
        register()
        self.toaster = create_toaster()

    def close(self):
        self.toaster.close()

    def send(self, item, activated, failed):
        from windows_toasts import Toast
        from winrt.windows.ui.notifications import NotificationSetting

        try:
            setting = self.toaster.toastNotifier.setting
        except OSError as exc:
            # Unpackaged registry-registered senders can submit toasts even though
            # get_Setting returns HRESULT_FROM_WIN32(ERROR_NOT_FOUND).
            if getattr(exc, "winerror", None) not in (-2147023728, 2147943568):
                raise
            setting = None
        if setting is not None and setting != NotificationSetting.ENABLED:
            raise OSError(
                "Windows notifications are disabled for GetItDone or by system policy. "
                "Enable them in Settings → System → Notifications."
            )
        toast = Toast()
        toast.text_fields = [item.get("notification_title", "GetItDone · Reminder"), item["text"]]
        toast.on_activated = lambda _: activated(item["id"])
        toast.on_failed = lambda event: failed(
            item["id"], False, "Windows rejected the notification: " + str(getattr(event, "error_code", "unknown error"))
        )
        self.toaster.show_toast(toast)


def create_toaster():
    """Keep native event sources alive and detach callbacks before interpreter shutdown."""
    from windows_toasts import InteractableWindowsToaster
    from windows_toasts.events import ToastActivatedEventArgs
    from windows_toasts.toasters import _build_adaptable_data, _build_toast_notification
    from winrt.windows.ui.notifications import ToastNotification

    class ManagedToaster(InteractableWindowsToaster):
        def __init__(self):
            super().__init__("GetItDone", notifierAUMID=APP_ID)
            self.active_toasts = []

        def show_toast(self, toast):
            native = ToastNotification(self._setup_toast(toast, True).xmlDocument)
            native.data = _build_adaptable_data(toast)
            tokens = []
            if toast.on_activated is not None:
                token = native.add_activated(
                    lambda _, event: toast.on_activated(ToastActivatedEventArgs.fromWinRt(event))
                )
                tokens.append((native.remove_activated, token))
            if toast.on_failed is not None:
                token = native.add_failed(lambda _, event: toast.on_failed(event))
                tokens.append((native.remove_failed, token))
            self.active_toasts.append((native, tokens))
            try:
                self.toastNotifier.show(_build_toast_notification(toast, native))
            except Exception:
                self.active_toasts.pop()
                for remove, token in tokens:
                    remove(token)
                raise

        def close(self):
            for native, tokens in self.active_toasts:
                for remove, token in tokens:
                    remove(token)
            self.active_toasts.clear()

    return ManagedToaster()
