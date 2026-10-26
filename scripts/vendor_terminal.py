"""Build-time only: pin and vendor official xterm.js packages, including licenses."""

import io
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app/terminal/web"
PACKAGES = [
    (
        "@xterm/xterm",
        "5.5.0",
        {"lib/xterm.js": "xterm.js", "css/xterm.css": "xterm.css", "LICENSE": "LICENSE.xterm"},
    ),
    ("@xterm/addon-fit", "0.10.0", {"lib/addon-fit.js": "addon-fit.js", "LICENSE": "LICENSE.addon-fit"}),
]
for name, version, files in PACKAGES:
    url = f"https://registry.npmjs.org/{name}/-/{name.split('/')[-1]}-{version}.tgz"
    with urllib.request.urlopen(url, timeout=30) as response:
        archive = tarfile.open(fileobj=io.BytesIO(response.read()), mode="r:gz")
    for source, target in files.items():
        (ROOT / target).write_bytes(archive.extractfile("package/" + source).read())
(ROOT / "versions.json").write_text(json.dumps({name: version for name, version, _ in PACKAGES}, indent=2))
