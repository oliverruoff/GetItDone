use anyhow::Result;
#[cfg(not(target_os = "macos"))]
pub fn deliver(title: &str, body: &str) -> Result<String> {
    notify_rust::Notification::new()
        .summary(title)
        .body(body)
        .show()?;
    Ok("Notification accepted by system; OS focus and banner settings still apply".into())
}
#[cfg(target_os = "macos")]
pub fn deliver(title: &str, body: &str) -> Result<String> {
    use anyhow::ensure;
    use objc2_foundation::{NSError, NSString};
    use objc2_user_notifications::{
        UNAuthorizationOptions, UNMutableNotificationContent, UNNotification,
        UNNotificationRequest, UNNotificationSettings, UNUserNotificationCenter,
    };
    use std::{ptr::NonNull, sync::mpsc, time::Duration};
    ensure!(
        std::env::current_exe()?
            .to_string_lossy()
            .contains(".app/Contents/MacOS/"),
        "Native notifications require the packaged GetItDone.app"
    );
    objc2::rc::autoreleasepool(|_| -> Result<String> {
        let center = UNUserNotificationCenter::currentNotificationCenter();
        let (tx, rx) = mpsc::channel();
        let block =
            block2::RcBlock::new(move |allowed: objc2::runtime::Bool, error: *mut NSError| {
                let _ = tx.send(allowed.as_bool() && error.is_null());
            });
        center.requestAuthorizationWithOptions_completionHandler(
            UNAuthorizationOptions::Alert | UNAuthorizationOptions::Sound,
            &block,
        );
        ensure!(
            rx.recv_timeout(Duration::from_secs(90))?,
            "Notifications denied. Enable GetItDone in System Settings → Notifications."
        );
        let (tx, rx) = mpsc::channel();
        let block = block2::RcBlock::new(move |settings: NonNull<UNNotificationSettings>| {
            // UserNotifications owns this object for the duration of the callback.
            let s = unsafe { settings.as_ref() };
            let _ = tx.send((s.authorizationStatus().0, s.alertSetting().0));
        });
        center.getNotificationSettingsWithCompletionHandler(&block);
        let (auth, alert) = rx.recv_timeout(Duration::from_secs(5))?;
        ensure!(auth == 2 || auth == 3, "Notifications are not authorized");
        ensure!(
            alert == 2,
            "Notification banners are disabled. Enable them in System Settings."
        );
        let content = UNMutableNotificationContent::new();
        content.setTitle(&NSString::from_str(title));
        content.setBody(&NSString::from_str(body));
        let id = crate::model::uid();
        let request = UNNotificationRequest::requestWithIdentifier_content_trigger(
            &NSString::from_str(&id),
            &content,
            None,
        );
        let (tx, rx) = mpsc::channel();
        let block = block2::RcBlock::new(move |error: *mut NSError| {
            let _ = tx.send(error.is_null());
        });
        center.addNotificationRequest_withCompletionHandler(&request, Some(&block));
        ensure!(
            rx.recv_timeout(Duration::from_secs(5))?,
            "System rejected the notification"
        );
        std::thread::sleep(Duration::from_millis(300));
        let (tx, rx) = mpsc::channel();
        let block = block2::RcBlock::new(
            move |notifications: NonNull<objc2_foundation::NSArray<UNNotification>>| {
                let list = unsafe { notifications.as_ref() };
                let found = list
                    .iter()
                    .any(|n| n.request().identifier().to_string() == id);
                let _ = tx.send(found);
            },
        );
        center.getDeliveredNotificationsWithCompletionHandler(&block);
        if rx.recv_timeout(Duration::from_secs(5))? {
            Ok("Notification verified in Notification Center".into())
        } else {
            Ok("Notification accepted; delivery may be deferred by Focus or system policy".into())
        }
    })
}
