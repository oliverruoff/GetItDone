"""User-owned Canvas files in the notebook data directory."""

from pathlib import Path


STARTER_HTML = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GetItDone Canvas</title>
<style>
body { margin: 0; background: #f5f6fa; color: #243047; font: 18px system-ui; }
main { max-width: 760px; margin: 12vh auto; padding: 40px; }
h1 { font-size: 48px; letter-spacing: -2px; }
p { line-height: 1.7; }
</style>
<main><h1>Your canvas.</h1>
<p>A dashboard, a collection of links, an idea made visible — this space is yours.</p>
<p>Use <strong>Open agent</strong> below to shape this page with your preferred agent.</p>
</main>
</html>
"""

AGENT_GUIDE = """# GetItDone Canvas

This folder is the free-form Canvas feature of the GetItDone personal notebook.
GetItDone displays canvas.html directly in its Canvas tab, with JavaScript enabled.
Edit this HTML to build whatever the user requests: dashboards, link collections,
visualizations of todos, diagrams, or any other HTML experience. There is no required
framework or layout. Keep the entry point named canvas.html.

## Editing
- Work in this folder. Changes to HTML and local assets automatically reload the view.
- Prefer self-contained HTML and relative paths for CSS, JavaScript, images and data.
- No build step or web server is started; the page is loaded as a local file.
- Remote requests from the local page are disabled; prefer assets copied here.
- Normal web links open in the system browser.
- The page has no privileged bridge to GetItDone, its notebook data or its terminals.
- Do not overwrite existing user content unless requested. Do not modify notebook.json.

## Backups — important
The ENTIRE canvas folder, including canvas.html, AGENTS.md, subfolders and assets,
is included in GetItDone's manual and scheduled full ZIP backups when they run.
Files OUTSIDE this folder are NOT included by the Canvas backup, even if the HTML
references them. Copy required local images, stylesheets, scripts and data INTO this
folder and reference them with relative paths. Remote resources are not downloaded
by backups; copy them here when a self-contained, restorable canvas is needed.
Live terminal output and native agent chat histories are not part of Canvas backups.
Do not use symlinks or junctions: linked paths cause backups to fail rather than
silently including external files. Backups are not encrypted; avoid storing secrets.
To restore, quit GetItDone and restore canvas/ into its data directory.
"""


def prepare_canvas(data_folder):
    folder = Path(data_folder) / "canvas"
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in (("canvas.html", STARTER_HTML), ("AGENTS.md", AGENT_GUIDE)):
        try:
            with (folder / name).open("x", encoding="utf-8") as stream:
                stream.write(content)
        except FileExistsError:
            pass
    return folder
