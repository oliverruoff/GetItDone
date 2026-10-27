"""OS-wide notifications with explicit authorization and scheduling results."""

import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QSystemTrayIcon


class Notifier(QObject):
    activated = Signal(str)
    status_changed = Signal(str)
    native_result = Signal(str, bool, str)

    def __init__(self, tray, parent=None):
        super().__init__(parent)
        self.tray = tray
        self.last_item = ""
        self.center = None
        self.permission = "unknown"
        self.status_changed.connect(self.set_status)
        self.status = "Use Test notification to verify system notification permissions."
        tray.messageClicked.connect(lambda: self.activated.emit(self.last_item))
        if sys.platform == "darwin":
            if getattr(sys, "frozen", False):
                self.setup_macos()
            else:
                self.permission = "unavailable"
                self.status = "System notifications are unavailable in the Python source process. Start GetItDone with run.command or GetItDone.app."
        elif not QSystemTrayIcon.supportsMessages():
            self.status = (
                "System notifications are unavailable. Check your operating system notification settings."
            )
        elif sys.platform == "win32":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\PushNotifications"
                ) as key:
                    if winreg.QueryValueEx(key, "ToastEnabled")[0] == 0:
                        self.status = "Windows notifications are disabled. Enable them in Settings → System → Notifications."
            except OSError:
                pass

    def setup_macos(self):
        try:
            import UserNotifications as UN
            from Foundation import NSObject

            notifier = self

            class GetItDoneNotificationDelegate(NSObject):
                def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(
                    self, center, response, completion
                ):
                    notifier.activated.emit(
                        str(response.notification().request().content().userInfo().get("item_id", ""))
                    )
                    completion()

                def userNotificationCenter_willPresentNotification_withCompletionHandler_(
                    self, center, notification, completion
                ):
                    completion(
                        UN.UNNotificationPresentationOptionBanner | UN.UNNotificationPresentationOptionSound
                    )

            self.delegate = GetItDoneNotificationDelegate.alloc().init()
            self.center = UN.UNUserNotificationCenter.currentNotificationCenter()
            self.center.setDelegate_(self.delegate)
            self.status = "Checking system notification permissions …"
            self.refresh_permission()
        except Exception as exc:
            self.center = None
            self.permission = "unavailable"
            self.status = "System notifications are unavailable: " + str(exc)

    @staticmethod
    def permission_message(settings):
        if int(settings.authorizationStatus()) == 0:
            return (
                False,
                "Notification permission has not been requested. Use Test notification to allow system banners.",
            )
        if int(settings.authorizationStatus()) not in (2, 3):
            return (
                False,
                "Notifications are not allowed. Enable GetItDone in System Settings → Notifications, including banners and sounds.",
            )
        if int(settings.alertSetting()) != 2:
            return (
                True,
                "Notification banners are disabled. Enable banners for GetItDone in System Settings → Notifications.",
            )
        return True, "Notifications allowed."

    def refresh_permission(self):
        if self.center:

            def read(settings):
                allowed, text = self.permission_message(settings)
                self.status_changed.emit(text)

            self.center.getNotificationSettingsWithCompletionHandler_(read)

    def request_permission(self):
        if self.center:
            import UserNotifications as UN

            self.center.requestAuthorizationWithOptions_completionHandler_(
                UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound,
                lambda granted, error: self.refresh_permission(),
            )

    def set_status(self, text):
        self.status = text
        self.permission = (
            "allowed"
            if text == "Notifications allowed."
            else "blocked"
            if any(value in text for value in ("not allowed", "disabled", "unavailable"))
            else "unknown"
        )

    def send(self, item):
        self.last_item = item["id"]
        if self.center:

            def schedule(settings):
                import UserNotifications as UN

                if int(settings.authorizationStatus()) == 0:

                    def authorized(granted, error):
                        if granted:
                            self.send(item)
                        else:
                            self.status_changed.emit(
                                "Notifications are not allowed. Enable GetItDone in System Settings → Notifications."
                            )
                            self.native_result.emit(
                                item["id"], False, "System notification permission was denied."
                            )

                    self.center.requestAuthorizationWithOptions_completionHandler_(
                        UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound, authorized
                    )
                    return

                allowed, message = self.permission_message(settings)
                self.status_changed.emit(message)
                if not allowed:
                    self.native_result.emit(item["id"], False, message)
                    return
                content = UN.UNMutableNotificationContent.alloc().init()
                content.setTitle_(item.get("notification_title", "GetItDone · Reminder"))
                content.setBody_(item["text"])
                content.setUserInfo_({"item_id": item["id"]})
                content.setSound_(UN.UNNotificationSound.defaultSound())
                request = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(
                    item["id"] or "getitdone-test", content, None
                )

                def completed(error):
                    detail = "Scheduled by macOS Notification Center." if error is None else str(error)
                    if error is not None:
                        self.status_changed.emit("System notification unavailable: " + detail)
                    self.native_result.emit(item["id"], error is None, detail)

                self.center.addNotificationRequest_withCompletionHandler_(request, completed)

            self.center.getNotificationSettingsWithCompletionHandler_(schedule)
        elif sys.platform == "darwin" or not QSystemTrayIcon.supportsMessages():
            self.status_changed.emit(self.status)
            self.native_result.emit(item["id"], False, self.status)
        else:
            self.tray.showMessage(item.get("notification_title", "GetItDone · Reminder"), item["text"], QSystemTrayIcon.Information, 10000)
            self.native_result.emit(item["id"], True, "Submitted to the system notification area.")
