# GetItDone 0.2.0

- `macos/GetItDone.app`: Apple Silicon app bundle; use this for native macOS notifications.
- `macos/GetItDone`: Apple Silicon terminal executable.
- `windows/GetItDone.exe`: Windows x86_64 GUI executable.
- `linux/GetItDone`: Linux x86_64 executable, glibc 2.28+, X11/Wayland desktop.

No Python runtime is required. Coding agents are installed/authenticated separately. The macOS bundle is ad-hoc signed. Windows/Linux builds were cross-compiled and have not yet been run on those operating systems. See `../VALIDATION.md` for the performed checks and remaining native acceptance.
