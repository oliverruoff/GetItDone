"""On macOS launch the real bundle so notification identity/permissions are reliable."""

import json
import subprocess
import sys
from pathlib import Path

from app.build_info import source_revision


def bundle_current(root):
    bundle = root / "dist/GetItDone.app"
    executable = bundle / "Contents/MacOS/GetItDone"
    metadata = bundle / "Contents/Frameworks/app/build-info.json"
    if not executable.is_file():
        return False
    try:
        return json.loads(metadata.read_text())["revision"] == source_revision(root / "app")
    except (OSError, ValueError, KeyError):
        return False


def main():
    if sys.platform != "darwin":
        from app.main import main as source_main

        return source_main()
    root = Path(__file__).resolve().parents[1]
    if not bundle_current(root):
        print("Updating GetItDone to the current source version …", flush=True)
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", str(root / "GetItDone.spec")],
            cwd=root,
            check=True,
        )
        if not bundle_current(root):
            raise RuntimeError("The new app bundle does not match the current source. Please retry.")
    # -n executes the current build even if Finder knows an older running process.
    # The startup channel activates a matching version or saves before a version handover.
    subprocess.run(
        ["open", "-n", str(root / "dist/GetItDone.app"), "--args", *sys.argv[1:]],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
