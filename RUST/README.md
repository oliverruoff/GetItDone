# GetItDone — Rust desktop notebook

GetItDone is a local desktop app for tasks, nested items, task notes, reminders, real coding-agent terminals and a file-based knowledge folder. The application and its UI are written in Rust, using egui/eframe. There is no Python runtime, WebView, account, server or synchronization requirement for the notebook. Coding agents continue to use their own installed CLIs and authentication.

The Python implementation is the main project in the repository root (`../`). This Rust implementation, tests, build scripts and releases are preserved in **`RUST/`**. Run the commands below from this directory (`cd RUST`). The original requirements and feedback remain in `../productivity-tool-spec-mit-wissensbereich.md`.

## Run

| Platform | File | Architecture |
| --- | --- | --- |
| macOS | `releases/macos/GetItDone.app` | Apple Silicon / ARM64 |
| macOS terminal launch | `releases/macos/GetItDone` | Apple Silicon / ARM64 |
| Windows | `releases/windows/GetItDone.exe` | x86_64 |
| Linux | `releases/linux/GetItDone` | x86_64; glibc 2.28+ |

On this Mac, double-click `run.command` or `releases/macos/GetItDone.app`. The app bundle is required for native macOS notifications. The build is locally ad-hoc signed; it is not a notarized public distribution.

For an isolated notebook:

```sh
releases/macos/GetItDone.app/Contents/MacOS/GetItDone --data-dir /tmp/getitdone-rust-test
```

Linux needs a graphical X11/Wayland session, working OpenGL drivers and the desktop's X11/Wayland/xkbcommon libraries. Folder dialogs use the desktop portal; notifications use the desktop notification service. Windows needs Windows 10 1809+ or Windows 11 for ConPTY. The executable imports Windows system libraries and does not require a separately installed Python, Rust or Node runtime. Agent CLIs may have their own runtime requirements.

See `VALIDATION.md` for exactly what was run, native platform limitations and the pi provider used in the live tests. Building an executable does not establish that it was tested on that operating system.

## Tasks

- **Add item** creates a task and opens its title editor. Enter creates a sibling; Escape exits editing. A single click selects; double-click or the edit button/F2 edits. The **More actions** menu adds children/siblings, indents/outdents, reorders, expands full titles and deletes an item with its descendants. Tab/Shift+Tab indent/outdent a selected item outside a text editor.
- Main items are stronger headings; nested items have indentation and connectors. Task notes appear across the row beneath their item. Deleting a note offers its own Undo.
- **Color** opens a 4×4 palette. A swatch immediately colors the row; **No color** clears it. Text contrast adapts. Children retain their own colors. Category names can be edited in Settings.
- Completing a parent completes descendants. **Undo** restores their previous completion states and preserves later text changes. Reopening a child reopens its ancestors. Open/Completed/All and search keep necessary ancestor context.
- **Reminder** accepts an unambiguous local date/time; Save schedules it without another enable switch. Remove reminder clears it. Completed tasks do not notify. A reminder fires at most once while running; reminders missed while fully closed are marked overdue without replaying notifications.
- Edits and task actions save immediately. The bottom status reports write errors; the previous valid notebook becomes `notebook.backup.json`.

## Agent terminals and exact Resume

Use **New session** on an item, select OpenCode, Codex, pi or Claude, and select an existing working folder. The item text is copied; paste and submit it yourself. The optional Model field overrides the CLI default for this session only. For pi it can include a provider, e.g. `openai/gpt-5.4-mini`. Leaving it empty preserves the installed CLI's configuration.

The terminals are real PTYs (Unix) or ConPTY (Windows), with ANSI screen rendering, keyboard input, paste, resize and scrollback. Each session has its own terminal tab. Click inside a terminal to send input. Command-C / terminal copy copies the visible screen; Control-C interrupts the agent.

**Resume** focuses an already running terminal or launches the exact saved native session ID. It never selects the newest conversation:

- OpenCode: an explicit native ID, resumed with `--session ID`.
- Codex: the local app-server creates and materializes a thread before its first TUI opens; its returned ID is saved. The TUI opens with `resume ID`. Legacy records with no ID retain conservative discovery or manual entry in Details.
- pi: a fixed UUID at creation, `--session ID` on resume. A small bundled pi extension relays public `agent_start` / `agent_end` events to a local status file; it stores no prompts or credentials.
- Claude: a fixed UUID at creation and `--resume ID`. Claude is supported but was not included in the three-agent live acceptance test.

