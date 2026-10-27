use eframe::egui::{self, Event, Key, Modifiers, PointerButton, Pos2, RawInput, Rect, Vec2};
use getitdone::{
    knowledge::{self, Document},
    model::Notebook,
    storage::Store,
    terminal::{Terminal, encode_key},
    ui::{Action, App},
};
use std::{
    fs,
    path::Path,
    time::{Duration, Instant},
};

fn app() -> (tempfile::TempDir, App) {
    let temp = tempfile::tempdir().unwrap();
    let (store, book) = Store::open(temp.path().join("data")).unwrap();
    (temp, App::new(store, book))
}
struct Driver {
    ctx: egui::Context,
    time: f64,
}
impl Driver {
    fn new() -> Self {
        let ctx = egui::Context::default();
        App::style(&ctx);
        Self { ctx, time: 0. }
    }
    fn frame(&mut self, app: &mut App, events: Vec<Event>) {
        self.time += 0.02;
        let input = RawInput {
            screen_rect: Some(Rect::from_min_size(Pos2::ZERO, Vec2::new(1440., 1000.))),
            time: Some(self.time),
            events,
            focused: true,
            ..Default::default()
        };
        let _ = self.ctx.run(input, |ctx| app.draw(ctx));
    }
    fn settle(&mut self, app: &mut App) {
        for _ in 0..3 {
            self.frame(app, vec![]);
        }
    }
    fn click(&mut self, app: &mut App, name: &str) {
        self.settle(app);
        let rect = *app.widgets.get(name).unwrap_or_else(|| {
            panic!("Missing widget {name}; available: {:?}", app.widgets.keys())
        });
        let p = rect.center();
        self.frame(
            app,
            vec![
                Event::PointerMoved(p),
                Event::PointerButton {
                    pos: p,
                    button: PointerButton::Primary,
                    pressed: true,
                    modifiers: Modifiers::NONE,
                },
            ],
        );
        self.frame(
            app,
            vec![Event::PointerButton {
                pos: p,
                button: PointerButton::Primary,
                pressed: false,
                modifiers: Modifiers::NONE,
            }],
        );
        self.settle(app);
    }
    fn text(&mut self, app: &mut App, text: &str) {
        self.frame(app, vec![Event::Text(text.into())]);
        self.settle(app);
    }
    fn key(&mut self, app: &mut App, key: Key) {
        self.frame(
            app,
            vec![Event::Key {
                key,
                physical_key: Some(key),
                pressed: true,
                repeat: false,
                modifiers: Modifiers::NONE,
            }],
        );
        self.frame(
            app,
            vec![Event::Key {
                key,
                physical_key: Some(key),
                pressed: false,
                repeat: false,
                modifiers: Modifiers::NONE,
            }],
        );
        self.settle(app);
    }
}
#[test]
fn ui_create_parent_child_delete_complete_undo_and_notes() {
    let (_temp, mut app) = app();
    let mut d = Driver::new();
    d.click(&mut app, "add-item");
    d.text(&mut app, "Release checklist");
    d.key(&mut app, Key::Escape);
    let parent = app.book.items[0].id.clone();
    assert_eq!(app.book.item(&parent).unwrap().text, "Release checklist");
    d.click(&mut app, &format!("more:{parent}"));
    d.click(&mut app, &format!("menu:Add child:{parent}"));
    d.text(&mut app, "Check exact session resume");
    d.key(&mut app, Key::Escape);
    let child = app.book.children(Some(&parent))[0].clone();
    assert_eq!(
        app.book.item(&child).unwrap().text,
        "Check exact session resume"
    );
    d.click(&mut app, &format!("note:{child}"));
    d.click(&mut app, &format!("note-editor:{child}"));
    d.text(&mut app, "Keep this task note\nwith two lines");
    assert!(app.book.item(&child).unwrap().notes.contains("two lines"));
    d.click(&mut app, &format!("delete-note:{child}"));
    assert!(app.book.item(&child).unwrap().notes.is_empty());
    d.click(&mut app, "undo:0");
    assert!(app.book.item(&child).unwrap().notes.contains("two lines"));
    d.click(&mut app, &format!("complete:{parent}"));
    assert!(app.book.item(&parent).unwrap().done && app.book.item(&child).unwrap().done);
    d.click(&mut app, "undo:0");
    assert!(!app.book.item(&parent).unwrap().done && !app.book.item(&child).unwrap().done);
    d.click(&mut app, &format!("more:{child}"));
    d.click(&mut app, &format!("menu:Delete item:{child}"));
    assert!(app.book.item(&child).is_none());
    let raw = fs::read(app.store.folder.join("notebook.json")).unwrap();
    let persisted: Notebook = serde_json::from_slice(&raw).unwrap();
    persisted.validate().unwrap();
    assert_eq!(persisted.items.len(), 1);
}
#[test]
fn ui_knowledge_import_titles_content_edit_and_create() {
    let (temp, mut app) = app();
    let folder = temp.path().join("notes");
    fs::create_dir(&folder).unwrap();
    for (name, text) in [
        ("Meeting notes", "Decisions\nOwner: Oliver"),
        ("Memory", "Remember the release token"),
        ("Überblick", "Äpfel, Öl und Grüße"),
        ("Empty", ""),
    ] {
        fs::write(folder.join(format!("{name}.txt")), text).unwrap();
    }
    fs::write(folder.join("ignored.bin"), b"ignore").unwrap();
    fs::create_dir(folder.join("nested")).unwrap();
    fs::write(folder.join("nested/hidden.txt"), "not top-level").unwrap();
    app.set_folder(folder.display().to_string()).unwrap();
    assert_eq!(app.documents.len(), 4);
    let mut d = Driver::new();
    d.click(&mut app, "tab:Knowledge");
    for (name, text) in [
        ("Meeting notes", "Decisions\nOwner: Oliver"),
        ("Memory", "Remember the release token"),
        ("Überblick", "Äpfel, Öl und Grüße"),
        ("Empty", ""),
    ] {
        let p = folder.join(format!("{name}.txt"));
        d.click(&mut app, &format!("document:{}", p.display()));
        assert_eq!(app.document.as_ref().unwrap().text, text);
    }
    let p = folder.join("Memory.txt");
    d.click(&mut app, &format!("document:{}", p.display()));
    d.click(&mut app, "document-editor");
    d.text(&mut app, " updated");
    app.save_document().unwrap();
    assert!(fs::read_to_string(&p).unwrap().contains("updated"));
    d.click(&mut app, "new-note-title");
    d.text(&mut app, "New real file");
    d.click(&mut app, "new-note");
    assert!(folder.join("New real file.txt").exists());
    assert_eq!(app.documents.len(), 5);
}
#[test]
fn mixed_completion_undo_preserves_later_edits() {
    let mut b = Notebook::default();
    let p = b.add("Parent", None, None).unwrap();
    let c = b.add("Child", Some(p.clone()), None).unwrap();
    let g = b.add("Done grandchild", Some(c.clone()), None).unwrap();
    b.complete(&g, true);
    let undo = b.complete(&p, true);
    b.item_mut(&c).unwrap().text = "Later change".into();
    b.restore_completion(&undo);
    assert!(!b.item(&p).unwrap().done && !b.item(&c).unwrap().done && b.item(&g).unwrap().done);
    assert_eq!(b.item(&c).unwrap().text, "Later change");
    b.complete(&g, false);
    assert!(!b.item(&p).unwrap().done);
}
#[test]
fn atomic_store_lock_backup_and_invalid_version() {
    let (temp, mut app) = app();
    app.execute(Action::Add(None), None).unwrap();
    assert!(Store::open(app.store.folder.clone()).is_err());
    app.book.items[0].text = "Updated".into();
    app.persist();
    let old: Notebook =
        serde_json::from_slice(&fs::read(app.store.folder.join("notebook.backup.json")).unwrap())
            .unwrap();
    assert_eq!(old.items[0].text, "");
    let folder = app.store.folder.clone();
    drop(app);
    let (_, book) = Store::open(folder).unwrap();
    assert_eq!(book.items[0].text, "Updated");
    let corrupt = temp.path().join("future");
    fs::create_dir(&corrupt).unwrap();
    let raw = r#"{"schema_version":99,"settings":{},"categories":[],"items":[],"sessions":[]}"#;
    fs::write(corrupt.join("notebook.json"), raw).unwrap();
    assert!(Store::open(corrupt.clone()).is_err());
    assert_eq!(
        fs::read_to_string(corrupt.join("notebook.json")).unwrap(),
        raw
    );
}
#[test]
fn conflict_does_not_overwrite_and_utf16_roundtrips() {
    let t = tempfile::tempdir().unwrap();
    let p = knowledge::create(t.path(), "Original", "Before").unwrap();
    let mut d = Document::open(&p).unwrap();
    d.text = "Local change".into();
    fs::write(&p, "External change").unwrap();
    assert!(d.save().is_err());
    assert_eq!(d.text, "Local change");
    assert_eq!(fs::read_to_string(&p).unwrap(), "External change");
    assert!(knowledge::create(t.path(), "Original", "Never overwrite").is_err());
    for bad in ["../bad", "CON", "LPT1", "trailing.", " bad", "bad/name"] {
        assert!(knowledge::validate_title(bad).is_err());
    }
    let p = t.path().join("utf16.txt");
    let mut raw = vec![255, 254];
    for w in "Grüße".encode_utf16() {
        raw.extend(w.to_le_bytes());
    }
    fs::write(&p, raw).unwrap();
    let mut d = Document::open(&p).unwrap();
    assert_eq!(d.text, "Grüße");
    d.text.push('!');
    d.save().unwrap();
    assert_eq!(Document::open(&p).unwrap().text, "Grüße!");
}
#[test]
fn ui_palette_and_reminder_save_remove() {
    let (_t, mut app) = app();
    let id = app.book.add("Colored task", None, None).unwrap();
    let mut d = Driver::new();
    for (name, _) in getitdone::ui::PALETTE {
        d.click(&mut app, &format!("palette:{id}"));
        d.click(&mut app, &format!("color:{id}:{name}"));
        assert!(app.book.item(&id).unwrap().category_id.is_some());
    }
    d.click(&mut app, &format!("reminder:{id}"));
    d.click(&mut app, "save-reminder");
    assert!(app.book.item(&id).unwrap().reminder.is_some());
    d.click(&mut app, &format!("reminder:{id}"));
    d.click(&mut app, "remove-reminder");
    assert!(app.book.item(&id).unwrap().reminder.is_none());
}
#[test]
fn context_inspector_redacts_config_and_lists_skills() {
    let t = tempfile::tempdir().unwrap();
    fs::write(t.path().join("AGENTS.md"), "Project instructions").unwrap();
    fs::create_dir_all(t.path().join(".agents/skills/example")).unwrap();
    fs::write(
        t.path().join(".agents/skills/example/SKILL.md"),
        "Example skill",
    )
    .unwrap();
    fs::write(
        t.path().join("opencode.jsonc"),
        r#"{// comment
"mcp":{"private":{"command":["secret-command"],"environment":{"TOKEN":"DO_NOT_LEAK"}}},}"#,
    )
    .unwrap();
    let f = getitdone::context::discover("opencode", t.path());
    assert!(
        f.iter()
            .any(|f| f.kind == "Instructions" && f.content == "Project instructions")
    );
    assert!(f.iter().any(|f| f.kind == "Skill" && f.name == "example"));
    let m = f
        .iter()
        .find(|f| f.kind == "MCP" && f.name == "private")
        .unwrap();
    assert!(!m.content.contains("secret-command") && !m.content.contains("DO_NOT_LEAK"));
}
#[test]
fn terminal_is_real_pty_and_handles_ansi_input_and_shutdown() {
    let t = tempfile::tempdir().unwrap();
    let args = if cfg!(windows) {
        vec![
            "cmd.exe".into(),
            "/Q".into(),
            "/D".into(),
            "/V:ON".into(),
            "/C".into(),
            "echo PTY_READY&set /p line=&echo ECHO:!line!&ping -n 20 127.0.0.1 >nul".into(),
        ]
    } else {
        vec!["/bin/sh".into(),"-c".into(),"test -t 0 && printf '\x1b[32mPTY_READY\x1b[0m\\n'; read line; printf 'ECHO:%s\\n' \"$line\"; sleep 20".into()]
    };
    let mut term = Terminal::spawn(&args, t.path(), None, None).unwrap();
    wait(
        || term.contents().contains("PTY_READY"),
        Duration::from_secs(5),
    );
    term.write(b"hello\r").unwrap();
    wait(
        || term.contents().contains("ECHO:hello"),
        Duration::from_secs(5),
    );
    term.stop();
    assert!(!term.alive);
    assert_eq!(encode_key(Key::C, Modifiers::CTRL, false), vec![3]);
    assert_eq!(encode_key(Key::ArrowUp, Modifiers::NONE, true), b"\x1bOA");
}
fn wait(mut condition: impl FnMut() -> bool, timeout: Duration) {
    let start = Instant::now();
    while !condition() {
        assert!(start.elapsed() < timeout, "Timed out");
        std::thread::sleep(Duration::from_millis(50));
    }
}

