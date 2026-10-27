use anyhow::{Context, Result, ensure};
use eframe::egui;
use std::path::Path;
pub struct PdfPreview {
    pub page: usize,
    pub count: usize,
    pub texture: Option<egui::TextureHandle>,
    pub loading: bool,
    pub error: Option<String>,
    rx: std::sync::mpsc::Receiver<Result<(usize, egui::ColorImage)>>,
    tx: std::sync::mpsc::Sender<Result<(usize, egui::ColorImage)>>,
}
impl Default for PdfPreview {
    fn default() -> Self {
        let (tx, rx) = std::sync::mpsc::channel();
        Self {
            page: 0,
            count: 0,
            texture: None,
            loading: false,
            error: None,
            rx,
            tx,
        }
    }
}
pub fn render(path: &Path, page: usize) -> Result<(usize, egui::ColorImage)> {
    let bytes = crate::storage::read_limited(path, 150 * 1024 * 1024)?;
    let pdf = hayro::hayro_syntax::Pdf::new(bytes)
        .map_err(|e| anyhow::anyhow!("Cannot preview PDF: {e:?}"))?;
    let pages = pdf.pages();
    ensure!(page < pages.len(), "Page does not exist");
    let p = pages.get(page).context("Page missing")?;
    let (w, h) = p.render_dimensions();
    ensure!(
        w.is_finite() && h.is_finite() && w > 0. && h > 0.,
        "Invalid PDF page size"
    );
    let scale = (1200_f32 / w).min(1800_f32 / h).min(2.);
    let pixmap = hayro::render(
        p,
        &hayro::RenderCache::new(),
        &Default::default(),
        &Default::default(),
        &hayro::PixmapSettings {
            x_scale: scale,
            y_scale: scale,
            ..Default::default()
        },
    );
    let size = [pixmap.width() as usize, pixmap.height() as usize];
    Ok((
        pages.len(),
        egui::ColorImage::from_rgba_premultiplied(size, pixmap.data_as_u8_slice()),
    ))
}
impl PdfPreview {
    fn load(&mut self, path: &Path, ctx: &egui::Context) {
        self.loading = true;
        self.error = None;
        self.texture = None;
        let path = path.to_path_buf();
        let tx = self.tx.clone();
        let page = self.page;
        let ctx = ctx.clone();
        std::thread::spawn(move || {
            let result = std::panic::catch_unwind(|| render(&path, page))
                .unwrap_or_else(|_| Err(anyhow::anyhow!("The PDF could not be rendered")));
            let _ = tx.send(result);
            ctx.request_repaint();
        });
    }
    pub fn ui(&mut self, ui: &mut egui::Ui, path: &Path) {
        while let Ok(result) = self.rx.try_recv() {
            self.loading = false;
            match result {
                Ok((count, image)) => {
                    self.count = count;
                    self.texture = Some(ui.ctx().load_texture(
                        "pdf-page",
                        image,
                        egui::TextureOptions::LINEAR,
                    ));
                }
                Err(e) => self.error = Some(e.to_string()),
            }
        }
        if self.texture.is_none() && !self.loading && self.error.is_none() {
            self.load(path, ui.ctx());
        }
        ui.horizontal(|ui| {
            if ui
                .add_enabled(
                    self.page > 0 && !self.loading,
                    egui::Button::new("Previous page"),
                )
                .clicked()
            {
                self.page -= 1;
                self.load(path, ui.ctx());
            }
            ui.label(format!("Page {} / {}", self.page + 1, self.count));
            if ui
                .add_enabled(
                    self.page + 1 < self.count && !self.loading,
                    egui::Button::new("Next page"),
                )
                .clicked()
            {
                self.page += 1;
                self.load(path, ui.ctx());
            }
        });
        if self.loading {
            ui.spinner();
            ui.label("Rendering PDF…");
        }
        if let Some(error) = &self.error {
            ui.colored_label(egui::Color32::DARK_RED, error);
        }
        if let Some(texture) = &self.texture {
            ui.add(
                egui::Image::new(texture)
                    .fit_to_exact_size(egui::vec2(
                        ui.available_width(),
                        ui.available_width() * texture.size()[1] as f32 / texture.size()[0] as f32,
                    ))
                    .bg_fill(egui::Color32::WHITE),
            );
        }
    }
}
