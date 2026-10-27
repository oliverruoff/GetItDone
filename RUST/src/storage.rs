use crate::model::Notebook;
use anyhow::{Context, Result, ensure};
use fs2::FileExt;
use std::{
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

pub struct Store {
    pub folder: PathBuf,
    _lock: File,
}
pub fn default_folder() -> PathBuf {
    let home = std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_default();
    if cfg!(target_os = "macos") {
        home.join("Library/Application Support/GetItDone/GetItDone")
    } else if cfg!(windows) {
        std::env::var_os("APPDATA")
            .map(PathBuf::from)
            .unwrap_or(home)
            .join("GetItDone/GetItDone")
    } else {
        std::env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .unwrap_or(home.join(".local/share"))
            .join("GetItDone/GetItDone")
    }
}
pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut temp = tempfile::NamedTempFile::new_in(path.parent().context("Missing parent")?)?;
    if path.exists() {
        temp.as_file()
            .set_permissions(fs::metadata(path)?.permissions())?;
    }
    temp.write_all(bytes)?;
    temp.as_file().sync_all()?;
    temp.persist(path).map_err(|e| e.error)?;
    #[cfg(unix)]
    File::open(path.parent().unwrap())?.sync_all()?;
    Ok(())
}
impl Store {
    pub fn open(folder: PathBuf) -> Result<(Self, Notebook)> {
        fs::create_dir_all(&folder)?;
        ensure!(
            !folder.join("instance.lock").exists(),
            "The archived Python app has an instance lock in this data folder. Quit that app before opening the same notebook in Rust."
        );
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(folder.join("notebook.lock"))?;
        lock.try_lock_exclusive()
            .context("This notebook is already open. Activate the running GetItDone window.")?;
        let path = folder.join("notebook.json");
        let book = if path.exists() {
            serde_json::from_slice::<Notebook>(&fs::read(&path)?)
                .context("Could not read notebook; original and backup preserved")?
        } else {
            Notebook::default()
        };
        book.validate()?;
        Ok((
            Self {
                folder,
                _lock: lock,
            },
            book,
        ))
    }
    pub fn save(&self, book: &Notebook) -> Result<()> {
        book.validate()?;
        let path = self.folder.join("notebook.json");
        if path.exists() {
            let raw = fs::read(&path)?;
            let previous: Notebook = serde_json::from_slice(&raw)?;
            previous.validate()?;
            atomic_write(&self.folder.join("notebook.backup.json"), &raw)?;
        }
        atomic_write(&path, &serde_json::to_vec_pretty(book)?)
    }
}
pub fn read_limited(path: &Path, limit: u64) -> Result<Vec<u8>> {
    use std::io::Read;
    let mut out = Vec::new();
    File::open(path)?.take(limit + 1).read_to_end(&mut out)?;
    ensure!(out.len() as u64 <= limit, "File exceeds preview limit");
    Ok(out)
}
