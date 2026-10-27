#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]
use getitdone::{
    storage::{Store, default_folder},
    ui::App,
};
fn main() {
    if let Err(error) = run() {
        eprintln!("GetItDone: {error:#}");
        let _ = rfd::MessageDialog::new()
            .set_title("GetItDone could not start")
            .set_description(format!(
                "{error:#}\n\nYour original notebook has not been replaced."
            ))
            .set_level(rfd::MessageLevel::Error)
            .show();
        std::process::exit(1);
    }
}
fn run() -> anyhow::Result<()> {
    let mut folder = default_folder();
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--version" => {
                println!("GetItDone 0.2.0 · Rust · {}", std::env::consts::ARCH);
                return Ok(());
            }
            "--data-dir" => {
                folder = args
                    .next()
                    .ok_or_else(|| anyhow::anyhow!("--data-dir requires a folder"))?
                    .into()
            }
            _ => anyhow::bail!("Unknown option: {arg}"),
        }
    }
    let (store, book) = match Store::open(folder.clone()) {
        Ok(value) => value,
        Err(e) if e.to_string().contains("already open") => {
            std::fs::write(folder.join("activate.request"), b"activate")?;
            return Ok(());
        }
        Err(e) => return Err(e),
    };
    let options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_title("GetItDone · Local work notebook")
            .with_inner_size([1280., 860.])
            .with_min_inner_size([960., 620.]),
        ..Default::default()
    };
    getitdone::lifecycle::install_native_quit();
    eframe::run_native(
        "GetItDone",
        options,
        Box::new(move |cc| {
            App::style(&cc.egui_ctx);
            let mut app = App::new(store, book);
            getitdone::lifecycle::attach(&cc.egui_ctx);
            app.tray = getitdone::tray::Tray::new(cc.egui_ctx.clone());
            Ok(Box::new(app))
        }),
    )
    .map_err(|e| anyhow::anyhow!("{e}"))?;
    Ok(())
}
