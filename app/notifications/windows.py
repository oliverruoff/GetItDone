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
        from windows_toasts import InteractableWindowsToaster

        register()
        self.toaster = InteractableWindowsToaster("GetItDone", notifierAUMID=APP_ID)

    def send(self, item, activated, failed):
        from windows_toasts import Toast
        from winrt.windows.ui.notifications import NotificationSetting

        if self.toaster.toastNotifier.setting != NotificationSetting.ENABLED:
            raise OSError(
                "Windows notifications are disabled for GetItDone or by system policy. "
                "Enable them in Settings → System → Notifications."
            )
        toast = Toast()
        toast.text_fields = [item.get("notification_title", "GetItDone · Reminder"), item["text"]]
        toast.on_activated = lambda _: activated(item["id"])
        toast.on_failed = lambda _: failed(item["id"], False, "Windows rejected the notification.")
        self.toaster.show_toast(toast)