**Running / Terminal closed** is process state. **Working / Ready / Failed / Interrupted / Status unavailable** is agent state. OpenCode activity comes from its local API, Codex from native session events, and pi from extension events. Terminal repaint activity is never treated as agent activity. New replies in inactive sessions are marked separately. Status collection runs outside the UI thread.

Closing a running terminal asks first and stops its process group. Saved session links and native histories remain. Deleting a task with running sessions asks before stopping and removing its links. Custom agent profiles can be edited as JSON argument lists in Settings; they do not have automatic native-session resume or context introspection.

## Knowledge / memory notes

Choose a local folder. Its immediate TXT, Markdown, DOCX, PDF and legacy DOC files are listed by filename; subfolders are not recursively imported. No contents are copied into the notebook JSON.

TXT files are editable with autosave after a typing pause and before switching documents. UTF-8, UTF-8 BOM and UTF-16 are supported and their encoding is preserved. If the file changes externally, saving stops and the local draft stays in the editor. **Save as new note** preserves both versions; **Reload from disk** explicitly confirms discarding unsaved text. New note creates a real `<Title>.txt` without replacing an existing file.

Markdown has a formatted read-only view without remote image loaders or script execution. Word shows text and table content. PDFs are rendered locally in Rust with page navigation, including pages without a text layer. Legacy DOC opens externally. PDF rendering is a document preview, not OCR or an Office layout guarantee; unsupported or damaged files display errors. Text previews are limited to 8 MB, PDF/DOCX to 150 MB and DOCX XML to 50 MB.

## Agent context

The independent **Agent context** tab discovers instructions, skills and MCP configurations for an agent/folder. It also queries Codex's read-only skill registry and OpenCode's local skill/MCP APIs. Configured/Available/Registered do not imply Loaded/Active. MCP commands, arguments, URLs and credentials are hidden; discovery never starts an MCP server or submits a model prompt. Running agents can retain older context, and not every extension, import or trust decision can be reproduced.

## Data and lifecycle

The existing schema-1 notebook stays compatible. Default paths preserve the Python app's locations:

- macOS: `~/Library/Application Support/GetItDone/GetItDone/`
- Windows: `%APPDATA%/GetItDone/GetItDone/`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/GetItDone/GetItDone/`

Quit the Python app before opening the same data folder. Its `instance.lock` prevents the Rust app from writing concurrently. Rust instances use an OS file lock; a second Rust launch requests activation of the existing window. Corrupt data, unknown schema versions and invalid references block startup without overwriting the original.

Closing the window hides it in the macOS/Windows tray when available, otherwise minimizes it. Sessions and reminders keep running. **Quit** (Dock menu, Command-Q, tray menu or in-app button) saves and stops terminals. With no running terminals it exits immediately. With running terminals it reveals the window and asks before stopping them; Cancel keeps them running. Save conflicts keep the app open with the draft intact. macOS notifications use UserNotifications with permission/banner checks and delivery verification when available. System Focus policies can defer delivery; the app reports that separately. Use **Settings → Test system notification** from the packaged app.

Terminal output stays in memory. Native agent histories are owned by the agents. Deliberately detached processes outside a terminal's process group cannot be reliably terminated. Agent sessions are resumed as new terminal processes, not reattached PTYs.

## Build and test

```sh
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test -- --test-threads=1
./scripts/package-macos.sh
```

The live acceptance test sends actual model prompts using installed authenticated CLIs:

```sh
GETITDONE_E2E_PI_MODEL=openai/gpt-5.4-mini \
  cargo test --test workflows live_agents -- --ignored --nocapture --test-threads=1
```

`GETITDONE_E2E_AGENT=codex,pi` optionally limits that test. Test transcripts and JSON reports are written under `tests/artifacts/` and are ignored by Git. GUI tests inject pointer/keyboard events into the actual egui widgets, rather than calling task actions directly.

For cross-building on macOS with Zig, cargo-zigbuild and MinGW installed:

```sh
rustup target add x86_64-unknown-linux-gnu x86_64-pc-windows-gnu
cargo zigbuild --release --target x86_64-unknown-linux-gnu.2.28 --target-dir target/linux
cargo build --release --target x86_64-pc-windows-gnu --target-dir target/windows
```

`.github/workflows/build.yml` also builds and tests on native macOS, Windows and Linux runners. No push or CI execution is implied by the local build.

Implementation references: [eframe](https://docs.rs/eframe/0.33.3/eframe/), [portable-pty](https://docs.rs/portable-pty/0.9.0/portable_pty/), [hayro](https://github.com/LaurenzV/hayro), [Codex CLI](https://developers.openai.com/codex/cli/reference/), [Codex app-server](https://developers.openai.com/codex/app-server).
