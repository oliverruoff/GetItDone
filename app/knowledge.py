"""File-based knowledge: no document contents enter notebook JSON."""

import html
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

SUPPORTED = {".txt", ".md", ".markdown", ".docx", ".pdf", ".doc"}
TEXT_LIMIT = 8 * 1024 * 1024
DOCUMENT_LIMIT = 150 * 1024 * 1024


class DocumentError(Exception):
    pass


class ConflictError(DocumentError):
    pass


def validate_title(title):
    if not title.strip() or title != title.strip() or title.endswith((".", " ")):
        raise DocumentError("Enter a title without leading or trailing spaces or a trailing period.")
    if len(title) > 180 or re.search(r'[<>:"/\\|?*\x00-\x1f]', title):
        raise DocumentError("The title contains invalid characters or is too long (180 characters maximum).")
    if title.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    }:
        raise DocumentError("This name is reserved on Windows. Please choose another title.")
    return title


def list_documents(folder, sort="name"):
    root = Path(folder)
    if not root.is_dir():
        raise DocumentError("The knowledge folder is unavailable. Please select a folder.")
    try:
        return sorted(
            (p for p in root.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED),
            key=lambda p: ((-p.stat().st_mtime if sort == "modified" else 0), p.stem.casefold(), p.suffix.casefold()),
        )
    except OSError as exc:
        raise DocumentError(f"Could not read the folder: {exc}") from exc


def limited_bytes(path, limit=TEXT_LIMIT):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise DocumentError(
                f"The file is too large for this view (limit {limit // 1024 // 1024} MB). You can open it externally."
            )
        return raw
    except OSError as exc:
        raise DocumentError(f"Could not read the file: {exc}") from exc


@dataclass
class TextDocument:
    path: Path
    text: str
    fingerprint: str
    encoding: str = "utf-8"

    def rename(self, title):
        title = validate_title(title)
        target = self.path.with_name(title + self.path.suffix)
        if target == self.path:
            return
        try:
            if self.path.is_symlink():
                raise DocumentError("Rename symbolic links externally.")
            if any(p != self.path and p.name.casefold() == target.name.casefold()
                   for p in self.path.parent.iterdir()):
                raise DocumentError("A file with this name already exists.")
            if sha256(limited_bytes(self.path)).hexdigest() != self.fingerprint:
                raise ConflictError("The file has changed externally. Reload before renaming.")
            if target.exists() and os.path.samefile(self.path, target):
                # Case-only rename on Windows/default macOS filesystems.
                self.path.rename(target)
                self.path = target
                return
            # Hard-link creation fails if a concurrent writer creates the destination.
            os.link(self.path, target)
            try:
                self.path.unlink()
            except OSError:
                target.unlink()
                raise
            self.path = target
        except OSError as exc:
            raise DocumentError(f"Could not rename the file: {exc}") from exc

    @classmethod
    def open(cls, path):
        raw = limited_bytes(path)
        encoding = (
            "utf-16"
            if raw.startswith((b"\xff\xfe", b"\xfe\xff"))
            else "utf-8-sig"
            if raw.startswith(b"\xef\xbb\xbf")
            else "utf-8"
        )
        try:
            return cls(Path(path), raw.decode(encoding), sha256(raw).hexdigest(), encoding)
        except UnicodeError as exc:
            raise DocumentError(
                "Unsupported text encoding. Please save the file as UTF-8 in an external editor."
            ) from exc

    def save(self, text):
        raw = text.encode(self.encoding)
        if len(raw) > TEXT_LIMIT:
            raise DocumentError("The text is too large (8 MB maximum).")
        temp = None
        try:
            # Resolve once: preserve a symlink instead of replacing the link itself.
            target = self.path.resolve(strict=True)
            if sha256(limited_bytes(target)).hexdigest() != self.fingerprint:
                raise ConflictError(
                    "The file has changed externally. Your changes remain in the editor. Save them as a new note or reload the external version."
                )
            mode = target.stat().st_mode
            fd, temp = tempfile.mkstemp(prefix=".getitdone-", dir=target.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp, mode)
            # Recheck directly before replace, including deletion/replacement of the source.
            if (
                self.path.resolve(strict=True) != target
                or sha256(limited_bytes(target)).hexdigest() != self.fingerprint
            ):
                raise ConflictError("The file changed externally while saving.")
            os.replace(temp, target)
            temp = None
            self.text, self.fingerprint = text, sha256(raw).hexdigest()
        except OSError as exc:
            raise DocumentError(f"Could not save the file: {exc}") from exc
        finally:
            if temp and Path(temp).exists():
                Path(temp).unlink()


def create_note(folder, title, text, extension=".txt"):
    title = validate_title(title)
    root = Path(folder)
    if not root.is_dir():
        raise DocumentError("Please select an available knowledge folder.")
    if extension not in (".txt", ".md"):
        raise DocumentError("Choose .txt or .md.")
    path = root / f"{title}{extension}"
    # Case-insensitive collision policy is consistent on macOS and Windows.
    if any(p.name.casefold() == path.name.casefold() for p in root.iterdir()):
        raise DocumentError("A file with this name already exists. Please choose another title.")
    raw = text.encode("utf-8")
    if len(raw) > TEXT_LIMIT:
        raise DocumentError("The text is too large (8 MB maximum).")
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise DocumentError(f"Could not create the note: {exc}") from exc
    return TextDocument.open(path)


def docx_html(path):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    if Path(path).stat().st_size > DOCUMENT_LIMIT:
        raise DocumentError("The Word file is too large. Please open it externally.")
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
                raise DocumentError("The uncompressed Word document is too large (50 MB maximum).")
        document = Document(path)
        parts = [
            '<p style="color:#666">Content preview · Layout, images and embedded objects are not fully displayed.</p>'
        ]
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                parts.append("<p>" + html.escape(block.text).replace("\n", "<br>") + "</p>")
            elif isinstance(block, Table):
                parts.append('<table border="1" cellspacing="0" cellpadding="5">')
                for row in block.rows:
                    parts.append(
                        "<tr>"
                        + "".join(
                            "<td>" + html.escape(cell.text).replace("\n", "<br>") + "</td>"
                            for cell in row.cells
                        )
                        + "</tr>"
                    )
                parts.append("</table>")
        return "".join(parts)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("The Word document is damaged, protected or unreadable.") from exc
