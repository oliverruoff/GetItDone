"""Package an already-built macOS .app with drag-to-Applications installation."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("DMG-Erstellung benötigt macOS.")
root = Path(__file__).resolve().parents[1]
source = root / "dist/GetItDone.app"
if not source.is_dir():
    raise SystemExit("Zuerst PyInstaller mit GetItDone.spec ausführen.")
with tempfile.TemporaryDirectory(prefix="getitdone-dmg-") as folder:
    stage = Path(folder)
    shutil.copytree(source, stage / source.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    for filename in ("README.md", "VALIDATION.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(root / filename, stage / filename)
    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            "GetItDone",
            "-srcfolder",
            str(stage),
            "-ov",
            "-format",
            "UDZO",
            str(root / "dist/GetItDone-macOS.dmg"),
        ],
        check=True,
    )
