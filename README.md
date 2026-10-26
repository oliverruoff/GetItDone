# GetItDone — personal work notebook

A local desktop app for Windows and macOS: tasks, child items, notes, row colors, one-time reminders and embedded coding-agent terminals. **Knowledge** reads normal files from a local folder and creates/edits real TXT files. No server, account or synchronization.

## Start

On this Mac, double-click **`run.command`** in the project folder to run the current app build. If the source changed, the launcher rebuilds the app automatically before opening it. On macOS this uses the real application bundle so system notifications have the correct app identity. The launcher saves and replaces the running instance through its normal shutdown flow. If sessions are running, the app asks before stopping them. File conflicts and cancelled shutdowns preserve the existing instance.

The packaged build is **`dist/GetItDone.app`**; drag it to Applications if desired:

```sh
open /Users/oliverruoff/Documents/develop/GetItDone/dist/GetItDone.app
```

The launcher automatically rebuilds stale packaged versions. A manual packaged build is also available below. Both source and packaged launches show the loaded revision in the window title (`--version` also prints it). A second launch of the same revision activates the existing window. A running packaged app checks for a replaced build when activated again.

Source setup (Python 3.11+, recommended 3.12+):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m app
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m app
```

Windows requires Windows 10 1809+ or Windows 11 for ConPTY. The local macOS build targets Apple Silicon. Install and authenticate agent CLIs separately. Finder-launched Node CLIs also need their Node runtime on PATH.

Use `--data-dir /tmp/getitdone-test` for an isolated test notebook.

## Tasks

- **+ Add item** creates a top-level item. Enter adds a sibling; Tab / Shift+Tab indents/outdents outside multiline notes. Double-click or F2 edits text in place. The expand icon shows the full wrapped title; expanded titles use a multiline editor. HTTP(S) URLs and Markdown links in titles open in the default browser. Task notes span the full row. Their trash icon deletes without confirmation and offers a separate Undo notice. A single click only selects; it does not enter editing. Row icons provide **Edit note**, **New session** and **More actions**; their tooltips and accessible names explain each action.
- Main items have bold headings, separators and group rails. Child items use deeper indentation, connectors and neutral background levels. Notes and sessions stay directly below their item.
- Click **Color** to open a 4×4 palette of 16 distinct colors. Click a swatch to apply it immediately to the **entire task row**. **No color** clears it. Text and icons switch contrast automatically. Children keep their own color choices. Existing categories are preserved and reused by color; optional naming/custom categories remain in Settings. There is no color filter or color legend; assigning a row color never hides tasks.
- Check a box to complete only that item. Completing a parent completes all descendants. Undo restores the exact previous mix of open/completed states, without reverting unrelated edits. Reopening a child also reopens its ancestors. Completed rows slide out of the open view and offer **Undo** for five seconds. The Completed / All filters show them again.
- Click the bell in **Reminder**, choose a date/time and click **Save**. No enable checkbox is required. The cell shows the saved local time immediately. **Remove reminder** explicitly clears it. Each scheduled time fires at most once while the app runs. Completed items do not notify. Reminders missed while the app was fully closed are only marked overdue on restart.
- **New session** at the task creates an agent session in the selected working directory. Only the item's text is copied. Paste and submit it yourself in the integrated terminal.
- A session row has **Resume** and a details icon. Resume focuses its live terminal or starts a new process with its exact saved native session ID, without an extra confirmation. A new session is created at the task, not from the session row. Details expose the working directory, label and native ID.
- OpenCode v2 sessions created by the app get an explicit native ID; its local API reports agent activity and new replies. Claude and pi receive a fixed UUID at launch. Codex IDs are read from its local CLI session index or metadata. Missing older Claude/pi IDs can also be recovered from local session headers. Recovery requires a unique match for working directory and creation time (within two minutes); ambiguous matches remain available for manual entry in Details. **Running terminal** describes process state; agent activity is reported separately when available.
- Select a session to inspect discovered instructions, MCP configurations and skills. **Discovered / Configured** never imply **Loaded / Active**. Configuration values and secrets are not displayed.

## Knowledge

Choose a local folder, then select a document. TXT is editable; Markdown, Word and PDF have integrated read-only views. **New note** creates `<Title>.txt` as a real UTF-8 file. TXT auto-saves after a short typing pause and when leaving the document. If the file changed externally, saving stops and your text stays in the editor. **Save as new note** preserves both versions; **Refresh** can reload the external version after explicitly discarding local edits.

Only files directly in the folder are listed. Supported: TXT, MD/MARKDOWN, DOCX and PDF; older DOC files display an explicit external-open notice. File names are the titles. Existing user text, document names and custom category names are not translated.

## Closing and notifications

Closing the window hides it in the system tray / menu bar, leaving sessions and reminders running. **File → Quit** exits completely and asks before ending running sessions. If no tray is available, the window stays minimized. **View** hides/shows the terminal panel. Agent context has its own top-level tab beside Tasks and Knowledge.

**Help → Test notification** checks native delivery. Permission status is visible in the status bar and Settings. The macOS launcher uses the real app bundle and UserNotifications. Scheduling a first reminder requests authorization. Permission and banner settings are checked before sending; source-only development runs explicitly report system notifications as unavailable. Click the notification status to open guidance and System Settings. Windows uses Qt tray messages and checks the global disabled-notifications switch when accessible. System permissions, focus modes and policies can prevent native delivery; overdue marks remain visible in the app. OS-owned dialogs can follow the system language; all app-owned UI is English.

## Data and recovery

`notebook.json` resides in the OS application-data directory; Settings shows its exact path. Tasks, categories, session links and settings persist. Knowledge files stay in the selected folder; only its path and last selection enter JSON. Terminal output and unread flags stay in memory. Agents may keep their own histories independently.

Task actions and live text edits are saved immediately and atomically. The persistent status shows All changes saved or a visible write failure. JSON retains `notebook.backup.json` as the previous valid version. Corrupt/unknown data versions block startup without overwriting the file. To recover: quit, back up the original, inspect the backup, then deliberately restore it as `notebook.json`. A lock and local startup channel prevent concurrent writers in the same directory.

TXT writes use a temporary file and atomic replacement with external-content checks. As with ordinary file editors, an uncooperative external writer in the final instant before replacement cannot be covered by a portable atomic compare-and-write transaction.

## Integration limits

- Resume starts a new local process using the exact native ID: `opencode --session ID`, `codex resume ID`, `claude --resume ID`, `pi --session ID`. pi also accepts an existing absolute `.jsonl` session-file path. GetItDone does not replay or persist terminal output.
- **Agent context** works without a session: select an installed CLI and a working folder, then browse **Skills**, **MCPs**, and **Instructions**. Selecting a session switches to its agent/folder. Entries show scope, status and source; selecting one displays its text. Global, shared and inherited instruction sources are included, and Codex override files take precedence. JSONC MCP configuration is parsed; server credentials, command arguments and URLs are hidden.
- Codex's read-only app-server skill registry includes bundled/plugin skills. OpenCode v2's read-only API supplies registered skills and MCP status when available. No model turn is started and no MCP command is launched by the inspector. Other agents use local discovery. “Available”/“Registered” means a skill can be loaded on demand, not that its full content is in a conversation. Loaded conversation contents are not reported. Running sessions can retain older instructions; CLI overrides, imports, plugins, trust decisions and additional paths are not fully reproduced. Pi extensions/MCP runtime state are not introspected. CLI presence does not verify account authentication.
- Qt tray fallback clicks identify only the last sent reminder because Qt does not expose a per-message ID. macOS packaged notifications carry the item ID.
- Word shows text and tables, not exact Office layout, images or embedded objects. PDF pages are rendered even without a text layer; no OCR is promised. Protected/damaged files display errors.
- Limits: text 8 MB; PDF/Word 150 MB; uncompressed DOCX 50 MB. Previews run no scripts or remote images. External links require a deliberate action.
- Shutdown signals the agent, then ends remaining members of its process group. Deliberately detached processes outside the group cannot be reliably identified. Existing PTYs are not reattached after a full app restart.

## Tests and builds

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests scripts
.venv/bin/python -m app --data-dir /tmp/getitdone-smoke --smoke-terminal
dist/GetItDone.app/Contents/MacOS/GetItDone --data-dir /tmp/getitdone-notification-test --test-notification
.venv/bin/python -m PyInstaller --noconfirm GetItDone.spec
.venv/bin/python scripts/build_dmg.py
```

