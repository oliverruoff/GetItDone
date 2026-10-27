use crate::{
    agents::{self, Activity},
    context::{self, Finding},
    knowledge::{self, Document},
    model::{Category, Notebook, Session, now, uid},
    storage::Store,
    terminal::Terminal,
};
use anyhow::Result;
use eframe::egui::{self, Color32, Key, Rect, Response, RichText};
use std::{
    collections::{HashMap, HashSet},
    path::{Path, PathBuf},
    sync::mpsc,
    time::{Duration, Instant},
};

const BLUE: Color32 = Color32::from_rgb(48, 93, 151);
const INK: Color32 = Color32::from_rgb(35, 49, 68);
const MUTED: Color32 = Color32::from_rgb(106, 119, 137);
pub const PALETTE: [(&str, &str); 16] = [
    ("Red", "#c9414f"),
    ("Orange", "#dc7931"),
    ("Amber", "#e5af39"),
    ("Yellow", "#f1d85b"),
    ("Lime", "#a1c84b"),
    ("Green", "#3d9e50"),
    ("Emerald", "#26846a"),
    ("Teal", "#287e89"),
    ("Cyan", "#46b1cd"),
    ("Blue", "#3565c7"),
    ("Indigo", "#5651ae"),
    ("Purple", "#864db1"),
    ("Magenta", "#b54c91"),
    ("Rose", "#da7c99"),
    ("Slate", "#6a7b90"),
    ("Brown", "#91684d"),
];
#[derive(Clone)]
pub enum Action {
    Add(Option<String>),
    Sibling(String),
    Complete(String, bool),
    Delete(String),
    Edit(String),
    Note(String),
    DeleteNote(String),
    Indent(String, bool),
    Move(String, isize),
    Color(String, Option<(String, String)>),
    NewSession(String),
    Resume(String),
    CloseTerminal(String),
    Details(String),
    Reminder(String),
    Undo(usize),
}
pub struct Undo {
    pub label: String,
    pub completion: HashMap<String, bool>,
    pub note: Option<(String, String)>,
}
#[derive(Clone)]
struct StatusUpdate {
    id: String,
    native: Option<String>,
    activity: Activity,
}
pub struct App {
    pub book: Notebook,
    pub store: Store,
    pub terminals: HashMap<String, Terminal>,
    pub activity: HashMap<String, Activity>,
    pub unread: HashSet<String>,
    pub active_terminal: Option<String>,
    pub selected: Option<String>,
    pub editing: Option<String>,
    pub note_open: HashSet<String>,
    pub expanded: HashSet<String>,
    pub tab: String,
    pub query: String,
    pub filter: String,
    pub undo: Vec<Undo>,
    pub status: String,
    pub error: Option<String>,
    pub show_terminal: bool,
    pub show_settings: bool,
    profiles_json: String,
    markdown: egui_commonmark::CommonMarkCache,
    pub knowledge_folder: String,
    pub documents: Vec<PathBuf>,
    pub document: Option<Document>,
    pub document_dirty_at: Option<Instant>,
    pub note_title: String,
    pub session_dialog: Option<String>,
    pub session_agent: String,
    pub session_model: String,
    pub workdir: String,
    pub details: Option<String>,
    pub reminder: Option<String>,
    pub reminder_at: String,
    pub context_agent: String,
    pub context_folder: String,
    pub findings: Vec<Finding>,
    pub finding: Option<usize>,
    context_rx: Option<mpsc::Receiver<Vec<Finding>>>,
    pub context_kind: String,
    pub confirm: Option<(String, Option<Action>)>,
    pub quit: bool,
    pub widgets: HashMap<String, Rect>,
    pub runtime: PathBuf,
    tx: mpsc::Sender<Vec<StatusUpdate>>,
    rx: mpsc::Receiver<Vec<StatusUpdate>>,
    polling: bool,
    last_poll: Instant,
    started: String,
    pub notifications: String,
    notification_rx: Option<mpsc::Receiver<Result<String>>>,
    pub pdf: crate::pdf::PdfPreview,
    pub tray: Option<crate::tray::Tray>,
}
impl App {
    pub fn new(store: Store, book: Notebook) -> Self {
        let folder = book.settings["knowledge_folder"]
            .as_str()
            .unwrap_or("")
            .to_owned();
        let workdir = book.settings["default_workdir"]
            .as_str()
            .unwrap_or("")
            .to_owned();
        let agent = book.settings["default_agent"]
            .as_str()
            .unwrap_or("opencode")
            .to_owned();
        let runtime = store.folder.join("runtime");
        let _ = std::fs::create_dir_all(&runtime);
        let (tx, rx) = mpsc::channel();
        let documents = knowledge::list(Path::new(&folder)).unwrap_or_default();
        let profiles_json = serde_json::to_string_pretty(
            book.settings
                .get("profiles")
                .unwrap_or(&serde_json::json!([])),
        )
        .unwrap_or_default();
        Self {
            profiles_json,
            markdown: Default::default(),
            tray: None,
            pdf: Default::default(),
            book,
            store,
            terminals: HashMap::new(),
            activity: HashMap::new(),
            unread: HashSet::new(),
            active_terminal: None,
            selected: None,
            editing: None,
            note_open: HashSet::new(),
            expanded: HashSet::new(),
            tab: "Tasks".into(),
            query: String::new(),
            filter: "open".into(),
            undo: vec![],
            status: "All changes saved".into(),
            error: None,
            show_terminal: true,
            show_settings: false,
            knowledge_folder: folder,
            documents,
            document: None,
            document_dirty_at: None,
            note_title: String::new(),
            session_dialog: None,
            session_agent: agent,
            session_model: String::new(),
            workdir: workdir.clone(),
            details: None,
            reminder: None,
            reminder_at: String::new(),
            context_agent: "codex".into(),
            context_folder: workdir,
            findings: vec![],
            finding: None,
            context_rx: None,
            context_kind: "Instructions".into(),
            confirm: None,
            quit: false,
            widgets: HashMap::new(),
            runtime,
            tx,
            rx,
            polling: false,
            last_poll: Instant::now() - Duration::from_secs(10),
            started: now(),
            notifications: "Notifications: delivery not tested".into(),
            notification_rx: None,
        }
    }
    pub fn style(ctx: &egui::Context) {
        let mut style = (*ctx.style()).clone();
        style.visuals = egui::Visuals::light();
        style.visuals.panel_fill = Color32::from_rgb(247, 249, 252);
        style.visuals.window_fill = Color32::WHITE;
        style.visuals.override_text_color = Some(INK);
        style.visuals.widgets.noninteractive.bg_stroke =
            egui::Stroke::new(1_f32, Color32::from_rgb(224, 230, 238));
        style.visuals.widgets.inactive.weak_bg_fill = Color32::from_rgb(237, 242, 248);
        style.visuals.selection.bg_fill = Color32::from_rgb(218, 231, 249);
        style.spacing.item_spacing = egui::vec2(8., 7.);
        style.spacing.button_padding = egui::vec2(11., 6.);
        style.spacing.interact_size.y = 29.;
        style
            .text_styles
            .insert(egui::TextStyle::Body, egui::FontId::proportional(14.));
        style
            .text_styles
            .insert(egui::TextStyle::Button, egui::FontId::proportional(13.));
        ctx.set_style(style);
    }
    pub fn mark(&mut self, name: impl Into<String>, response: &Response) {
        self.widgets.insert(name.into(), response.rect);
    }
    pub fn persist(&mut self) {
        match self.store.save(&self.book) {
            Ok(()) => self.status = "All changes saved".into(),
            Err(e) => {
                self.status = format!("Save failed: {e}");
                self.error = Some(self.status.clone());
            }
        }
    }
    pub fn execute(&mut self, action: Action, ctx: Option<&egui::Context>) -> Result<()> {
        match action {
            Action::Add(parent) => {
                let id = self.book.add("", parent, None)?;
                self.selected = Some(id.clone());
                self.editing = Some(id);
            }
            Action::Sibling(id) => {
                let parent = self.book.item(&id).and_then(|i| i.parent_id.clone());
                let id = self.book.add("", parent, Some(&id))?;
                self.selected = Some(id.clone());
                self.editing = Some(id);
            }
            Action::Complete(id, done) => {
                let snapshot = self.book.complete(&id, done);
                self.undo.push(Undo {
                    label: if done {
                        "Item completed"
                    } else {
                        "Item reopened"
                    }
                    .into(),
                    completion: snapshot,
                    note: None,
                });
            }
            Action::Delete(id) => {
                let sessions = self.book.delete(&id);
                for s in sessions {
                    self.terminals.remove(&s);
                    self.activity.remove(&s);
                    self.unread.remove(&s);
                }
                if self
                    .book
                    .items
                    .iter()
                    .all(|i| Some(&i.id) != self.selected.as_ref())
                {
                    self.selected = None;
                }
            }
            Action::Edit(id) => {
                self.selected = Some(id.clone());
                self.editing = Some(id);
            }
            Action::Note(id) => {
                self.note_open.insert(id);
            }
            Action::DeleteNote(id) => {
                if let Some(i) = self.book.item_mut(&id) {
                    let text = std::mem::take(&mut i.notes);
                    self.undo.push(Undo {
                        label: "Note deleted".into(),
                        completion: HashMap::new(),
                        note: Some((id.clone(), text)),
                    });
                    self.note_open.remove(&id);
                }
            }
            Action::Indent(id, out) => self.book.indent(&id, out),
            Action::Move(id, delta) => self.book.shift(&id, delta),
            Action::Color(id, color) => {
                let category = if let Some((name, color)) = color {
                    Some(
                        if let Some(c) = self.book.categories.iter().find(|c| c.color == color) {
                            c.id.clone()
                        } else {
                            let id = uid();
                            self.book.categories.push(Category {
                                id: id.clone(),
                                name,
                                color,
                            });
                            id
                        },
                    )
                } else {
                    None
                };
                if let Some(i) = self.book.item_mut(&id) {
                    i.category_id = category;
                }
            }
            Action::NewSession(id) => {
                self.session_model = self.book.settings["agent_models"][&self.session_agent]
                    .as_str()
                    .unwrap_or("")
                    .to_owned();
                self.session_dialog = Some(id);
            }
            Action::Resume(id) => self.resume(&id, ctx)?,
            Action::CloseTerminal(id) => {
                self.terminals.remove(&id);
                if self.active_terminal.as_ref() == Some(&id) {
                    self.active_terminal = self.terminals.keys().next().cloned();
                }
            }
            Action::Details(id) => {
                self.details = Some(id);
            }
            Action::Reminder(id) => {
                self.reminder_at = self
                    .book
                    .item(&id)
                    .and_then(|i| i.reminder.as_ref())
                    .and_then(|r| r["at"].as_str())
                    .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
                    .map(|d| {
                        d.with_timezone(&chrono::Local)
                            .format("%Y-%m-%d %H:%M")
                            .to_string()
                    })
                    .unwrap_or_else(|| {
                        (chrono::Local::now() + chrono::Duration::hours(1))
                            .format("%Y-%m-%d %H:%M")
                            .to_string()
                    });
                self.reminder = Some(id);
            }
            Action::Undo(index) => {
                if index < self.undo.len() {
                    let undo = self.undo.remove(index);
                    self.book.restore_completion(&undo.completion);
                    if let Some((id, text)) = undo.note
                        && let Some(i) = self.book.item_mut(&id)
                    {
                        i.notes = text;
                        self.note_open.insert(id);
                    }
                }
            }
        }
        self.persist();
        Ok(())
    }
    pub fn start_session(&mut self, item: &str, ctx: Option<&egui::Context>) -> Result<String> {
        let id = self
            .book
            .new_session(item, &self.session_agent, &self.workdir)?;
        if !self.session_model.trim().is_empty() {
            self.book
                .sessions
                .iter_mut()
                .find(|s| s.id == id)
                .unwrap()
                .model = Some(self.session_model.trim().to_owned());
        }
        let mut s = self
            .book
            .sessions
            .iter()
            .find(|s| s.id == id)
            .unwrap()
            .clone();
        if s.agent == "codex" {
            match agents::create_codex_session(&s.workdir) {
                Ok(native) => {
                    s.native_session_id = Some(native.clone());
                    self.book
                        .sessions
                        .iter_mut()
                        .find(|s| s.id == id)
                        .unwrap()
                        .native_session_id = Some(native);
                }
                Err(e) => {
                    self.book.sessions.retain(|s| s.id != id);
                    return Err(e);
                }
            }
        }
        match Terminal::start_configured(
            &s,
            s.agent == "codex",
            &self.runtime,
            ctx.cloned(),
            &self.book.settings,
        ) {
            Ok(t) => {
                self.terminals.insert(id.clone(), t);
                self.active_terminal = Some(id.clone());
                self.show_terminal = true;
                self.book.settings["agent_models"][&self.session_agent] =
                    self.session_model.clone().into();
                self.book.settings["default_agent"] = self.session_agent.clone().into();
                self.book.settings["default_workdir"] = self.workdir.clone().into();
                self.persist();
                Ok(id)
            }
            Err(e) => {
                self.book.sessions.retain(|s| s.id != id);
                Err(e)
            }
        }
    }
    pub fn resume(&mut self, id: &str, ctx: Option<&egui::Context>) -> Result<()> {
        if !self.terminals.get(id).is_some_and(|t| t.alive) {
            let s = self
                .book
                .sessions
                .iter()
                .find(|s| s.id == id)
                .ok_or_else(|| anyhow::anyhow!("Session not found"))?
                .clone();
            let term = Terminal::start_configured(
                &s,
                true,
                &self.runtime,
                ctx.cloned(),
                &self.book.settings,
            )?;
            self.terminals.insert(id.into(), term);
        }
        if let Some(t) = self.terminals.get_mut(id) {
            t.focus = true;
        }
        self.active_terminal = Some(id.into());
        self.show_terminal = true;
        self.unread.remove(id);
        if let Some(s) = self.book.sessions.iter().find(|s| s.id == id) {
            self.context_agent = s.agent.clone();
            self.context_folder = s.workdir.clone();
        }
        Ok(())
    }
    pub fn set_folder(&mut self, folder: String) -> Result<()> {
        self.save_document()?;
        let docs = knowledge::list(Path::new(&folder))?;
        self.knowledge_folder = folder.clone();
        self.documents = docs;
        self.document = None;
        self.book.settings["knowledge_folder"] = folder.into();
        self.persist();
        Ok(())
    }
    pub fn open_document(&mut self, path: &Path) -> Result<()> {
        self.save_document()?;
        self.document = Some(Document::open(path)?);
        self.pdf = Default::default();
        self.book.settings["knowledge_last_file"] = path.to_string_lossy().as_ref().into();
        self.persist();
        Ok(())
    }
    pub fn save_document(&mut self) -> Result<()> {
        if let Some(d) = &mut self.document
            && d.editable
            && d.dirty()
        {
            d.save()?;
        }
        self.document_dirty_at = None;
        Ok(())
    }
    pub fn notify(&mut self, title: String, body: String) {
        let (tx, rx) = mpsc::channel();
        self.notification_rx = Some(rx);
        self.notifications = "Checking notification permissions…".into();
        std::thread::spawn(move || {
            let _ = tx.send(crate::notifications::deliver(&title, &body));
        });
    }
    pub fn tick(&mut self, ctx: Option<&egui::Context>) {
        if let Some(result) = self
            .notification_rx
            .as_ref()
            .and_then(|r| r.try_recv().ok())
        {
            self.notifications = match result {
                Ok(message) => message,
                Err(e) => format!("Notification unavailable: {e}"),
            };
            self.notification_rx = None;
        }

        if let Some(findings) = self.context_rx.as_ref().and_then(|rx| rx.try_recv().ok()) {
            self.findings = findings;
            self.finding = None;
            self.context_rx = None;
        }
        for t in self.terminals.values_mut() {
            t.poll();
        }
        while let Ok(updates) = self.rx.try_recv() {
            self.polling = false;
            let mut changed = false;
            for u in updates {
                if let Some(native) = u.native
                    && let Some(s) = self.book.sessions.iter_mut().find(|s| s.id == u.id)
                    && s.native_session_id.is_none()
                {
                    s.native_session_id = Some(native);
                    changed = true;
                }
                if let Some(previous) = self.activity.get(&u.id)
                    && u.activity.message.is_some()
                    && u.activity.message != previous.message
                    && self.active_terminal.as_ref() != Some(&u.id)
                {
                    self.unread.insert(u.id.clone());
                }
                self.activity.insert(u.id, u.activity);
            }
            if changed {
                self.persist();
            }
        }
        if !self.polling && self.last_poll.elapsed() > Duration::from_secs(1) {
            let sessions: Vec<Session> = self
                .book
                .sessions
                .iter()
                .filter(|s| self.terminals.get(&s.id).is_some_and(|t| t.alive))
                .cloned()
                .collect();
            if !sessions.is_empty() {
                self.polling = true;
                let runtime = self.runtime.clone();
                let tx = self.tx.clone();
                let context = ctx.cloned();
                std::thread::spawn(move || {
                    let mut updates = vec![];
                    for mut s in sessions {
                        let native = if s.agent == "codex" && s.native_session_id.is_none() {
                            agents::discover_codex(&s)
                        } else {
                            None
                        };
                        if let Some(id) = &native {
                            s.native_session_id = Some(id.clone());
                        }
                        updates.push(StatusUpdate {
                            id: s.id.clone(),
                            native,
                            activity: agents::snapshot(&s, &runtime),
                        });
                    }
                    let _ = tx.send(updates);
                    if let Some(ctx) = context {
                        ctx.request_repaint();
                    }
                });
            }
            self.last_poll = Instant::now();
        }
        if self
            .document_dirty_at
            .is_some_and(|t| t.elapsed() > Duration::from_millis(600))
            && let Err(e) = self.save_document()
        {
            self.error = Some(e.to_string());
            self.document_dirty_at = None;
        }
        let now = chrono::Utc::now();
        let start = chrono::DateTime::parse_from_rfc3339(&self.started).unwrap();
        let mut changed = false;
        let mut due = vec![];
        for i in &mut self.book.items {
            if i.done {
                continue;
            }
            if let Some(r) = &mut i.reminder {
                if r["notified_at"].is_string() || r["notified"] == true {
                    continue;
                }
                if let Some(at) = r["at"]
                    .as_str()
                    .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
                    && at <= now
                {
                    r["notified_at"] = crate::model::now().into();
                    changed = true;
                    if at >= start {
                        due.push(i.text.clone());
                    }
                }
            }
        }
        if changed {
            self.persist();
        }
        for text in due {
            self.notify("GetItDone reminder".into(), text);
        }
    }
    pub fn request(&mut self, action: Action, ctx: &egui::Context) {
        let needs_confirmation = match &action {
            Action::Delete(id) => {
                let mut ids = self.book.descendants(id);
                ids.push(id.clone());
                self.book.sessions.iter().any(|s| {
                    ids.contains(&s.item_id) && self.terminals.get(&s.id).is_some_and(|t| t.alive)
                })
            }
            Action::Complete(id, true) => {
                let mut ids = self.book.descendants(id);
                ids.push(id.clone());
                self.book.sessions.iter().any(|s| {
                    ids.contains(&s.item_id) && self.terminals.get(&s.id).is_some_and(|t| t.alive)
                })
            }
            Action::CloseTerminal(id) => self.terminals.get(id).is_some_and(|t| t.alive),
            _ => false,
        };
        if needs_confirmation {
            self.confirm=Some((match &action{Action::Delete(_)=>"Delete this item and its children? Their running terminals will be stopped. Native agent histories remain available.",Action::Complete(_,_)=>"Complete this item and its children? Running sessions will be hidden from the open view but remain active.",_=>"Close this running terminal? The process will stop. Resume reopens its saved conversation."}.into(),Some(action)));
        } else if let Err(e) = self.execute(action, Some(ctx)) {
            self.error = Some(e.to_string());
        }
    }
    pub fn finish_quit(&mut self) -> bool {
        if let Err(e) = self.save_document() {
            self.error = Some(e.to_string());
            return false;
        }
        self.persist();
        if self.status.starts_with("Save failed") {
            return false;
        }
        self.terminals.clear();
        self.quit = true;
        true
    }
    pub fn request_quit(&mut self, ctx: &egui::Context) {
        crate::lifecycle::reveal(ctx);
        if self.terminals.values().any(|t| t.alive) {
            self.confirm = Some(("Quit GetItDone and stop running terminals?".into(), None));
        } else {
            self.finish_quit();
        }
    }
    pub fn draw(&mut self, ctx: &egui::Context) {
        self.widgets.clear();
        self.tick(Some(ctx));
        if crate::lifecycle::take_quit_request() {
            self.request_quit(ctx);
        }
        if self.store.folder.join("activate.request").exists() {
            let _ = std::fs::remove_file(self.store.folder.join("activate.request"));
            ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
            ctx.send_viewport_cmd(egui::ViewportCommand::Minimized(false));
            ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
        }
        if let Some(event) = self.tray.as_ref().and_then(|t| t.poll()) {
            match event {
                "show" => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
                    ctx.send_viewport_cmd(egui::ViewportCommand::Minimized(false));
                    ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
                }
                "quit" => self.request_quit(ctx),
                _ => {}
            }
        }
        egui::TopBottomPanel::top("header")
            .frame(
                egui::Frame::new()
                    .fill(Color32::WHITE)
                    .inner_margin(egui::Margin::symmetric(22, 15)),
            )
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("G").size(25.).strong().color(BLUE));
                    ui.add_space(5.);
                    ui.label(RichText::new("GetItDone").size(22.).strong());
                    ui.label(RichText::new("LOCAL WORK NOTEBOOK").size(10.).color(MUTED));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let r = ui.button("Settings");
                        self.mark("settings", &r);
                        if r.clicked() {
                            self.show_settings = true;
                        }
                        let quit = ui.button("Quit");
                        self.mark("quit", &quit);
                        if quit.clicked() {
                            self.request_quit(ctx);
                        }
                        ui.checkbox(&mut self.show_terminal, "Terminal");
                    });
                });
                ui.add_space(12.);
                ui.horizontal(|ui| {
                    for tab in ["Tasks", "Knowledge", "Agent context"] {
                        let r = ui.selectable_label(
                            self.tab == tab,
                            RichText::new(tab).strong().size(14.),
                        );
                        self.mark(format!("tab:{tab}"), &r);
                        if r.clicked() {
                            if let Err(e) = self.save_document() {
                                self.error = Some(e.to_string());
                            } else {
                                self.tab = tab.into();
                            }
                        }
                    }
                });
            });
        egui::TopBottomPanel::bottom("status")
            .frame(
                egui::Frame::new()
                    .fill(Color32::from_rgb(236, 241, 248))
                    .inner_margin(egui::Margin::symmetric(18, 7)),
            )
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new(if self.status.starts_with("Save failed") {
                            &self.status
                        } else {
                            "● All changes saved"
                        })
                        .size(11.)
                        .color(
                            if self.status.starts_with("Save failed") {
                                Color32::DARK_RED
                            } else {
                                MUTED
                            },
                        ),
                    );
                    ui.separator();
                    ui.label(
                        RichText::new(format!(
                            "{} items · {} terminals",
                            self.book.items.len(),
                            self.terminals.values().filter(|t| t.alive).count()
                        ))
                        .size(11.)
                        .color(MUTED),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(RichText::new("Rust · 0.2.0").size(11.).color(MUTED));
                    });
                });
            });
        if self.show_terminal && !self.terminals.is_empty() {
            egui::TopBottomPanel::bottom("terminals")
                .resizable(true)
                .default_height(320.)
                .min_height(150.)
                .frame(
                    egui::Frame::new()
                        .fill(Color32::from_rgb(24, 29, 40))
                        .inner_margin(8),
                )
                .show(ctx, |ui| {
                    self.terminal_panel(ui, ctx);
                });
        }
        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(Color32::from_rgb(247, 249, 252))
                    .inner_margin(egui::Margin::symmetric(22, 16)),
            )
            .show(ctx, |ui| match self.tab.as_str() {
                "Knowledge" => self.knowledge_ui(ui),
                "Agent context" => self.context_ui(ui),
                _ => self.tasks_ui(ui, ctx),
            });
        self.dialogs(ctx);
        ctx.request_repaint_after(Duration::from_millis(150));
        if ctx.input(|i| i.viewport().close_requested()) && !self.quit {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            if self.tray.is_some() {
                ctx.send_viewport_cmd(egui::ViewportCommand::Visible(false));
            } else {
                ctx.send_viewport_cmd(egui::ViewportCommand::Minimized(true));
            }
        }
        if self.quit {
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
    }
    fn tasks_ui(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        let mut actions = vec![];
        let mut changed = false;
        ui.horizontal(|ui| {
            ui.label(RichText::new("Your work").size(20.).strong());
            ui.add_space(15.);
            let r = ui.add(
                egui::TextEdit::singleline(&mut self.query)
                    .hint_text("Search items and notes…")
                    .desired_width(260.),
            );
            self.mark("search", &r);
            egui::ComboBox::from_id_salt("status-filter")
                .selected_text(match self.filter.as_str() {
                    "done" => "Completed",
                    "all" => "All items",
                    _ => "Open items",
                })
                .show_ui(ui, |ui| {
                    for (id, label) in [
                        ("open", "Open items"),
                        ("done", "Completed"),
                        ("all", "All items"),
                    ] {
                        let r = ui.selectable_value(&mut self.filter, id.into(), label);
                        self.mark(format!("filter:{id}"), &r);
                    }
                });
        });
        ui.add_space(12.);
        if self.undo.len() > 8 {
            self.undo.remove(0);
        }
        for index in 0..self.undo.len() {
            let label = self.undo[index].label.clone();
            egui::Frame::new()
                .fill(Color32::from_rgb(228, 242, 234))
                .corner_radius(5)
                .inner_margin(6)
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(label);
                        let r = ui.button("Undo");
                        self.mark(format!("undo:{index}"), &r);
                        if r.clicked() {
                            actions.push(Action::Undo(index));
                        }
                        if ui.small_button("Dismiss").clicked() {
                            actions.push(Action::Undo(usize::MAX));
                        }
                    });
                });
        }
        ui.horizontal(|ui| {
            ui.label(
                RichText::new("ITEM / NOTES / SESSIONS")
                    .size(10.)
                    .color(MUTED),
            );
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.label(
                    RichText::new("COLOR       REMINDER          ACTIONS")
                        .size(10.)
                        .color(MUTED),
                );
            });
        });
        ui.separator();
        let visible = self.book.visible(&self.query, &self.filter);
        let mut ordered = vec![];
        fn visit(
            book: &Notebook,
            parent: Option<&str>,
            depth: usize,
            out: &mut Vec<(String, usize)>,
        ) {
            for id in book.children(parent) {
                out.push((id.clone(), depth));
                visit(book, Some(&id), depth + 1, out);
            }
        }
        visit(&self.book, None, 0, &mut ordered);
        egui::ScrollArea::vertical().id_salt("tasks-scroll").auto_shrink([false,false]).show(ui,|ui|{
            if ordered.is_empty(){ui.add_space(45.);ui.vertical_centered(|ui|{ui.label(RichText::new("A clear place for your next thought.").size(20.).color(MUTED));ui.label("Add an item below. Keep notes, reminders and agent sessions with your work.");});ui.add_space(30.);}
            for (id,depth) in ordered {if !visible.contains(&id){continue;}
                let item=self.book.item(&id).unwrap().clone();let category=item.category_id.as_ref().and_then(|c|self.book.categories.iter().find(|x|&x.id==c)).cloned();
                let fill=category.as_ref().and_then(|c|hex(&c.color)).unwrap_or(if depth==0{Color32::WHITE}else{Color32::from_rgb(240,244,249)});
                let foreground=if fill.r() as u32*299+fill.g() as u32*587+fill.b() as u32*114<145000{Color32::WHITE}else{INK};
                let selected=self.selected.as_ref()==Some(&id);let stroke=if selected{egui::Stroke::new(1.5_f32,BLUE)}else{egui::Stroke::new(1_f32,Color32::from_rgb(224,230,238))};
                if depth==0{ui.add_space(5.);}
                egui::Frame::new().fill(fill).stroke(stroke).corner_radius(5).inner_margin(egui::Margin::symmetric(10,7)).show(ui,|ui|{
                    ui.style_mut().visuals.override_text_color=Some(foreground);
                    ui.horizontal(|ui|{
                        ui.add_space((depth.min(10)*27) as f32);if depth>0{ui.label(RichText::new("└").color(foreground.gamma_multiply(0.65)));}
                        let mut done=item.done;let r=ui.checkbox(&mut done,"");self.mark(format!("complete:{id}"),&r);if r.changed(){actions.push(Action::Complete(id.clone(),done));}
                        let reserved=355.;let width=(ui.available_width()-reserved).max(100.);
                        if self.editing.as_ref()==Some(&id){
                            let mut text=item.text.clone();let newly=ui.memory_mut(|m|m.data.get_temp::<bool>(egui::Id::new(("editing",&id)))).unwrap_or(false);
                            let r=if self.expanded.contains(&id){ui.add_sized([width,65.],egui::TextEdit::multiline(&mut text).id_salt(("title",&id)))}else{ui.add_sized([width,29.],egui::TextEdit::singleline(&mut text).id_salt(("title",&id)).hint_text("What needs doing?"))};
                            self.mark(format!("title-editor:{id}"),&r);if !newly{r.request_focus();ui.memory_mut(|m|m.data.insert_temp(egui::Id::new(("editing",&id)),true));}
                            if r.changed(){self.book.item_mut(&id).unwrap().text=text;self.book.item_mut(&id).unwrap().updated_at=now();changed=true;}
                            if r.has_focus()&&ui.input(|i|i.key_pressed(Key::Escape)){self.editing=None;ui.memory_mut(|m|m.data.remove::<bool>(egui::Id::new(("editing",&id))));}
                            if r.lost_focus(){self.editing=None;ui.memory_mut(|m|m.data.remove::<bool>(egui::Id::new(("editing",&id))));}
                            if r.has_focus()&&ui.input(|i|i.key_pressed(Key::Enter))&&!self.expanded.contains(&id){actions.push(Action::Sibling(id.clone()));ui.memory_mut(|m|m.data.remove::<bool>(egui::Id::new(("editing",&id))));}
                        }else{
                            let text=if item.text.is_empty(){"Untitled item"}else{&item.text};let mut rich=RichText::new(text).color(foreground);if depth==0{rich=rich.strong();}
if done{rich=rich.strikethrough();}
                            let label=egui::Label::new(rich).sense(egui::Sense::click());let label=if self.expanded.contains(&id){label.wrap()}else{label.truncate()};
                            let r=ui.add_sized([width,29.],label);self.mark(format!("item:{id}"),&r);if r.clicked(){self.selected=Some(id.clone());r.request_focus();}
if r.double_clicked(){actions.push(Action::Edit(id.clone()));}
                        }
                        let r=ui.menu_button(RichText::new("●").color(foreground),|ui|{
                            ui.label("Row color");egui::Grid::new(("palette",&id)).spacing([4.,4.]).show(ui,|ui|{for (n,(name,color)) in PALETTE.iter().enumerate(){let r=ui.add_sized([27.,25.],egui::Button::new("").fill(hex(color).unwrap())).on_hover_text(*name);self.mark(format!("color:{id}:{name}"),&r);if r.clicked(){actions.push(Action::Color(id.clone(),Some((name.to_string(),color.to_string()))));ui.close();}
if n%4==3{ui.end_row();}}});
                            let r=ui.button("No color");self.mark(format!("no-color:{id}"),&r);if r.clicked(){actions.push(Action::Color(id.clone(),None));ui.close();}
                        });self.mark(format!("palette:{id}"),&r.response);r.response.on_hover_text(category.as_ref().map(|c|c.name.as_str()).unwrap_or("Color"));
                        let reminder=item.reminder.as_ref().and_then(|r|r["at"].as_str()).and_then(|s|chrono::DateTime::parse_from_rfc3339(s).ok());
                        let label=reminder.map(|d|format!("◷ {}",d.with_timezone(&chrono::Local).format("%d %b %H:%M"))).unwrap_or_else(||"◷ Reminder".into());
                        let r=ui.add_sized([112.,26.],egui::Button::new(RichText::new(label).size(11.).color(foreground)).frame(false));self.mark(format!("reminder:{id}"),&r);if r.clicked(){actions.push(Action::Reminder(id.clone()));}
                        for (name,label,tip,action) in [("edit","✎","Edit item",Action::Edit(id.clone())),("note","≡","Edit note",Action::Note(id.clone())),("session","＋","New session",Action::NewSession(id.clone()))]{let r=ui.small_button(RichText::new(label).color(foreground)).on_hover_text(tip);r.widget_info(||egui::WidgetInfo::labeled(egui::WidgetType::Button,true,tip));self.mark(format!("{name}:{id}"),&r);if r.clicked(){actions.push(action);}}
                        let menu=ui.menu_button(RichText::new("···").color(foreground),|ui|{
                            for (label,action) in [("Add child",Action::Add(Some(id.clone()))),("Add sibling",Action::Sibling(id.clone())),("Indent",Action::Indent(id.clone(),false)),("Outdent",Action::Indent(id.clone(),true)),("Move up",Action::Move(id.clone(),-1)),("Move down",Action::Move(id.clone(),1)),("Delete item",Action::Delete(id.clone()))]{let r=ui.button(label);self.mark(format!("menu:{label}:{id}"),&r);if r.clicked(){actions.push(action);ui.close();}}
                            if ui.button("Expand / collapse title").clicked(){if !self.expanded.remove(&id){self.expanded.insert(id.clone());}ui.close();}
                            for url in urls(&item.text){if ui.button(format!("Open {url}")).clicked(){let _=open::that(url);ui.close();}}
                        });self.mark(format!("more:{id}"),&menu.response);
                    });
                });
                if self.note_open.contains(&id)||!item.notes.is_empty(){egui::Frame::new().fill(Color32::from_rgb(235,241,249)).inner_margin(egui::Margin::symmetric(12,8)).show(ui,|ui|{ui.horizontal(|ui|{ui.add_space((depth*27+30) as f32);let mut notes=item.notes.clone();let r=ui.add_sized([ui.available_width()-50.,62.],egui::TextEdit::multiline(&mut notes).hint_text("Add a note…").id_salt(("note",&id)));self.mark(format!("note-editor:{id}"),&r);if r.changed(){self.book.item_mut(&id).unwrap().notes=notes;changed=true;}let r=ui.button("×").on_hover_text("Delete note");self.mark(format!("delete-note:{id}"),&r);if r.clicked(){actions.push(Action::DeleteNote(id.clone()));}});});}
                let sessions:Vec<_>=self.book.sessions.iter().filter(|s|s.item_id==id).cloned().collect();
                for session in sessions {ui.horizontal(|ui|{ui.add_space((depth*27+46) as f32);ui.label(RichText::new("↳").color(MUTED));ui.label(RichText::new(&session.agent).strong().size(12.));
                    let running=self.terminals.get(&session.id).is_some_and(|t|t.alive);let a=self.activity.get(&session.id).cloned();let state=if running{a.as_ref().map(|a|a.state.as_str()).unwrap_or("Connecting")}else{"Terminal closed"};
                    let r=ui.label(RichText::new(format!("{}  ·  {}{}",if running{"● Running"}else{"○ Saved"},state,if self.unread.contains(&session.id){" · New reply"}else{""})).size(11.).color(if state=="Working"{BLUE}else{MUTED}));self.mark(format!("status:{}",session.id),&r);r.on_hover_text(a.as_ref().map(|a|a.source.as_str()).unwrap_or("Waiting for an agent event"));
                    let r=ui.small_button("Resume");self.mark(format!("resume:{}",session.id),&r);if r.clicked(){actions.push(Action::Resume(session.id.clone()));}
                    let r=ui.small_button("ⓘ").on_hover_text("Session details");r.widget_info(||egui::WidgetInfo::labeled(egui::WidgetType::Button,true,"Session details"));self.mark(format!("details:{}",session.id),&r);if r.clicked(){actions.push(Action::Details(session.id.clone()));}
                });}
            }
            ui.add_space(10.);let r=ui.add_sized([ui.available_width(),36.],egui::Button::new(RichText::new("＋  Add item").color(BLUE)).fill(Color32::from_rgb(231,239,250)));self.mark("add-item",&r);if r.clicked(){actions.push(Action::Add(None));}
        });
        if !ctx.wants_keyboard_input()
            && let Some(id) = self.selected.clone()
        {
            if ctx.input(|i| i.key_pressed(Key::F2)) {
                actions.push(Action::Edit(id.clone()));
            }
            if ctx.input(|i| i.key_pressed(Key::Tab)) {
                actions.push(Action::Indent(id.clone(), ctx.input(|i| i.modifiers.shift)));
            }
        }
        if changed {
            self.persist();
        }
        for action in actions {
            if matches!(action, Action::Undo(usize::MAX)) {
                self.undo.pop();
            } else {
                self.request(action, ctx);
            }
        }
    }
    fn terminal_panel(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        let mut close = None;
        ui.horizontal_wrapped(|ui| {
            ui.label(RichText::new("TERMINALS").size(10.).color(Color32::GRAY));
            let sessions: Vec<_> = self
                .book
                .sessions
                .iter()
                .filter(|s| self.terminals.contains_key(&s.id))
                .cloned()
                .collect();
            for s in sessions {
                let label = format!(
                    "{} · {}",
                    s.agent,
                    s.title.chars().take(25).collect::<String>()
                );
                let r = ui.selectable_label(
                    self.active_terminal.as_ref() == Some(&s.id),
                    RichText::new(label).color(Color32::from_rgb(210, 222, 242)),
                );
                self.mark(format!("terminal-tab:{}", s.id), &r);
                if r.clicked() {
                    self.active_terminal = Some(s.id.clone());
                    self.unread.remove(&s.id);
                    if let Some(t) = self.terminals.get_mut(&s.id) {
                        t.focus = true;
                    }
                }
                let r = ui
                    .small_button(RichText::new("×").color(Color32::LIGHT_GRAY))
                    .on_hover_text("Close terminal");
                self.mark(format!("close-terminal:{}", s.id), &r);
                if r.clicked() {
                    close = Some(s.id.clone());
                }
            }
        });
        ui.separator();
        if let Some(id) = self.active_terminal.clone()
            && let Some(term) = self.terminals.get_mut(&id)
            && let Err(e) = term.ui(ui)
        {
            self.error = Some(e.to_string());
        }
        if let Some(rect) = self
            .active_terminal
            .as_ref()
            .and_then(|id| self.terminals.get(id))
            .and_then(|t| t.rect)
        {
            self.widgets.insert("terminal-surface".into(), rect);
        }
        if let Some(id) = close {
            self.request(Action::CloseTerminal(id), ctx);
        }
    }
    fn knowledge_ui(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.label(RichText::new("Knowledge").size(20.).strong());
            let r = ui.button("Choose folder…");
            self.mark("choose-folder", &r);
            if r.clicked()
                && let Some(p) = rfd::FileDialog::new().pick_folder()
                && let Err(e) = self.set_folder(p.display().to_string())
            {
                self.error = Some(e.to_string());
            }
            let r = ui.button("Refresh");
            self.mark("refresh-documents", &r);
            if r.clicked() {
                match knowledge::list(Path::new(&self.knowledge_folder)) {
                    Ok(d) => self.documents = d,
                    Err(e) => self.error = Some(e.to_string()),
                }
            }
        });
        ui.label(
            RichText::new(if self.knowledge_folder.is_empty() {
                "Choose a local folder. Your notes remain ordinary files."
            } else {
                &self.knowledge_folder
            })
            .size(11.)
            .color(MUTED),
        );
        ui.add_space(12.);
        ui.horizontal(|ui| {
            let r = ui.add(
                egui::TextEdit::singleline(&mut self.note_title)
                    .hint_text("New note title")
                    .desired_width(220.),
            );
            self.mark("new-note-title", &r);
            let r = ui.button("＋ New note");
            self.mark("new-note", &r);
            if r.clicked() {
                match knowledge::create(Path::new(&self.knowledge_folder), &self.note_title, "") {
                    Ok(p) => {
                        self.note_title.clear();
                        self.documents =
                            knowledge::list(Path::new(&self.knowledge_folder)).unwrap_or_default();
                        if let Err(e) = self.open_document(&p) {
                            self.error = Some(e.to_string());
                        }
                    }
                    Err(e) => self.error = Some(e.to_string()),
                }
            }
            let r = ui.button("Save as new note");
            self.mark("save-as-note", &r);
            if r.clicked() {
                let text = self
                    .document
                    .as_ref()
                    .map(|d| d.text.clone())
                    .unwrap_or_default();
                match knowledge::create(Path::new(&self.knowledge_folder), &self.note_title, &text)
                {
                    Ok(p) => {
                        self.document_dirty_at = None;
                        self.document = None;
                        self.note_title.clear();
                        self.documents =
                            knowledge::list(Path::new(&self.knowledge_folder)).unwrap_or_default();
                        if let Err(e) = self.open_document(&p) {
                            self.error = Some(e.to_string());
                        }
                        self.error = None;
                    }
                    Err(e) => self.error = Some(e.to_string()),
                }
            }
        });
        ui.separator();
        let height = ui.available_height();
        ui.columns(2, |columns| {
            egui::ScrollArea::vertical()
                .id_salt("documents-list")
                .max_height(height)
                .show(&mut columns[0], |ui| {
                    ui.set_min_width(ui.available_width());
                    let docs = self.documents.clone();
                    if docs.is_empty() {
                        ui.label(
                            RichText::new("No supported documents in this folder.").color(MUTED),
                        );
                    }
                    for path in docs {
                        let title = path.file_stem().unwrap_or_default().to_string_lossy();
                        let ext = path
                            .extension()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .to_uppercase();
                        let selected = self.document.as_ref().is_some_and(|d| d.path == path);
                        let r = ui.selectable_label(selected, format!("{title}     {ext}"));
                        self.mark(format!("document:{}", path.display()), &r);
                        if r.clicked()
                            && let Err(e) = self.open_document(&path)
                        {
                            self.error = Some(e.to_string());
                        }
                    }
                });
            columns[1].set_min_height(height);
            if let Some(mut doc) = self.document.take() {
                columns[1].heading(doc.path.file_stem().unwrap_or_default().to_string_lossy());
                columns[1].horizontal(|ui| {
                    ui.label(
                        RichText::new(if doc.editable {
                            "TXT · Auto-save"
                        } else {
                            "Read-only preview"
                        })
                        .size(11.)
                        .color(MUTED),
                    );
                    if ui.small_button("Open externally").clicked() {
                        let _ = open::that(&doc.path);
                    }
                    if ui.small_button("Reload from disk").clicked() {
                        self.confirm = Some((
                            "Reload the document from disk and discard unsaved local edits?".into(),
                            Some(Action::Undo(usize::MAX - 1)),
                        ));
                    }
                });
                egui::ScrollArea::vertical()
                    .id_salt("document-content")
                    .max_height(height - 65.)
                    .show(&mut columns[1], |ui| {
                        if doc
                            .path
                            .extension()
                            .is_some_and(|s| s.eq_ignore_ascii_case("pdf"))
                        {
                            self.pdf.ui(ui, &doc.path);
                        } else if doc.path.extension().is_some_and(|s| {
                            s.eq_ignore_ascii_case("md") || s.eq_ignore_ascii_case("markdown")
                        }) {
                            egui_commonmark::CommonMarkViewer::new().show(
                                ui,
                                &mut self.markdown,
                                &doc.text,
                            );
                        } else {
                            let r = ui.add_sized(
                                [ui.available_width(), (height - 80.).max(150.)],
                                egui::TextEdit::multiline(&mut doc.text)
                                    .interactive(doc.editable)
                                    .font(egui::TextStyle::Body)
                                    .desired_width(f32::INFINITY),
                            );
                            self.mark("document-editor", &r);
                            if r.changed() {
                                self.document_dirty_at = Some(Instant::now());
                            }
                        }
                    });
                self.document = Some(doc);
            } else {
                columns[1].add_space(45.);
                columns[1].label(
                    RichText::new("Select a document to read or edit.")
                        .size(18.)
                        .color(MUTED),
                );
            }
        });
    }
    fn context_ui(&mut self, ui: &mut egui::Ui) {
        ui.heading("Agent context");
        ui.label(
            RichText::new(
                "Local discovery. Available and configured do not imply loaded or active.",
            )
            .color(MUTED),
        );
        ui.add_space(10.);
        ui.horizontal(|ui| {
            egui::ComboBox::from_id_salt("context-agent")
                .selected_text(&self.context_agent)
                .show_ui(ui, |ui| {
                    for agent in ["opencode", "codex", "pi", "claude"] {
                        ui.selectable_value(&mut self.context_agent, agent.into(), agent);
                    }
                });
            ui.add(
                egui::TextEdit::singleline(&mut self.context_folder)
                    .hint_text("Working folder")
                    .desired_width(400.),
            );
            if ui.button("Browse…").clicked()
                && let Some(p) = rfd::FileDialog::new().pick_folder()
            {
                self.context_folder = p.display().to_string();
            }
            let r = ui.button("Discover");
            self.mark("discover-context", &r);
            if r.clicked() {
                let (tx, rx) = mpsc::channel();
                self.context_rx = Some(rx);
                let agent = self.context_agent.clone();
                let folder = self.context_folder.clone();
                std::thread::spawn(move || {
                    let _ = tx.send(context::runtime_discover(&agent, Path::new(&folder)));
                });
                self.finding = None;
            }
        });
        ui.horizontal(|ui| {
            for kind in ["Instructions", "Skill", "MCP"] {
                ui.selectable_value(
                    &mut self.context_kind,
                    kind.into(),
                    if kind == "Skill" {
                        "Skills"
                    } else if kind == "MCP" {
                        "MCPs"
                    } else {
                        kind
                    },
                );
            }
        });
        ui.separator();
        let height = ui.available_height();
        ui.columns(2, |col| {
            egui::ScrollArea::vertical()
                .id_salt("context-list")
                .max_height(height)
                .show(&mut col[0], |ui| {
                    for (n, f) in self
                        .findings
                        .iter()
                        .enumerate()
                        .filter(|(_, f)| f.kind == self.context_kind)
                    {
                        let r = ui.selectable_label(
                            self.finding == Some(n),
                            format!("{}\n{} · {}", f.name, f.scope, f.state),
                        );
                        if r.clicked() {
                            self.finding = Some(n);
                        }
                    }
                });
            if let Some(f) = self.finding.and_then(|n| self.findings.get(n)) {
                col[1].heading(&f.name);
                col[1].label(RichText::new(&f.path).size(11.).color(MUTED));
                egui::ScrollArea::vertical()
                    .id_salt("context-preview")
                    .max_height(height - 65.)
                    .show(&mut col[1], |ui| {
                        ui.add(egui::Label::new(&f.content).wrap().selectable(true));
                    });
            }
        });
    }
    fn dialogs(&mut self, ctx: &egui::Context) {
        if self.show_settings {
            let mut open = true;
            egui::Window::new("Settings").open(&mut open).resizable(false).default_width(520.).show(ctx,|ui|{
            ui.heading("Local notebook");ui.label("Data is stored locally. Agent CLIs use their own authentication.");ui.label(self.store.folder.display().to_string());ui.separator();
            ui.label("Default working folder");if ui.text_edit_singleline(&mut self.workdir).changed(){self.book.settings["default_workdir"]=self.workdir.clone().into();self.persist();}
            if ui.button("Choose working folder…").clicked()&& let Some(p)=rfd::FileDialog::new().pick_folder(){self.workdir=p.display().to_string();self.book.settings["default_workdir"]=self.workdir.clone().into();self.persist();}
            ui.separator();for agent in ["opencode","codex","pi","claude"]{ui.horizontal(|ui|{ui.label(RichText::new(agent).strong());ui.label(if agents::executable(agent).is_some(){"Installed"}else{"Not found"});});}
            ui.separator();ui.label(&self.notifications);if ui.button("Test system notification").clicked(){self.notify("GetItDone".into(),"Your local notebook can deliver notifications.".into());}
            if cfg!(target_os="macos")&&ui.button("Open notification settings").clicked(){let _=open::that("x-apple.systempreferences:com.apple.Notifications-Settings.extension");}
            ui.separator();egui::CollapsingHeader::new("Custom agent profiles").show(ui,|ui|{
                ui.label("JSON list with name, executable and args. Arguments are passed directly, without a shell. Do not enter credentials.");ui.add(egui::TextEdit::multiline(&mut self.profiles_json).desired_width(470.).desired_rows(5));
                if ui.button("Apply profiles").clicked(){match parse_profiles(&self.profiles_json){Ok(profiles)=>{self.book.settings["profiles"]=profiles;self.persist();},Err(e)=>self.error=Some(e.to_string())}}
            });
            egui::CollapsingHeader::new("Category names").show(ui,|ui|{let mut changed=false;let mut delete=None;for c in &mut self.book.categories{ui.horizontal(|ui|{changed|=ui.text_edit_singleline(&mut c.name).changed();if ui.small_button("Remove").clicked(){delete=Some(c.id.clone());}});}
if let Some(id)=delete{self.book.categories.retain(|c|c.id!=id);for item in &mut self.book.items{if item.category_id.as_ref()==Some(&id){item.category_id=None;}}changed=true;}
if changed{self.persist();}});
            ui.separator();ui.label("Close window hides it when a tray is available; Quit stops sessions and exits.");
        });
            self.show_settings = open;
        }
        if let Some(item_id) = self.session_dialog.clone() {
            let mut open = true;
            egui::Window::new("New agent session").open(&mut open).collapsible(false).resizable(false).default_width(520.).show(ctx,|ui|{
            ui.label(RichText::new(self.book.item(&item_id).map(|i|i.text.as_str()).unwrap_or("")).strong());ui.add_space(8.);
            ui.horizontal(|ui|{ui.label("Agent");for agent in ["opencode","codex","pi","claude"]{let r=ui.selectable_value(&mut self.session_agent,agent.into(),agent);self.mark(format!("agent:{agent}"),&r);if r.changed(){self.session_model=self.book.settings["agent_models"][agent].as_str().unwrap_or("").to_owned();}}});
            let profiles=self.book.settings["profiles"].as_array().cloned().unwrap_or_default();ui.horizontal_wrapped(|ui|{for p in &profiles{if let(Some(id),Some(name))=(p["id"].as_str(),p["name"].as_str()){ui.selectable_value(&mut self.session_agent,id.to_owned(),name);}}});
            ui.label("Working folder");let r=ui.add(egui::TextEdit::singleline(&mut self.workdir).desired_width(480.));self.mark("session-workdir",&r);if ui.button("Choose folder…").clicked()&& let Some(p)=rfd::FileDialog::new().pick_folder(){self.workdir=p.display().to_string();}
            ui.label("Model (optional; leave empty for the CLI default)");let r=ui.text_edit_singleline(&mut self.session_model);self.mark("session-model",&r);
            ui.label(RichText::new("The item text is copied. Paste and submit it in the terminal.\nResume always uses this conversation's saved native ID.").size(12.).color(MUTED));
            let installed=agents::executable(&self.session_agent).is_some()||profiles.iter().any(|p|p["id"]==self.session_agent&&p["executable"].as_str().and_then(agents::executable).is_some());if !installed{ui.colored_label(Color32::DARK_RED,"CLI not found. Install and authenticate this agent first.");}
            let r=ui.add_enabled(installed&&Path::new(&self.workdir).is_dir(),egui::Button::new("Start session"));self.mark("start-session",&r);if r.clicked(){match self.start_session(&item_id,Some(ctx)){Ok(_)=>{ctx.copy_text(self.book.item(&item_id).map(|i|i.text.clone()).unwrap_or_default());self.session_dialog=None;},Err(e)=>self.error=Some(e.to_string())}}
        });
            if !open {
                self.session_dialog = None;
            }
        }
        if let Some(id) = self.details.clone() {
            let mut open = true;
            let mut changed = false;
            egui::Window::new("Session details")
                .open(&mut open)
                .default_width(520.)
                .show(ctx, |ui| {
                    if let Some(s) = self.book.sessions.iter_mut().find(|s| s.id == id) {
                        ui.label(format!("Agent: {}", s.agent));
                        ui.label(format!("Working folder: {}", s.workdir));
                        ui.label("Label");
                        changed |= ui.text_edit_singleline(&mut s.title).changed();
                        ui.label("Exact native session ID");
                        let native = s.native_session_id.get_or_insert_default();
                        changed |= ui.text_edit_singleline(native).changed();
                        ui.label("No 'latest session' fallback is used.");
                    }
                });
            if changed {
                self.persist();
            }
            if !open {
                self.details = None;
            }
        }
        if let Some(id) = self.reminder.clone() {
            let mut open = true;
            egui::Window::new("Reminder").open(&mut open).resizable(false).show(ctx,|ui|{
            ui.label("Local date and time (YYYY-MM-DD HH:MM)");let r=ui.text_edit_singleline(&mut self.reminder_at);self.mark("reminder-date",&r);ui.horizontal(|ui|{
                let r=ui.button("Save");self.mark("save-reminder",&r);if r.clicked(){use chrono::TimeZone;match chrono::NaiveDateTime::parse_from_str(&self.reminder_at,"%Y-%m-%d %H:%M").ok().and_then(|d|chrono::Local.from_local_datetime(&d).single()){Some(at)=>{if let Some(i)=self.book.item_mut(&id){i.reminder=Some(serde_json::json!({"at":at.to_rfc3339(),"notified_at":null}));}self.persist();self.reminder=None;},None=>self.error=Some("Enter an unambiguous local date and time in YYYY-MM-DD HH:MM format.".into())}}
                let r=ui.button("Remove reminder");self.mark("remove-reminder",&r);if r.clicked(){if let Some(i)=self.book.item_mut(&id){i.reminder=None;}self.persist();self.reminder=None;}
            });});
            if !open {
                self.reminder = None;
            }
        }
        if let Some((message, action)) = self.confirm.clone() {
            egui::Window::new("Confirm")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0., 0.])
                .show(ctx, |ui| {
                    ui.set_max_width(440.);
                    ui.label(message);
                    ui.horizontal(|ui| {
                        let r = ui.button("Continue");
                        self.mark("confirm", &r);
                        if r.clicked() {
                            self.confirm = None;
                            if let Some(action) = action {
                                if matches!(action,Action::Undo(n) if n==usize::MAX-1) {
                                    if let Some(path) =
                                        self.document.as_ref().map(|d| d.path.clone())
                                    {
                                        match Document::open(&path) {
                                            Ok(d) => {
                                                self.document = Some(d);
                                                self.document_dirty_at = None;
                                            }
                                            Err(e) => self.error = Some(e.to_string()),
                                        }
                                    }
                                } else if let Err(e) = self.execute(action, Some(ctx)) {
                                    self.error = Some(e.to_string());
                                }
                            } else {
                                self.finish_quit();
                            }
                        }
                        let r = ui.button("Cancel");
                        self.mark("cancel-confirm", &r);
                        if r.clicked() {
                            self.confirm = None;
                        }
                    });
                });
        }
        if let Some(error) = self.error.clone() {
            egui::Window::new("Attention")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0., -100.])
                .show(ctx, |ui| {
                    ui.set_max_width(500.);
                    ui.colored_label(Color32::DARK_RED, error);
                    let r = ui.button("OK");
                    self.mark("dismiss-error", &r);
                    if r.clicked() {
                        self.error = None;
                    }
                });
        }
    }
}
impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.draw(ctx);
    }
    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        let _ = self.save_document();
        self.persist();
        self.terminals.clear();
    }
}
pub fn hex(s: &str) -> Option<Color32> {
    let n = u32::from_str_radix(s.strip_prefix('#')?, 16).ok()?;
    Some(Color32::from_rgb((n >> 16) as u8, (n >> 8) as u8, n as u8))
}
fn urls(text: &str) -> Vec<String> {
    text.split_whitespace()
        .filter_map(|s| {
            let start = s.find("https://").or_else(|| s.find("http://"))?;
            Some(
                s[start..]
                    .trim_end_matches([')', ']', '>', ',', '.'])
                    .to_owned(),
            )
        })
        .collect()
}

fn parse_profiles(text: &str) -> Result<serde_json::Value> {
    let mut value: serde_json::Value = serde_json::from_str(text)?;
    let profiles = value
        .as_array_mut()
        .ok_or_else(|| anyhow::anyhow!("Profiles must be a JSON list"))?;
    let mut seen: HashSet<String> = ["opencode", "codex", "pi", "claude"]
        .iter()
        .map(|s| s.to_string())
        .collect();
    for p in profiles {
        anyhow::ensure!(
            p["name"].as_str().is_some_and(|s| !s.trim().is_empty())
                && p["executable"]
                    .as_str()
                    .is_some_and(|s| !s.trim().is_empty())
                && p["args"]
                    .as_array()
                    .is_some_and(|a| a.iter().all(|v| v.is_string())),
            "Each profile needs name, executable and args (a list of strings)"
        );
        if p.get("id").is_none() {
            p["id"] = format!("custom-{}", uid()).into();
        }
        let id = p["id"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("Profile ID must be text"))?;
        anyhow::ensure!(
            seen.insert(id.into()),
            "Profile IDs must be unique and cannot replace a built-in agent"
        );
    }
    Ok(value)
}
