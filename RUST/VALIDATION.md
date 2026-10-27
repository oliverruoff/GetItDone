# Rust validation — 27 October 2026

This report describes performed checks. It does not claim native Windows/Linux execution or a completed visual desktop acceptance.

## Automated checks on Apple Silicon macOS

- `cargo fmt --check` — passed.
- `cargo clippy --all-targets -- -D warnings` — passed.
- `cargo test -- --test-threads=1` — 15 tests passed; the live test is explicitly ignored in the normal suite.
- The live test was run explicitly with installed, authenticated CLIs and real model requests. A full three-agent run passed, including simultaneous open terminals.

The UI tests run the actual application UI through egui frames and pointer/keyboard events. Buttons, menus, text editors, checkboxes, confirmations and Resume are clicked through their rendered widget rectangles. This checks application interaction and backend integration; it does not substitute for a visual review of the native window.

## User-requested end-to-end scenario

`GETITDONE_E2E_PI_MODEL=openai/gpt-5.4-mini cargo test --test workflows live_agents -- --ignored --nocapture --test-threads=1`

1. Click Add item, enter a parent title, use More actions to add a child, enter its title.
2. At the child, create OpenCode, Codex and pi sessions in separate isolated working folders.
3. Paste and submit a harmless prompt through the terminal UI for each agent. Each conversation receives a different randomly generated token; the prompts prohibit tools/file changes.
4. Observe Working and Ready from each agent's own events/API, independently of terminal liveness.
5. Leave all three terminals open, then close each through its terminal-tab button and confirmation. Confirm zero remaining terminals while preserving all three session links.
6. Click Resume for each saved link. A new PTY opens using exactly its saved native ID.
7. Submit a second prompt asking for the remembered token without including that token. Verify the actual latest assistant reply in the native conversation record/API, not merely a matching substring in repainted terminal history.
8. Confirm the saved native ID is unchanged. Close each resumed terminal.
9. Delete the parent and verify its child and session links are removed and no test terminals remain.
10. Create another item, complete it and click Undo; verify it is open again.

Full transcripts and JSON reports are stored locally in `tests/artifacts/` (Git-ignored). `live-report.json` records each exact native ID and whether Working, Ready and token recall were observed. The test does not touch the user's existing notebook or unrelated sessions. Temporary workspaces are cleaned up; the agents retain their native test conversations.

## Knowledge and task checks

- Create several real TXT files in a test folder, including an empty file, multiline content and Unicode names/content.
- Import/select the folder. Verify every top-level TXT document title and its exact content through the UI. Ignore unsupported files and nested folders.
- Edit a TXT through the UI, save, read back from disk, and create an additional real TXT through New note.
- Simulate an external file edit; verify a local draft cannot overwrite it and stays in memory. Refuse duplicate filenames, traversal and Windows-reserved names.
- Read and write UTF-16 without losing its BOM/encoding.
- Read a generated DOCX containing paragraphs and a table cell. Render an actual PDF page and verify nonempty colored pixels.
- Create/edit parent and child task notes; delete a note and restore it through its own Undo.
- Complete a hierarchy with previously completed descendants. Undo preserves the exact previous completion mixture and later text edits.
- Select each of the 16 palette colors, save/remove a reminder, and verify resulting state.
- Verify atomic notebook persistence, previous-valid backup, exclusive writer lock and refusal to overwrite an unknown schema.
- Load a schema-1 notebook without new optional Rust fields and preserve its settings and exact native session IDs.
- Verify hierarchy normalization after deleting and adding siblings.
- Test an actual PTY with ANSI output, input echo and shutdown; verify terminal control-key encoding.
- Discover instruction/skill files and parse JSONC MCP configuration while hiding commands, arguments and credentials.
- Verify Codex Working/Ready/Interrupted states from session events.

## Agent/provider findings

OpenCode and Codex successfully used their installed authentication/configuration. Codex's bundled CLI can report a Desktop-origin session even when launched as a CLI. New Rust sessions therefore obtain the exact ID from the local app-server before opening the TUI; no timestamp-based guess is needed.

pi's installed default (`openai-codex/gpt-5.5`) returned a missing-credentials error. Other configured providers returned exhausted Google credits, unavailable Kimi subscription access and insufficient MiniMax balance. These were real Failed events and appeared as Failed in GetItDone. No accounts, subscriptions, global model settings or authentication files were changed.

The successful pi test used the existing `OPENAI_API_KEY` environment with the per-session model `openai/gpt-5.4-mini`. A Finder-launched app needs provider authentication available to the CLI in that environment; the successful test does not repair an unusable default provider or install credentials. The optional session Model field allows an explicit provider/model without changing the global default.

## Built artifacts

| Platform | Result | Execution evidence |
| --- | --- | --- |
| macOS ARM64 | Rust executable plus ad-hoc signed `.app` | `--version`, signature verification and native startup with isolated data directory |
| Windows x86_64 | Real PE32+ GUI `.exe`, cross-compiled with MinGW | Binary format/import inspection; no native Windows runtime available |
| Linux x86_64 | Real ELF executable, cross-compiled with Zig for glibc 2.28 | Binary format/dynamic dependency inspection; no native Linux runtime available |

The exact files live under `releases/macos`, `releases/windows`, `releases/linux`. `releases/SHA256SUMS` identifies the final executables. Cross-compiled artifacts are not placeholders. Native three-platform CI configuration is included, but no push or CI run was performed.

## Remaining native acceptance

The release macOS window was launched using an isolated manual notebook. Computer Use initially reported that the Mac was locked and could not be automatically unlocked; subsequent native inspection attempts timed out. Therefore the final visual desktop review, OS folder-dialog interaction, tray interaction and macOS notification-center delivery have **not** been verified interactively in this run. The user was asked to unlock the Mac; automated UI and live PTY tests continued independently.

The notification implementation uses macOS UserNotifications, requests permission, checks authorization/banner settings and checks delivered notifications when sending from the app bundle. That implementation is compiled, but native delivery is not claimed as tested here. Windows and Linux GUI/notification/ConPTY behavior still needs native execution. PDF preview covers ordinary documents and reports unsupported/damaged files; it is not a guarantee for every PDF feature.

Before opening the user's existing data directory, quit the still-running old Python app. The Rust app deliberately refuses to write into a folder that still has the Python instance lock.

## Follow-up: macOS Dock / tray Quit

Native macOS `terminate:` (used by Dock Quit and Command-Q) is intercepted and routed through the same save/confirmation/PTY cleanup path as the in-app Quit button. Tray menu events reveal and wake a hidden window before processing an action; they no longer depend on polling a hidden UI. Quit with no running terminals saves and exits without a redundant confirmation.

Three regression tests passed: pending TXT is saved and the notebook lock is released; an external TXT conflict preserves the draft and blocks exit; running-terminal shutdown can be cancelled, then confirmed. The native `cargo run --example quit_probe` test also passed: a real native window was hidden, `NSApplication::terminate(None)` was dispatched on the main queue, the app ran its shutdown path, exited its event loop and released the data lock. This is an actual native lifecycle test; clicking the Dock itself through Computer Use remains blocked by repeated tool timeouts.

The already-running pre-fix application cannot acquire patched code until restarted. The release bundle and executable are rebuilt with the fix.