#[test]
#[ignore = "Starts installed, authenticated agent CLIs and sends real model prompts"]
fn live_agents_prompt_status_close_and_exact_resume() {
    let (temp, mut app) = app();
    let mut d = Driver::new();
    d.click(&mut app, "add-item");
    d.text(&mut app, "GetItDone E2E session retention");
    d.key(&mut app, Key::Escape);
    let parent = app.book.items[0].id.clone();
    d.click(&mut app, &format!("more:{parent}"));
    d.click(&mut app, &format!("menu:Add child:{parent}"));
    d.text(&mut app, "Three real coding agents");
    d.key(&mut app, Key::Escape);
    let child = app.book.children(Some(&parent))[0].clone();
    let artifacts = Path::new("tests/artifacts");
    fs::create_dir_all(artifacts).unwrap();
    let mut report = vec![];
    let mut cases = vec![];
    for agent in ["opencode", "codex", "pi"].into_iter().filter(|a| {
        std::env::var("GETITDONE_E2E_AGENT")
            .map(|v| v.split(',').any(|x| x == *a))
            .unwrap_or(true)
    }) {
        let cwd = temp.path().join(agent);
        fs::create_dir(&cwd).unwrap();
        d.click(&mut app, &format!("session:{child}"));
        d.click(&mut app, &format!("agent:{agent}"));
        app.workdir = cwd.display().to_string();
        app.session_model = if agent == "pi" {
            std::env::var("GETITDONE_E2E_PI_MODEL").unwrap_or_default()
        } else {
            String::new()
        };
        d.click(&mut app, "start-session");
        assert!(app.error.is_none(), "{:?}", app.error);
        let id = app.book.sessions.last().unwrap().id.clone();
        let start = Instant::now();
        let mut trusted = false;
        loop {
            app.tick(None);
            let text = app.terminals[&id].contents();
            if !trusted && (text.to_lowercase().contains("trust") || text.contains("allow access"))
            {
                app.terminals.get_mut(&id).unwrap().write(b"\r").unwrap();
                trusted = true;
            }
            if start.elapsed() > Duration::from_secs(12) {
                break;
            }
            std::thread::sleep(Duration::from_millis(150));
        }
        fs::write(
            artifacts.join(format!("{agent}-startup.txt")),
            app.terminals[&id].contents(),
        )
        .unwrap();
        let token = format!("GID_{}", &getitdone::model::uid().replace('-', "")[..10]);
        let prompt = format!(
            "Remember the token {token} for this conversation. Reply exactly: STORED {token}. Do not use tools or change files."
        );
        d.click(&mut app, "terminal-surface");
        d.frame(&mut app, vec![Event::Paste(prompt)]);
        d.key(&mut app, Key::Enter);
        let mut working = false;
        let mut ready = false;
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(180) {
            app.tick(None);
            let a = app.activity.get(&id);
            if a.is_some_and(|a| a.state == "Working") {
                working = true;
            }
            if a.is_some_and(|a| a.state == "Failed") {
                break;
            }
            if a.is_some_and(|a| a.state == "Ready" && a.message.is_some()) {
                ready = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(150));
        }
        fs::write(
            artifacts.join(format!("{agent}-first.txt")),
            app.terminals[&id].raw_text(),
        )
        .unwrap();
        assert!(
            ready,
            "{agent} did not finish: {:?}; screen: {}",
            app.activity.get(&id),
            app.terminals[&id].contents()
        );
        let session = app
            .book
            .sessions
            .iter()
            .find(|s| s.id == id)
            .unwrap()
            .clone();
        let native = session
            .native_session_id
            .clone()
            .expect("Native session ID must be persisted");
        assert!(working, "{agent} did not report Working before Ready");
        assert_eq!(latest_reply(&session).trim(), format!("STORED {token}"));
        cases.push((agent.to_owned(), id, native, token, working));
    }
    assert_eq!(app.terminals.len(), cases.len());
    for (_, id, _, _, _) in &cases {
        d.click(&mut app, &format!("close-terminal:{id}"));
        d.click(&mut app, "confirm");
    }
    assert!(app.terminals.is_empty());
    assert_eq!(app.book.sessions.len(), cases.len());
    for (agent, id, native, token, working) in cases {
        d.click(&mut app, &format!("resume:{id}"));
        assert!(app.error.is_none(), "Resume {agent}: {:?}", app.error);
        std::thread::sleep(Duration::from_secs(8));
        let old_message = app.activity.get(&id).and_then(|a| a.message.clone());
        d.click(&mut app, "terminal-surface");
        d.frame(&mut app,vec![Event::Paste("What exact token did I ask you to remember? Reply only with that token. Do not use tools.".into())]);
        d.key(&mut app, Key::Enter);
        let started = Instant::now();
        let mut resumed = false;
        while started.elapsed() < Duration::from_secs(180) {
            app.tick(None);
            if app.activity.get(&id).is_some_and(|a| {
                a.state == "Ready" && a.message.is_some() && a.message != old_message
            }) {
                resumed = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(150));
        }
        fs::write(
            artifacts.join(format!("{agent}-resumed.txt")),
            app.terminals[&id].raw_text(),
        )
        .unwrap();
        assert!(
            resumed,
            "{agent} resume did not reply: {}",
            app.terminals[&id].contents()
        );
        let resumed_session = app.book.sessions.iter().find(|s| s.id == id).unwrap();
        assert_eq!(
            latest_reply(resumed_session).trim(),
            token,
            "Resumed {agent} lost conversation token"
        );
        assert_eq!(
            app.book
                .sessions
                .iter()
                .find(|s| s.id == id)
                .unwrap()
                .native_session_id
                .as_ref(),
            Some(&native)
        );
        report.push(serde_json::json!({"agent":agent,"native_id":native,"saw_working":working,"ready":true,"resume_recalled_token":true}));
        fs::write(
            artifacts.join(format!("{agent}-report.json")),
            serde_json::to_vec_pretty(report.last().unwrap()).unwrap(),
        )
        .unwrap();
        d.click(&mut app, &format!("close-terminal:{id}"));
        d.click(&mut app, "confirm");
    }
    fs::write(
        artifacts.join("live-report.json"),
        serde_json::to_vec_pretty(&report).unwrap(),
    )
    .unwrap();
    d.click(&mut app, &format!("more:{parent}"));
    d.click(&mut app, &format!("menu:Delete item:{parent}"));
    assert!(app.book.items.is_empty() && app.book.sessions.is_empty() && app.terminals.is_empty());
    d.click(&mut app, "add-item");
    d.text(&mut app, "Keep after undo");
    d.key(&mut app, Key::Escape);
    let id = app.book.items[0].id.clone();
    d.click(&mut app, &format!("complete:{id}"));
    assert!(app.book.item(&id).unwrap().done);
    d.click(&mut app, "undo:0");
    assert!(!app.book.item(&id).unwrap().done);
}

