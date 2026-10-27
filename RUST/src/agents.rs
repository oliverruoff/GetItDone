use crate::model::Session;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs,
    io::{BufRead, BufReader, Read, Seek, SeekFrom},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

pub fn home() -> PathBuf {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_default()
}
pub fn executable(name: &str) -> Option<PathBuf> {
    let mut roots: Vec<PathBuf> =
        std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()).collect();
    roots.extend([
        home().join(".local/bin"),
        home().join(".npm-global/bin"),
        PathBuf::from("/opt/homebrew/bin"),
        PathBuf::from("/usr/local/bin"),
    ]);
    if name == "codex" {
        let p = PathBuf::from(
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
        );
        if p.is_file() {
            return Some(p);
        }
    }
    if let Some(a) = std::env::var_os("APPDATA") {
        roots.push(PathBuf::from(a).join("npm"));
    }
    for root in roots {
        for suffix in if cfg!(windows) {
            vec![".exe", ".cmd", ""]
        } else {
            vec![""]
        } {
            let path = root.join(format!("{name}{suffix}"));
            if path.is_file() {
                return Some(path);
            }
        }
    }
    None
}
pub fn augmented_path() -> std::ffi::OsString {
    let mut roots: Vec<PathBuf> =
        std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()).collect();
    roots.extend([
        home().join(".local/bin"),
        home().join(".npm-global/bin"),
        PathBuf::from("/opt/homebrew/bin"),
        PathBuf::from("/usr/local/bin"),
        PathBuf::from("/usr/bin"),
        PathBuf::from("/bin"),
    ]);
    if let Some(a) = std::env::var_os("APPDATA") {
        roots.push(PathBuf::from(a).join("npm"));
    }
    std::env::join_paths(roots).unwrap_or_default()
}
pub fn command(session: &Session, resume: bool) -> Result<Vec<String>> {
    let exe = executable(&session.agent)
        .context("Agent CLI not found. Install and authenticate it first.")?;
    let mut args = vec![exe.to_string_lossy().into_owned()];
    if resume {
        let id = session
            .native_session_id
            .as_deref()
            .context("Native session ID is not known yet. Set it in Details before resuming.")?;
        ensure!(
            !id.is_empty() && !id.starts_with('-') && !id.chars().any(char::is_control),
            "Invalid native session ID"
        );
        args.extend(match session.agent.as_str() {
            "codex" => vec!["resume".into(), id.into()],
            "claude" => vec!["--resume".into(), id.into()],
            _ => vec!["--session".into(), id.into()],
        });
    } else if let Some(id) = &session.native_session_id {
        args.extend([
            if session.agent == "opencode" {
                "--session".into()
            } else {
                "--session-id".into()
            },
            id.clone(),
        ]);
    }
    Ok(args)
}
// Deadlines prevent a stalled CLI from occupying status workers indefinitely.
pub fn output_timeout(args: &[String], cwd: Option<&Path>, timeout: Duration) -> Result<Vec<u8>> {
    let mut cmd = Command::new(&args[0]);
    cmd.args(&args[1..])
        .env("PATH", augmented_path())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    if let Some(p) = cwd {
        cmd.current_dir(p);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let mut child = cmd.spawn()?;
    let stdout = child.stdout.take().unwrap();
    let reader = std::thread::spawn(move || {
        let mut b = vec![];
        stdout.take(8 * 1024 * 1024).read_to_end(&mut b).map(|_| b)
    });
    let start = Instant::now();
    loop {
        if let Some(status) = child.try_wait()? {
            ensure!(status.success(), "Agent status command failed");
            return Ok(reader
                .join()
                .map_err(|_| anyhow::anyhow!("Reader failed"))??);
        }
        if start.elapsed() > timeout {
            let _ = child.kill();
            let _ = child.wait();
            anyhow::bail!("Agent status timed out");
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Activity {
    pub state: String,
    pub message: Option<String>,
    pub source: String,
}
impl Activity {
    pub fn unknown() -> Self {
        Self {
            state: "Status unavailable".into(),
            message: None,
            source: "No agent event received".into(),
        }
    }
}
pub fn pi_extension(folder: &Path) -> Result<PathBuf> {
    fs::create_dir_all(folder)?;
    let path = folder.join("getitdone-status.ts");
    fs::write(&path, include_str!("pi-status.ts"))?;
    Ok(path)
}
pub fn pi_status_path(folder: &Path, id: &str) -> PathBuf {
    folder.join(format!("pi-{id}.json"))
}
pub fn snapshot(session: &Session, runtime: &Path) -> Activity {
    match session.agent.as_str() {
        "pi" => fs::read(pi_status_path(runtime, &session.id))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_else(Activity::unknown),
        "opencode" => opencode_snapshot(session).unwrap_or_else(|_| Activity::unknown()),
        "codex" => codex_log(session)
            .and_then(|p| log_activity(&p).ok())
            .unwrap_or_else(Activity::unknown),
        _ => Activity::unknown(),
    }
}
pub fn opencode_api(op: &str, params: &[String]) -> Result<Value> {
    let exe = executable("opencode").context("OpenCode missing")?;
    let mut args = vec![exe.to_string_lossy().into(), "api".into(), op.into()];
    for p in params {
        args.extend(["--param".into(), p.clone()]);
    }
    let bytes = output_timeout(&args, None, Duration::from_secs(4))?;
    Ok(serde_json::from_slice::<Value>(&bytes)?["data"].clone())
}
fn opencode_snapshot(session: &Session) -> Result<Activity> {
    let id = session.native_session_id.as_ref().context("No ID")?;
    let active = opencode_api("session.active", &[])?;
    let messages = opencode_api(
        "session.message.list",
        &[
            format!("sessionID={id}"),
            "limit=20".into(),
            "order=desc".into(),
        ],
    )?;
    let list = messages.as_array().context("Session not available yet")?;
    let latest = list
        .iter()
        .find(|m| m["type"] == "assistant" && !m["time"]["completed"].is_null());
    let failed = list
        .iter()
        .find(|m| m["type"] == "idle")
        .and_then(|m| m["outcome"].as_str())
        .is_some_and(|s| s != "succeeded");
    Ok(Activity {
        state: if active.get(id).is_some() {
            "Working"
        } else if failed {
            "Failed"
        } else {
            "Ready"
        }
        .into(),
        message: latest.and_then(|m| m["id"].as_str()).map(str::to_owned),
        source: "OpenCode API".into(),
    })
}
pub fn codex_root() -> PathBuf {
    std::env::var_os("CODEX_HOME")
        .map(PathBuf::from)
        .unwrap_or(home().join(".codex"))
}
pub fn codex_log(session: &Session) -> Option<PathBuf> {
    let id = session.native_session_id.as_ref()?;
    walkdir::WalkDir::new(codex_root().join("sessions"))
        .into_iter()
        .filter_map(Result::ok)
        .find(|e| {
            e.file_type().is_file()
                && e.file_name()
                    .to_string_lossy()
                    .ends_with(&format!("{id}.jsonl"))
        })
        .map(|e| e.into_path())
}
pub fn discover_codex(session: &Session) -> Option<String> {
    let started = chrono::DateTime::parse_from_rfc3339(&session.created_at)
        .ok()?
        .timestamp();
    let cwd = Path::new(&session.workdir).canonicalize().ok()?;
    let mut ids = std::collections::HashSet::new();
    for e in walkdir::WalkDir::new(codex_root().join("sessions"))
        .into_iter()
        .filter_map(Result::ok)
        .filter(|e| e.file_type().is_file() && e.path().extension().is_some_and(|e| e == "jsonl"))
    {
        let Ok(f) = fs::File::open(e.path()) else {
            continue;
        };
        let mut line = String::new();
        let _ = BufReader::new(f).take(64 * 1024).read_line(&mut line);
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        let p = &v["payload"];
        if p["source"] != "cli" {
            continue;
        }
        let Some(dir) = p["cwd"].as_str() else {
            continue;
        };
        if Path::new(dir).canonicalize().ok().as_ref() != Some(&cwd) {
            continue;
        }
        let Some(time) = p["timestamp"]
            .as_str()
            .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
        else {
            continue;
        };
        if (started - 2..=started + 120).contains(&time.timestamp())
            && let Some(id) = p["id"].as_str()
        {
            ids.insert(id.to_owned());
        }
    }
    if ids.len() == 1 {
        ids.into_iter().next()
    } else {
        None
    }
}
pub fn log_activity(path: &Path) -> Result<Activity> {
    let mut file = fs::File::open(path)?;
    let size = file.metadata()?.len();
    if size > 2 * 1024 * 1024 {
        file.seek(SeekFrom::End(-2 * 1024 * 1024))?;
    }
    let mut text = String::new();
    file.read_to_string(&mut text)?;
    let mut a = Activity::unknown();
    a.source = "Codex session events".into();
    for line in text.lines() {
        let Ok(v) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        if v["type"] != "event_msg" {
            continue;
        }
        let p = &v["payload"];
        match p["type"].as_str() {
            Some("task_started") => a.state = "Working".into(),
            Some("task_complete") => {
                a.state = "Ready".into();
                a.message = v["timestamp"].as_str().map(str::to_owned);
            }
            Some("turn_aborted") => a.state = "Interrupted".into(),
            Some("error") => a.state = "Failed".into(),
            _ => {}
        }
    }
    Ok(a)
}

/// A short-lived local RPC client. It never supplies authentication tokens or changes CLI configuration.
pub fn codex_rpc(method: &str, params: Value) -> Result<Value> {
    use std::io::Write;
    let executable = executable("codex").context("Codex is not installed")?;
    let mut command = Command::new(executable);
    command
        .args(["app-server", "--listen", "stdio://"])
        .env("PATH", augmented_path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    for (key, _) in std::env::vars_os() {
        if key.to_string_lossy().starts_with("CODEX_") {
            command.env_remove(key);
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn()?;
    let mut stdin = child.stdin.take().unwrap();
    let stdout = child.stdout.take().unwrap();
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if let Ok(value) = serde_json::from_str::<Value>(&line)
                && tx.send(value).is_err()
            {
                break;
            }
        }
    });
    let result = (|| -> Result<Value> {
        fn receive(rx: &std::sync::mpsc::Receiver<Value>, id: u32) -> Result<Value> {
            let deadline = Instant::now() + Duration::from_secs(8);
            loop {
                let v = rx.recv_timeout(deadline.saturating_duration_since(Instant::now()))?;
                if v["id"] == id {
                    ensure!(
                        v.get("error").is_none(),
                        "Codex RPC rejected request: {}",
                        v["error"]
                    );
                    return Ok(v["result"].clone());
                }
            }
        }
        writeln!(
            stdin,
            "{}",
            serde_json::json!({"id":1,"method":"initialize","params":{"clientInfo":{"name":"getitdone","title":"GetItDone","version":"0.2.0"}}})
        )?;
        stdin.flush()?;
        receive(&rx, 1)?;
        writeln!(stdin, "{}", serde_json::json!({"method":"initialized"}))?;
        writeln!(
            stdin,
            "{}",
            serde_json::json!({"id":2,"method":method,"params":params})
        )?;
        stdin.flush()?;
        let value = receive(&rx, 2)?;
        // An empty new thread is materialized by naming it before the client disconnects.
        if method == "thread/start" {
            let id = value["thread"]["id"]
                .as_str()
                .context("Codex did not return a thread ID")?;
            writeln!(
                stdin,
                "{}",
                serde_json::json!({"id":3,"method":"thread/name/set","params":{"threadId":id,"name":"GetItDone session"}})
            )?;
            stdin.flush()?;
            receive(&rx, 3)?;
        }
        Ok(value)
    })();
    drop(stdin);
    let _ = child.kill();
    let _ = child.wait();
    result
}
pub fn create_codex_session(workdir: &str) -> Result<String> {
    let result = codex_rpc(
        "thread/start",
        serde_json::json!({"cwd":workdir,"ephemeral":false,"persistExtendedHistory":true}),
    )?;
    Ok(result["thread"]["id"]
        .as_str()
        .context("Codex did not return a session ID")?
        .to_owned())
}
