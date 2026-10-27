//! Native application Quit is distinct from closing/hiding a notebook window.
use std::sync::atomic::{AtomicBool, Ordering};
static QUIT_REQUESTED: AtomicBool = AtomicBool::new(false);
static CONTEXT: std::sync::OnceLock<eframe::egui::Context> = std::sync::OnceLock::new();
pub fn attach(ctx: &eframe::egui::Context) {
    let _ = CONTEXT.set(ctx.clone());
}
pub fn request_quit() {
    QUIT_REQUESTED.store(true, Ordering::Release);
    if let Some(ctx) = CONTEXT.get() {
        reveal(ctx);
    }
}
pub fn take_quit_request() -> bool {
    QUIT_REQUESTED.swap(false, Ordering::AcqRel)
}
pub fn reveal(ctx: &eframe::egui::Context) {
    use eframe::egui::ViewportCommand;
    ctx.send_viewport_cmd(ViewportCommand::Visible(true));
    ctx.send_viewport_cmd(ViewportCommand::Minimized(false));
    ctx.send_viewport_cmd(ViewportCommand::Focus);
    ctx.request_repaint();
}
#[cfg(target_os = "macos")]
pub fn install_native_quit() {
    use objc2::{
        ClassType, MainThreadMarker,
        runtime::{AnyObject, Imp, Sel},
        sel,
    };
    use objc2_app_kit::NSApplication;
    extern "C" fn terminate(_app: &NSApplication, _selector: Sel, _sender: Option<&AnyObject>) {
        request_quit();
    }
    let mtm =
        MainThreadMarker::new().expect("Native lifecycle must be installed on the main thread");
    let _app = NSApplication::sharedApplication(mtm);
    let method = NSApplication::class()
        .instance_method(sel!(terminate:))
        .expect("NSApplication has terminate:");
    type Terminate = extern "C" fn(&NSApplication, Sel, Option<&AnyObject>);
    // Same Objective-C method signature as NSApplication's terminate:. Intercepting it
    // keeps Dock Quit and Cmd-Q in the normal Rust save/confirmation/PTY cleanup path.
    unsafe {
        let implementation = std::mem::transmute::<Terminate, Imp>(terminate);
        method.set_implementation(implementation);
    }
}
#[cfg(not(target_os = "macos"))]
pub fn install_native_quit() {}
