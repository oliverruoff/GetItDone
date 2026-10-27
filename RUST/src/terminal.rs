use crate::{agents, model::Session};
use anyhow::{Context, Result};
use eframe::egui::{self, Color32, Event, FontId, Key, Modifiers, RichText};
use portable_pty::{Child, CommandBuilder, MasterPty, PtySize, native_pty_system};
use std::{
    io::{Read, Write},
    path::Path,
    sync::{Arc, Mutex},
    time::Instant,
};

pub struct Terminal {
    pub parser: Arc<Mutex<vt100::Parser>>,
    master: Box<dyn MasterPty + Send>,
    writer: Arc<Mutex<Box<dyn Write + Send>>>,
    child: Box<dyn Child + Send + Sync>,
    pub alive: bool,
    pub raw: Arc<Mutex<Vec<u8>>>,
    pub last_size: (u16, u16),
    pub focus: bool,
    pub exit: Option<String>,
    pub started: Instant,
    pub rect: Option<egui::Rect>,
}
impl Terminal {
    pub fn start(
        session: &Session,
        resume: bool,
        runtime: &Path,
        ctx: Option<egui::Context>,
    ) -> Result<Self> {
        let mut args = agents::command(session, resume)?;
        if let Some(model) = session.model.as_ref().filter(|m| !m.is_empty()) {
            args.extend(["--model".into(), model.clone()]);
        }
        if session.agent == "pi" {
            args.extend([
                "--extension".into(),
                agents::pi_extension(runtime)?
                    .to_string_lossy()
                    .into_owned(),
            ]);
        }
        Self::spawn(
            &args,
            Path::new(&session.workdir),
            if session.agent == "pi" {
                Some(agents::pi_status_path(runtime, &session.id))
            } else {
                None
            },
            ctx,
        )
    }
    pub fn start_configured(
        session: &Session,
        resume: bool,
        runtime: &Path,
        ctx: Option<egui::Context>,
        settings: &serde_json::Value,
    ) -> Result<Self> {
        if ["opencode", "codex", "pi", "claude"].contains(&session.agent.as_str()) {
            return Self::start(session, resume, runtime, ctx);
        }
        anyhow::ensure!(
            !resume,
            "This custom profile does not support native session resume"
        );
        let profile = settings["profiles"]
            .as_array()
            .and_then(|p| p.iter().find(|p| p["id"] == session.agent))
            .context("Agent profile not found")?;
        let executable = profile["executable"]
            .as_str()
            .and_then(agents::executable)
            .context("Custom agent executable not found")?;
        let mut args = vec![executable.to_string_lossy().into_owned()];
        if let Some(values) = profile["args"].as_array() {
            for value in values {
                args.push(value.as_str().context("Invalid profile argument")?.into());
            }
        }
        Self::spawn(&args, Path::new(&session.workdir), None, ctx)
    }
    pub fn spawn(
        args: &[String],
        cwd: &Path,
        pi_status: Option<std::path::PathBuf>,
        ctx: Option<egui::Context>,
    ) -> Result<Self> {
        let pair = native_pty_system().openpty(PtySize {
            rows: 24,
            cols: 100,
            pixel_width: 0,
            pixel_height: 0,
        })?;
        let mut cmd = CommandBuilder::new(&args[0]);
        cmd.args(&args[1..]);
        cmd.cwd(cwd);
        cmd.env("TERM", "xterm-256color");
        cmd.env("COLORTERM", "truecolor");
        cmd.env("PATH", agents::augmented_path());
        // A desktop launch must create an independent CLI session, not inherit this Codex run.
        cmd.env_remove("CODEX_THREAD_ID");
        cmd.env("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", "codex_cli_rs");
        cmd.env_remove("CODEX_SESSION_ID");
        cmd.env_remove("CODEX_CI");
        cmd.env_remove("CODEX_SHELL");
        if let Some(path) = pi_status {
            let _ = std::fs::remove_file(&path);
            cmd.env("GETITDONE_PI_STATUS", path);
        }
        let child = pair.slave.spawn_command(cmd)?;
        drop(pair.slave);
        let mut reader = pair.master.try_clone_reader()?;
        let writer = Arc::new(Mutex::new(pair.master.take_writer()?));
        let parser = Arc::new(Mutex::new(vt100::Parser::new(24, 100, 10000)));
        let raw = Arc::new(Mutex::new(Vec::new()));
        let p = parser.clone();
        let r = raw.clone();
        let reply = writer.clone();
        std::thread::spawn(move || {
            let mut buf = [0u8; 16384];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(n) => {
                        if let Ok(mut p) = p.lock() {
                            p.process(&buf[..n]);
                            let (row, col) = p.screen().cursor_position();
                            if let Ok(mut writer) = reply.lock() {
                                for query in buf[..n].windows(4) {
                                    if query == b"\x1b[6n" {
                                        let _ = write!(writer, "\x1b[{};{}R", row + 1, col + 1);
                                    }
                                }
                                if buf[..n].windows(3).any(|w| w == b"\x1b[c") {
                                    let _ = writer.write_all(b"\x1b[?1;2c");
                                }
                                let _ = writer.flush();
                            }
                        }
                        if let Ok(mut raw) = r.lock() {
                            raw.extend_from_slice(&buf[..n]);
                            if raw.len() > 2 * 1024 * 1024 {
                                let len = raw.len() - 1024 * 1024;
                                raw.drain(..len);
                            }
                        }
                        if let Some(ctx) = &ctx {
                            ctx.request_repaint();
                        }
                    }
                }
            }
        });
        Ok(Self {
            parser,
            raw,
            master: pair.master,
            writer,
            child,
            alive: true,
            last_size: (24, 100),
            focus: true,
            exit: None,
            started: Instant::now(),
            rect: None,
        })
    }
    pub fn write(&mut self, bytes: &[u8]) -> Result<()> {
        let mut writer = self
            .writer
            .lock()
            .map_err(|_| anyhow::anyhow!("Terminal input unavailable"))?;
        writer.write_all(bytes)?;
        writer.flush()?;
        Ok(())
    }
    pub fn poll(&mut self) {
        if self.alive {
            match self.child.try_wait() {
                Ok(Some(status)) => {
                    self.alive = false;
                    self.exit = Some(format!("Process exited: {status}"));
                }
                Err(e) => {
                    self.alive = false;
                    self.exit = Some(e.to_string());
                }
                _ => {}
            }
        }
    }
    pub fn stop(&mut self) {
        if !self.alive {
            return;
        }
        #[cfg(unix)]
        if let Some(pid) = self.child.process_id() {
            unsafe {
                libc::kill(-(pid as i32), libc::SIGTERM);
            }
        }
        #[cfg(windows)]
        if let Some(pid) = self.child.process_id() {
            let mut cmd = std::process::Command::new("taskkill");
            cmd.args(["/PID", &pid.to_string(), "/T", "/F"]);
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
            let _ = cmd.status();
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
        self.alive = false;
    }
    pub fn contents(&self) -> String {
        self.parser
            .lock()
            .map(|p| p.screen().contents())
            .unwrap_or_default()
    }
    pub fn raw_text(&self) -> String {
        self.raw
            .lock()
            .map(|b| String::from_utf8_lossy(&b).into_owned())
            .unwrap_or_default()
    }
    pub fn ui(&mut self, ui: &mut egui::Ui) -> Result<()> {
        self.poll();
        if let Some(exit) = &self.exit {
            ui.label(RichText::new(exit).color(Color32::LIGHT_RED));
        }
        let font = FontId::monospace(13.0);
        let char_width = ui.fonts_mut(|f| f.glyph_width(&font, 'M'));
        let line = 17.;
        let size = ui.available_size();
        let cols = ((size.x - 20.) / char_width).floor().clamp(20., 400.) as u16;
        let rows = ((size.y - 14.) / line).floor().clamp(4., 150.) as u16;
        if (rows, cols) != self.last_size {
            self.master.resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })?;
            self.parser
                .lock()
                .map_err(|_| anyhow::anyhow!("Terminal parser unavailable"))?
                .screen_mut()
                .set_size(rows, cols);
            self.last_size = (rows, cols);
        }
        let (rect, response) = ui.allocate_exact_size(
            egui::vec2(size.x, size.y.max(100.)),
            egui::Sense::click_and_drag(),
        );
        self.rect = Some(rect);
        if response.clicked() || self.focus {
            response.request_focus();
            self.focus = false;
        }
        let painter = ui.painter_at(rect);
        painter.rect_filled(rect, 6., Color32::from_rgb(24, 29, 40));
        let mut bytes = vec![];
        {
            let mut parser = self
                .parser
                .lock()
                .map_err(|_| anyhow::anyhow!("Terminal parser unavailable"))?;
            if response.hovered() {
                let scroll = ui.input(|i| i.smooth_scroll_delta.y);
                if scroll.abs() > 1. {
                    let current = parser.screen().scrollback() as i32;
                    parser
                        .screen_mut()
                        .set_scrollback((current + (scroll / line) as i32).max(0) as usize);
                }
            }
            let screen = parser.screen();
            for row in 0..rows {
                for col in 0..cols {
                    if let Some(cell) = screen.cell(row, col) {
                        if cell.is_wide_continuation() {
                            continue;
                        }
                        let pos = rect.min
                            + egui::vec2(10. + col as f32 * char_width, 7. + row as f32 * line);
                        let mut fg = color(cell.fgcolor(), true);
                        let mut bg = color(cell.bgcolor(), false);
                        if cell.inverse() {
                            std::mem::swap(&mut fg, &mut bg);
                        }
                        if bg != Color32::from_rgb(24, 29, 40) {
                            painter.rect_filled(
                                egui::Rect::from_min_size(
                                    pos,
                                    egui::vec2(
                                        char_width * if cell.is_wide() { 2. } else { 1. },
                                        line,
                                    ),
                                ),
                                0.,
                                bg,
                            );
                        }
                        if !cell.contents().is_empty() {
                            painter.text(
                                pos,
                                egui::Align2::LEFT_TOP,
                                cell.contents(),
                                font.clone(),
                                fg,
                            );
                        }
                    }
                }
            }
            if response.has_focus() && !screen.hide_cursor() && screen.scrollback() == 0 {
                let (r, c) = screen.cursor_position();
                let pos = rect.min + egui::vec2(10. + c as f32 * char_width, 7. + r as f32 * line);
                painter.rect_stroke(
                    egui::Rect::from_min_size(pos, egui::vec2(char_width, line)),
                    0.,
                    egui::Stroke::new(1_f32, Color32::LIGHT_BLUE),
                    egui::StrokeKind::Inside,
                );
            }
            if response.has_focus() && self.alive {
                for event in ui.input(|i| i.events.clone()) {
                    match event {
                        Event::Text(t) => bytes.extend_from_slice(t.as_bytes()),
                        Event::Paste(t) => {
                            if screen.bracketed_paste() {
                                bytes.extend_from_slice(b"\x1b[200~");
                                bytes.extend_from_slice(t.as_bytes());
                                bytes.extend_from_slice(b"\x1b[201~");
                            } else {
                                bytes.extend_from_slice(t.as_bytes());
                            }
                        }
                        Event::Key {
                            key,
                            pressed: true,
                            modifiers,
                            ..
                        } => bytes.extend(encode_key(key, modifiers, screen.application_cursor())),
                        Event::Copy => ui.ctx().copy_text(screen.contents()),
                        _ => {}
                    }
                }
            }
        }
        if !bytes.is_empty() {
            self.parser.lock().unwrap().screen_mut().set_scrollback(0);
            self.write(&bytes).context("Could not write to terminal")?;
        }
        Ok(())
    }
}
impl Drop for Terminal {
    fn drop(&mut self) {
        self.stop();
    }
}
pub fn encode_key(key: Key, m: Modifiers, app: bool) -> Vec<u8> {
    if m.ctrl {
        let c = match key {
            Key::A => 1,
            Key::B => 2,
            Key::C => 3,
            Key::D => 4,
            Key::E => 5,
            Key::F => 6,
            Key::G => 7,
            Key::H => 8,
            Key::K => 11,
            Key::L => 12,
            Key::N => 14,
            Key::O => 15,
            Key::P => 16,
            Key::R => 18,
            Key::S => 19,
            Key::T => 20,
            Key::U => 21,
            Key::V => 22,
            Key::W => 23,
            Key::X => 24,
            Key::Y => 25,
            Key::Z => 26,
            _ => 0,
        };
        if c != 0 {
            return vec![c];
        }
    }
    match key {
        Key::Enter => b"\r".to_vec(),
        Key::Backspace => vec![127],
        Key::Escape => vec![27],
        Key::Tab => {
            if m.shift {
                b"\x1b[Z".to_vec()
            } else {
                vec![9]
            }
        }
        Key::ArrowUp => {
            if app {
                b"\x1bOA".to_vec()
            } else {
                b"\x1b[A".to_vec()
            }
        }
        Key::ArrowDown => {
            if app {
                b"\x1bOB".to_vec()
            } else {
                b"\x1b[B".to_vec()
            }
        }
        Key::ArrowRight => b"\x1b[C".to_vec(),
        Key::ArrowLeft => b"\x1b[D".to_vec(),
        Key::Home => b"\x1b[H".to_vec(),
        Key::End => b"\x1b[F".to_vec(),
        Key::Delete => b"\x1b[3~".to_vec(),
        Key::PageUp => b"\x1b[5~".to_vec(),
        Key::PageDown => b"\x1b[6~".to_vec(),
        _ => vec![],
    }
}
fn color(c: vt100::Color, fg: bool) -> Color32 {
    match c {
        vt100::Color::Default => {
            if fg {
                Color32::from_rgb(218, 226, 239)
            } else {
                Color32::from_rgb(24, 29, 40)
            }
        }
        vt100::Color::Rgb(r, g, b) => Color32::from_rgb(r, g, b),
        vt100::Color::Idx(i) => {
            let base = [
                [35, 40, 50],
                [229, 94, 110],
                [96, 192, 141],
                [230, 189, 104],
                [110, 163, 234],
                [190, 135, 228],
                [94, 196, 211],
                [214, 222, 235],
                [108, 119, 137],
                [255, 133, 144],
                [139, 220, 164],
                [255, 215, 137],
                [145, 191, 255],
                [218, 168, 255],
                [143, 223, 236],
                [247, 250, 255],
            ];
            let [r, g, b] = if i < 16 {
                base[i as usize]
            } else if i < 232 {
                let n = i - 16;
                let v = |n: u8| if n == 0 { 0 } else { 55 + 40 * n };
                [v(n / 36), v((n / 6) % 6), v(n % 6)]
            } else {
                let v = 8 + 10 * (i - 232);
                [v, v, v]
            };
            Color32::from_rgb(r, g, b)
        }
    }
}