#[test]
fn document_previews_include_docx_text_and_render_pdf_page() {
    use std::io::Write;
    let t = tempfile::tempdir().unwrap();
    let path = t.path().join("notes.docx");
    let mut zip = zip::ZipWriter::new(fs::File::create(&path).unwrap());
    zip.start_file(
        "word/document.xml",
        zip::write::SimpleFileOptions::default(),
    )
    .unwrap();
    zip.write_all(br#"<w:document xmlns:w="urn:test"><w:p><w:r><w:t>Document title</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:document>"#).unwrap();
    zip.finish().unwrap();
    let d = Document::open(&path).unwrap();
    assert!(!d.editable && d.text.contains("Document title") && d.text.contains("Table cell"));
    let path = t.path().join("page.pdf");
    let objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 150] /Resources << >> /Contents 4 0 R >>",
        "<< /Length 30 >>\nstream\n0 0 1 rg 20 20 80 80 re f\nendstream",
    ];
    let mut pdf = String::from("%PDF-1.4\n");
    let mut offsets = vec![0];
    for (n, object) in objects.iter().enumerate() {
        offsets.push(pdf.len());
        pdf.push_str(&format!("{} 0 obj\n{}\nendobj\n", n + 1, object));
    }
    let xref = pdf.len();
    pdf.push_str("xref\n0 5\n0000000000 65535 f \n");
    for offset in &offsets[1..] {
        pdf.push_str(&format!("{offset:010} 00000 n \n"));
    }
    pdf.push_str(&format!(
        "trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ));
    fs::write(&path, pdf).unwrap();
    let (count, image) = getitdone::pdf::render(&path, 0).unwrap();
    assert_eq!(count, 1);
    assert!(image.size[0] > 0 && image.size[1] > 0);
    assert!(image.pixels.iter().any(|c| c.b() > 200 && c.r() < 100));
}
#[test]
fn status_is_from_events_and_failed_pi_event_is_preserved() {
    let t = tempfile::tempdir().unwrap();
    let p = t.path().join("codex.jsonl");
    fs::write(
        &p,
        "{\"type\":\"event_msg\",\"payload\":{\"type\":\"task_started\"}}\n",
    )
    .unwrap();
    assert_eq!(
        getitdone::agents::log_activity(&p).unwrap().state,
        "Working"
    );
    use std::io::Write;
    let mut f = fs::OpenOptions::new().append(true).open(&p).unwrap();
    writeln!(f,"{}",serde_json::json!({"type":"event_msg","timestamp":"2026-10-27T10:00:00Z","payload":{"type":"task_complete"}})).unwrap();
    let a = getitdone::agents::log_activity(&p).unwrap();
    assert_eq!(a.state, "Ready");
    assert!(a.message.is_some());
    writeln!(
        f,
        "{}",
        serde_json::json!({"type":"event_msg","payload":{"type":"turn_aborted"}})
    )
    .unwrap();
    assert_eq!(
        getitdone::agents::log_activity(&p).unwrap().state,
        "Interrupted"
    );
}
#[test]
fn old_notebook_format_remains_compatible_and_unknown_hierarchy_is_rejected() {
    let mut b = Notebook::default();
    let p = b.add("Legacy", None, None).unwrap();
    b.settings["custom_setting"] = serde_json::json!({"keep":"yes"});
    let mut value = serde_json::to_value(&b).unwrap();
    value["sessions"] = serde_json::json!([{"id":"session-old","item_id":p,"agent":"pi","workdir":"/tmp","title":"Old session","native_session_id":"native-exact-id","created_at":"2026-10-26T10:00:00Z"}]);
    let b: Notebook = serde_json::from_value(value.clone()).unwrap();
    b.validate().unwrap();
    assert_eq!(
        b.sessions[0].native_session_id.as_deref(),
        Some("native-exact-id")
    );
    assert_eq!(b.settings["custom_setting"]["keep"], "yes");
    value["items"][0]["parent_id"] = p.into();
    let b: Notebook = serde_json::from_value(value).unwrap();
    assert!(b.validate().is_err());
}
#[test]
fn deleting_and_readding_does_not_duplicate_positions() {
    let mut b = Notebook::default();
    let a = b.add("A", None, None).unwrap();
    let middle = b.add("Middle", None, None).unwrap();
    let c = b.add("C", None, None).unwrap();
    b.delete(&middle);
    let d = b.add("D", None, None).unwrap();
    assert_eq!(b.children(None), vec![a, c, d]);
    assert_eq!(
        b.items.iter().map(|i| i.position).collect::<Vec<_>>(),
        vec![0, 1, 2]
    );
}
fn latest_reply(session: &getitdone::model::Session) -> String {
    use serde_json::Value;
    let id = session.native_session_id.as_deref().unwrap();
    if session.agent == "opencode" {
        let messages = getitdone::agents::opencode_api(
            "session.message.list",
            &[
                format!("sessionID={id}"),
                "limit=20".into(),
                "order=desc".into(),
            ],
        )
        .unwrap();
        let m = messages
            .as_array()
            .unwrap()
            .iter()
            .find(|m| m["type"] == "assistant")
            .unwrap();
        return m["content"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|p| p["text"].as_str())
            .collect::<Vec<_>>()
            .join("");
    }
    if session.agent == "codex" {
        let p = getitdone::agents::codex_log(session).unwrap();
        return fs::read_to_string(p)
            .unwrap()
            .lines()
            .filter_map(|l| serde_json::from_str::<Value>(l).ok())
            .rfind(|v| v["type"] == "event_msg" && v["payload"]["type"] == "task_complete")
            .unwrap()["payload"]["last_agent_message"]
            .as_str()
            .unwrap()
            .into();
    }
    let root = std::env::var_os("PI_CODING_AGENT_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or(getitdone::agents::home().join(".pi/agent"))
        .join("sessions");
    for e in walkdir::WalkDir::new(root)
        .into_iter()
        .filter_map(Result::ok)
        .filter(|e| e.file_type().is_file() && e.file_name().to_string_lossy().contains(id))
    {
        let text = fs::read_to_string(e.path()).unwrap();
        if let Some(v) = text
            .lines()
            .filter_map(|l| serde_json::from_str::<Value>(l).ok())
            .rfind(|v| v["type"] == "message" && v["message"]["role"] == "assistant")
        {
            return v["message"]["content"]
                .as_array()
                .unwrap()
                .iter()
                .filter_map(|p| p["text"].as_str())
                .collect::<Vec<_>>()
                .join("");
        }
    }
    panic!("pi session log not found for {id}");
}

#[test]
fn quit_saves_pending_note_and_releases_notebook_lock() {
    let (temp, mut app) = app();
    let notes = temp.path().join("notes");
    fs::create_dir(&notes).unwrap();
    let path = knowledge::create(&notes, "Draft", "Before").unwrap();
    app.set_folder(notes.display().to_string()).unwrap();
    app.open_document(&path).unwrap();
    app.document.as_mut().unwrap().text = "Saved on quit".into();
    let mut d = Driver::new();
    d.click(&mut app, "quit");
    assert!(app.quit);
    assert!(app.confirm.is_none());
    assert_eq!(fs::read_to_string(&path).unwrap(), "Saved on quit");
    let folder = app.store.folder.clone();
    drop(app);
    assert!(Store::open(folder).is_ok());
}
#[test]
fn quit_preserves_conflicting_draft_and_leaves_app_open() {
    let (temp, mut app) = app();
    let notes = temp.path().join("notes");
    fs::create_dir(&notes).unwrap();
    let path = knowledge::create(&notes, "Conflict", "Before").unwrap();
    app.set_folder(notes.display().to_string()).unwrap();
    app.open_document(&path).unwrap();
    app.document.as_mut().unwrap().text = "Unsaved draft".into();
    fs::write(&path, "External edit").unwrap();
    let mut d = Driver::new();
    d.click(&mut app, "quit");
    assert!(!app.quit);
    assert!(app.error.as_ref().unwrap().contains("externally"));
    assert_eq!(app.document.as_ref().unwrap().text, "Unsaved draft");
    assert_eq!(fs::read_to_string(&path).unwrap(), "External edit");
}
#[test]
fn quit_with_running_terminal_can_cancel_then_shut_down() {
    let (temp, mut app) = app();
    let args = if cfg!(windows) {
        vec![
            "cmd.exe".into(),
            "/C".into(),
            "ping -n 30 127.0.0.1 >nul".into(),
        ]
    } else {
        vec!["/bin/sh".into(), "-c".into(), "sleep 30".into()]
    };
    let terminal = Terminal::spawn(&args, temp.path(), None, None).unwrap();
    app.terminals.insert("quit-test".into(), terminal);
    app.show_terminal = false;
    let mut d = Driver::new();
    d.click(&mut app, "quit");
    assert!(!app.quit && app.confirm.is_some());
    d.click(&mut app, "cancel-confirm");
    assert!(app.terminals["quit-test"].alive && !app.quit);
    d.click(&mut app, "quit");
    d.click(&mut app, "confirm");
    assert!(app.quit && app.terminals.is_empty());
}
