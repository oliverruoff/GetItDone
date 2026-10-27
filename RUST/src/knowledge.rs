use crate::storage::{atomic_write, read_limited};
use anyhow::{Context, Result, ensure};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
};
const TEXT_LIMIT: u64 = 8 * 1024 * 1024;
#[derive(Clone)]
pub struct Document {
    pub path: PathBuf,
    pub text: String,
    original: Vec<u8>,
    pub editable: bool,
    encoding: u8,
}
fn decode(raw: &[u8]) -> Result<(String, u8)> {
    if raw.starts_with(&[0xff, 0xfe]) || raw.starts_with(&[0xfe, 0xff]) {
        ensure!(raw.len().is_multiple_of(2), "Invalid UTF-16");
        let le = raw[0] == 0xff;
        let words: Vec<u16> = raw[2..]
            .as_chunks::<2>()
            .0
            .iter()
            .map(|b| {
                if le {
                    u16::from_le_bytes([b[0], b[1]])
                } else {
                    u16::from_be_bytes([b[0], b[1]])
                }
            })
            .collect();
        Ok((String::from_utf16(&words)?, if le { 2 } else { 3 }))
    } else if raw.starts_with(&[0xef, 0xbb, 0xbf]) {
        Ok((String::from_utf8(raw[3..].to_vec())?, 1))
    } else {
        Ok((String::from_utf8(raw.to_vec())?, 0))
    }
}
pub fn list(folder: &Path) -> Result<Vec<PathBuf>> {
    ensure!(folder.is_dir(), "Knowledge folder is unavailable");
    let mut paths = vec![];
    for e in fs::read_dir(folder)? {
        let p = e?.path();
        if p.is_file()
            && ["txt", "md", "markdown", "docx", "pdf", "doc"].contains(
                &p.extension()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_lowercase()
                    .as_str(),
            )
        {
            paths.push(p);
        }
    }
    paths.sort_by_key(|p| {
        p.file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_lowercase()
    });
    Ok(paths)
}
pub fn validate_title(title: &str) -> Result<()> {
    ensure!(
        !title.is_empty() && title.trim() == title && title.len() <= 180 && !title.ends_with('.'),
        "Enter a valid title (180 characters maximum)"
    );
    ensure!(
        !title
            .chars()
            .any(|c| c.is_control() || "<>:\"/\\|?*".contains(c)),
        "Title contains invalid characters"
    );
    let first = title.split('.').next().unwrap().to_uppercase();
    ensure!(
        !["CON", "PRN", "AUX", "NUL"].contains(&first.as_str())
            && !(first.len() == 4
                && (first.starts_with("COM") || first.starts_with("LPT"))
                && first.ends_with(|c: char| c.is_ascii_digit())),
        "Reserved Windows filename"
    );
    Ok(())
}
pub fn create(folder: &Path, title: &str, text: &str) -> Result<PathBuf> {
    validate_title(title)?;
    ensure!(text.len() as u64 <= TEXT_LIMIT, "Note exceeds 8 MB");
    let path = folder.join(format!("{title}.txt"));
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)?;
    file.write_all(text.as_bytes())?;
    file.sync_all()?;
    Ok(path)
}
impl Document {
    pub fn open(path: &Path) -> Result<Self> {
        let ext = path
            .extension()
            .unwrap_or_default()
            .to_string_lossy()
            .to_lowercase();
        let raw = read_limited(
            path,
            if ["docx", "pdf"].contains(&ext.as_str()) {
                150 * 1024 * 1024
            } else {
                TEXT_LIMIT
            },
        )?;
        let (text, encoding) = if ext == "docx" {
            let mut zip = zip::ZipArchive::new(std::io::Cursor::new(&raw))?;
            let file = zip.by_name("word/document.xml")?;
            ensure!(
                file.size() <= 50 * 1024 * 1024,
                "DOCX content exceeds 50 MB"
            );
            let mut xml = String::new();
            file.take(50 * 1024 * 1024 + 1).read_to_string(&mut xml)?;
            let mut reader = quick_xml::Reader::from_str(&xml);
            let mut text = String::new();
            loop {
                use quick_xml::events::Event;
                match reader.read_event()? {
                    Event::Text(t) => text.push_str(&quick_xml::escape::unescape(&t.decode()?)?),
                    Event::End(e) if e.name().as_ref() == b"w:p" => text.push('\n'),
                    Event::End(e) if e.name().as_ref() == b"w:tc" => text.push('\t'),
                    Event::Eof => break,
                    _ => {}
                }
            }
            (text, 0)
        } else if ext == "pdf" {
            (
                String::from(
                    "PDF preview opens in your system viewer. The original file is preserved.",
                ),
                0,
            )
        } else if ext == "doc" {
            (
                String::from("Legacy Word document. Open externally to view or convert it."),
                0,
            )
        } else {
            decode(&raw).context("Text must be UTF-8 or UTF-16")?
        };
        Ok(Self {
            path: path.into(),
            text,
            original: raw,
            editable: ext == "txt",
            encoding,
        })
    }
    pub fn dirty(&self) -> bool {
        self.encode() != self.original
    }
    fn encode(&self) -> Vec<u8> {
        match self.encoding {
            1 => [vec![0xef, 0xbb, 0xbf], self.text.as_bytes().to_vec()].concat(),
            2 | 3 => {
                let mut bytes = if self.encoding == 2 {
                    vec![0xff, 0xfe]
                } else {
                    vec![0xfe, 0xff]
                };
                for w in self.text.encode_utf16() {
                    bytes.extend(if self.encoding == 2 {
                        w.to_le_bytes()
                    } else {
                        w.to_be_bytes()
                    });
                }
                bytes
            }
            _ => self.text.as_bytes().to_vec(),
        }
    }
    pub fn save(&mut self) -> Result<()> {
        ensure!(self.editable, "Read-only document");
        let raw = self.encode();
        ensure!(raw.len() as u64 <= TEXT_LIMIT, "Note exceeds 8 MB");
        let target = self.path.canonicalize()?;
        ensure!(
            read_limited(&target, TEXT_LIMIT)? == self.original,
            "File changed externally. Your edits remain here. Save as new note or reload."
        );
        ensure!(
            self.path.canonicalize()? == target,
            "File target changed externally"
        );
        atomic_write(&target, &raw)?;
        self.original = raw;
        Ok(())
    }
}
