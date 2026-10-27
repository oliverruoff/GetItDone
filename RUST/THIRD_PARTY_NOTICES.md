# Third-party software

GetItDone uses Rust crates distributed under their respective licenses. The exact dependency graph and versions are recorded in `Cargo.lock`. See each crate's source distribution for its license text.

Major components include egui/eframe (MIT OR Apache-2.0), portable-pty (MIT), vt100 (MIT), hayro and its PDF/font components (MIT OR Apache-2.0), egui_commonmark (MIT OR Apache-2.0), rfd (MIT), notify-rust (MIT OR Apache-2.0), tray-icon (MIT OR Apache-2.0), serde (MIT OR Apache-2.0), chrono (MIT OR Apache-2.0), zip (MIT) and objc2 bindings (MIT).

Bundled font resources are supplied by egui and hayro under the licenses included in their crate distributions. The old Python/Qt/xterm notices are preserved in `Archive/python-v1/THIRD_PARTY_NOTICES.md`; those components are not part of the Rust application runtime.

Coding-agent CLIs are independently installed software and are not bundled in GetItDone.
