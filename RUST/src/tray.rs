#[cfg(any(target_os = "macos", target_os = "windows"))]
pub struct Tray {
    _icon: tray_icon::TrayIcon,
    events: std::sync::mpsc::Receiver<&'static str>,
}
#[cfg(not(any(target_os = "macos", target_os = "windows")))]
pub struct Tray;
impl Tray {
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    pub fn new(ctx: eframe::egui::Context) -> Option<Self> {
        use tray_icon::{
            Icon, TrayIconBuilder,
            menu::{Menu, MenuItem},
        };
        let menu = Menu::new();
        let show = MenuItem::new("Show GetItDone", true, None);
        let quit = MenuItem::new("Quit GetItDone", true, None);
        menu.append(&show).ok()?;
        menu.append(&quit).ok()?;
        let mut rgba = vec![0_u8; 20 * 20 * 4];
        for y in 2..18 {
            for x in 2..18 {
                if x < 5
                    || !(5..=14).contains(&y)
                    || (x > 13 && y > 9)
                    || (y > 8 && y < 12 && x > 9)
                {
                    let n = (y * 20 + x) * 4;
                    rgba[n..n + 4].copy_from_slice(&[45, 76, 118, 255]);
                }
            }
        }
        let icon = Icon::from_rgba(rgba, 20, 20).ok()?;
        let tray = TrayIconBuilder::new()
            .with_menu(Box::new(menu))
            .with_tooltip("GetItDone")
            .with_icon(icon)
            .build()
            .ok()?;
        let (tx, events) = std::sync::mpsc::channel();
        let show = show.id().clone();
        let quit = quit.id().clone();
        tray_icon::menu::MenuEvent::set_event_handler(Some(
            move |event: tray_icon::menu::MenuEvent| {
                let action = if event.id == show {
                    Some("show")
                } else if event.id == quit {
                    Some("quit")
                } else {
                    None
                };
                if let Some(action) = action {
                    let _ = tx.send(action);
                    crate::lifecycle::reveal(&ctx);
                }
            },
        ));
        Some(Self {
            _icon: tray,
            events,
        })
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    pub fn new(_ctx: eframe::egui::Context) -> Option<Self> {
        None
    }
    pub fn poll(&self) -> Option<&'static str> {
        #[cfg(any(target_os = "macos", target_os = "windows"))]
        if let Ok(action) = self.events.try_recv() {
            return Some(action);
        }
        None
    }
}
