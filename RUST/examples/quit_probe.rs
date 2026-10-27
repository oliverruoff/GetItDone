//! Native macOS regression probe: the same terminate: selector used by Dock Quit.
#[cfg(target_os = "macos")]
fn main() -> anyhow::Result<()> {
    use eframe::egui;
    use getitdone::{lifecycle, storage::Store, ui::App};
    use std::sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    };
    struct Probe {
        app: App,
        exited: Arc<AtomicBool>,
    }
    impl eframe::App for Probe {
        fn update(&mut self, ctx: &egui::Context, frame: &mut eframe::Frame) {
            eframe::App::update(&mut self.app, ctx, frame);
        }
        fn on_exit(&mut self, gl: Option<&eframe::glow::Context>) {
            assert!(self.app.quit, "Native Quit must use the app shutdown flow");
            eframe::App::on_exit(&mut self.app, gl);
            self.exited.store(true, Ordering::SeqCst);
        }
    }
    let temp = tempfile::tempdir()?;
    let (store, book) = Store::open(temp.path().join("data"))?;
    lifecycle::install_native_quit();
    let exited = Arc::new(AtomicBool::new(false));
    let flag = exited.clone();
    eframe::run_native(
        "GetItDone quit regression",
        eframe::NativeOptions::default(),
        Box::new(move |cc| {
            lifecycle::attach(&cc.egui_ctx);
            App::style(&cc.egui_ctx);
            let mut app = App::new(store, book);
            app.tray = getitdone::tray::Tray::new(cc.egui_ctx.clone());
            cc.egui_ctx
                .send_viewport_cmd(egui::ViewportCommand::Visible(false));
            std::thread::spawn(|| {
                std::thread::sleep(std::time::Duration::from_millis(500));
                dispatch2::DispatchQueue::main().exec_async(|| {
                    let mtm = objc2::MainThreadMarker::new().unwrap();
                    objc2_app_kit::NSApplication::sharedApplication(mtm).terminate(None);
                });
            });
            Ok(Box::new(Probe { app, exited: flag }))
        }),
    )
    .map_err(|e| anyhow::anyhow!("{e}"))?;
    anyhow::ensure!(exited.load(Ordering::SeqCst), "on_exit did not finish");
    let _ = Store::open(temp.path().join("data"))?;
    println!("PASS: native terminate: while hidden saved, exited, and released the notebook lock");
    Ok(())
}
#[cfg(not(target_os = "macos"))]
fn main() {
    println!("Native Dock Quit probe runs on macOS");
}