`terminal_spike.py` probes installed CLIs without sending a prompt; it prints metadata rather than terminal contents. Normal tests cover a real WebEngine/xterm/PTY connection. A real model-call test is opt-in with `GETITDONE_LIVE_OPENCODE=1`.

xterm.js is pinned and vendored; `scripts/vendor_terminal.py` is only needed for a dependency update. `.github/workflows/build.yml` tests/builds on macOS and Windows; Inno Setup creates the Windows installer. No push or CI run is implied by local work. Public macOS releases require Developer ID signing/notarization, and Windows releases should use your own signing certificate. Local macOS builds are ad-hoc signed. Uninstallers do not delete knowledge files.

See [VALIDATION.md](VALIDATION.md) for actual validation and platform limitations, and [the spec](productivity-tool-spec-mit-wissensbereich.md) for the agreed scope and current UX amendments.

## Adapter references

Official documentation checked during implementation:

- [OpenCode CLI](https://opencode.ai/docs/cli/), [configuration](https://opencode.ai/docs/config/), [skills](https://opencode.ai/docs/skills/)
- [Codex CLI](https://developers.openai.com/codex/cli/reference/), [configuration](https://developers.openai.com/codex/config-basic/)
- [Claude Code CLI](https://code.claude.com/docs/en/cli-reference), [MCP](https://code.claude.com/docs/en/mcp)
- [pi](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent)
- [pywinpty](https://github.com/andfoy/pywinpty), [Qt tray messages](https://doc.qt.io/qt-6/qsystemtrayicon.html)
