use anyhow::{Result, bail, ensure};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{HashMap, HashSet};

pub fn uid() -> String {
    uuid::Uuid::new_v4().to_string()
}
pub fn now() -> String {
    Utc::now().to_rfc3339()
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Item {
    pub id: String,
    pub parent_id: Option<String>,
    pub position: usize,
    pub text: String,
    pub notes: String,
    pub done: bool,
    pub category_id: Option<String>,
    pub reminder: Option<Value>,
    pub created_at: String,
    pub updated_at: String,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Category {
    pub id: String,
    pub name: String,
    pub color: String,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Session {
    pub id: String,
    pub item_id: String,
    pub agent: String,
    pub workdir: String,
    pub title: String,
    pub native_session_id: Option<String>,
    #[serde(default)]
    pub model: Option<String>,
    pub created_at: String,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Notebook {
    pub schema_version: u32,
    pub settings: Value,
    pub categories: Vec<Category>,
    pub items: Vec<Item>,
    pub sessions: Vec<Session>,
}
impl Default for Notebook {
    fn default() -> Self {
        Self {
            schema_version: 1,
            settings: json!({"default_agent":"opencode", "default_workdir":""}),
            categories: vec![],
            items: vec![],
            sessions: vec![],
        }
    }
}
impl Notebook {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.schema_version == 1,
            "Unknown notebook version; original preserved"
        );
        ensure!(self.settings.is_object(), "Invalid settings");
        let mut ids = HashSet::new();
        for id in self
            .items
            .iter()
            .map(|x| &x.id)
            .chain(self.categories.iter().map(|x| &x.id))
            .chain(self.sessions.iter().map(|x| &x.id))
        {
            ensure!(!id.is_empty() && ids.insert(id), "Missing or duplicate ID");
        }
        for i in &self.items {
            let mut seen = HashSet::from([i.id.as_str()]);
            let mut p = i.parent_id.as_deref();
            while let Some(id) = p {
                ensure!(seen.insert(id), "Circular hierarchy");
                p = self
                    .item(id)
                    .ok_or_else(|| anyhow::anyhow!("Missing parent"))?
                    .parent_id
                    .as_deref();
            }
            if let Some(id) = &i.category_id {
                ensure!(
                    self.categories.iter().any(|c| &c.id == id),
                    "Missing category"
                );
            }
            if let Some(r) = &i.reminder {
                chrono::DateTime::parse_from_rfc3339(r["at"].as_str().unwrap_or(""))?;
            }
        }
        for s in &self.sessions {
            ensure!(self.item(&s.item_id).is_some(), "Missing session task");
        }
        Ok(())
    }
    pub fn item(&self, id: &str) -> Option<&Item> {
        self.items.iter().find(|i| i.id == id)
    }
    pub fn item_mut(&mut self, id: &str) -> Option<&mut Item> {
        self.items.iter_mut().find(|i| i.id == id)
    }
    pub fn children(&self, parent: Option<&str>) -> Vec<String> {
        let mut rows: Vec<_> = self
            .items
            .iter()
            .filter(|i| i.parent_id.as_deref() == parent)
            .collect();
        rows.sort_by_key(|i| i.position);
        rows.iter().map(|i| i.id.clone()).collect()
    }
    pub fn descendants(&self, id: &str) -> Vec<String> {
        let mut out = vec![];
        for child in self.children(Some(id)) {
            out.push(child.clone());
            out.extend(self.descendants(&child));
        }
        out
    }
    pub fn ancestors(&self, id: &str) -> Vec<String> {
        let mut out = vec![];
        let mut p = self.item(id).and_then(|i| i.parent_id.clone());
        while let Some(id) = p {
            p = self.item(&id).and_then(|i| i.parent_id.clone());
            out.push(id);
        }
        out
    }
    pub fn add(
        &mut self,
        text: &str,
        parent: Option<String>,
        after: Option<&str>,
    ) -> Result<String> {
        if let Some(p) = &parent {
            ensure!(self.item(p).is_some(), "Parent does not exist");
        }
        let siblings = self.children(parent.as_deref());
        let pos = after
            .and_then(|id| siblings.iter().position(|s| s == id))
            .map(|p| p + 1)
            .unwrap_or(siblings.len());
        for id in siblings.iter().skip(pos) {
            self.item_mut(id).unwrap().position += 1;
        }
        let id = uid();
        self.items.push(Item {
            id: id.clone(),
            parent_id: parent,
            position: pos,
            text: text.into(),
            notes: String::new(),
            done: false,
            category_id: None,
            reminder: None,
            created_at: now(),
            updated_at: now(),
        });
        for p in self.ancestors(&id) {
            self.item_mut(&p).unwrap().done = false;
        }
        Ok(id)
    }
    pub fn complete(&mut self, id: &str, done: bool) -> HashMap<String, bool> {
        let mut ids = vec![id.to_owned()];
        ids.extend(if done {
            self.descendants(id)
        } else {
            self.ancestors(id)
        });
        let mut snapshot = HashMap::new();
        for id in ids {
            if let Some(i) = self.item_mut(&id) {
                snapshot.insert(id, i.done);
                i.done = done;
                i.updated_at = now();
            }
        }
        snapshot
    }
    pub fn restore_completion(&mut self, snapshot: &HashMap<String, bool>) {
        for (id, done) in snapshot {
            if let Some(i) = self.item_mut(id) {
                i.done = *done;
            }
        }
        for (id, done) in snapshot {
            if !done {
                for p in self.ancestors(id) {
                    self.item_mut(&p).unwrap().done = false;
                }
            }
        }
    }
    pub fn delete(&mut self, id: &str) -> Vec<String> {
        let parent = self.item(id).and_then(|i| i.parent_id.clone());
        let mut ids = self.descendants(id);
        ids.push(id.into());
        let sessions = self
            .sessions
            .iter()
            .filter(|s| ids.contains(&s.item_id))
            .map(|s| s.id.clone())
            .collect();
        self.items.retain(|i| !ids.contains(&i.id));
        self.sessions.retain(|s| !ids.contains(&s.item_id));
        self.normalize(parent.as_deref());
        sessions
    }
    fn normalize(&mut self, parent: Option<&str>) {
        for (position, id) in self.children(parent).into_iter().enumerate() {
            self.item_mut(&id).unwrap().position = position;
        }
    }
    pub fn shift(&mut self, id: &str, delta: isize) {
        if let Some(i) = self.item(id) {
            let siblings = self.children(i.parent_id.as_deref());
            if let Some(p) = siblings.iter().position(|x| x == id) {
                let n = p as isize + delta;
                if n >= 0 && (n as usize) < siblings.len() {
                    let other = &siblings[n as usize];
                    let a = self.item(id).unwrap().position;
                    let b = self.item(other).unwrap().position;
                    self.item_mut(id).unwrap().position = b;
                    self.item_mut(other).unwrap().position = a;
                }
            }
        }
    }
    pub fn indent(&mut self, id: &str, out: bool) {
        let Some(item) = self.item(id).cloned() else {
            return;
        };
        let (parent, after) = if out {
            let Some(p) = item.parent_id.as_ref().and_then(|p| self.item(p)) else {
                return;
            };
            (p.parent_id.clone(), Some(p.id.clone()))
        } else {
            let siblings = self.children(item.parent_id.as_deref());
            let Some(pos) = siblings.iter().position(|s| s == id) else {
                return;
            };
            if pos == 0 {
                return;
            }
            (Some(siblings[pos - 1].clone()), None)
        };
        let pos = after
            .as_ref()
            .and_then(|p| self.item(p))
            .map(|i| i.position + 1)
            .unwrap_or(self.children(parent.as_deref()).len());
        for sibling in self.children(parent.as_deref()) {
            if self.item(&sibling).unwrap().position >= pos {
                self.item_mut(&sibling).unwrap().position += 1;
            }
        }
        let i = self.item_mut(id).unwrap();
        i.parent_id = parent;
        i.position = pos;
        self.normalize(item.parent_id.as_deref());
        if !item.done {
            for p in self.ancestors(id) {
                self.item_mut(&p).unwrap().done = false;
            }
        }
    }
    pub fn visible(&self, query: &str, status: &str) -> HashSet<String> {
        let mut result = HashSet::new();
        let q = query.to_lowercase();
        for i in &self.items {
            if (status == "all" || i.done == (status == "done"))
                && format!("{}\n{}", i.text, i.notes)
                    .to_lowercase()
                    .contains(&q)
            {
                result.insert(i.id.clone());
                result.extend(self.ancestors(&i.id));
            }
        }
        result
    }
    pub fn new_session(&mut self, item_id: &str, agent: &str, workdir: &str) -> Result<String> {
        let title = self
            .item(item_id)
            .ok_or_else(|| anyhow::anyhow!("Select a task"))?
            .text
            .clone();
        ensure!(
            std::path::Path::new(workdir).is_dir(),
            "Select an existing working folder"
        );
        if !["opencode", "codex", "pi", "claude"].contains(&agent)
            && !self.settings["profiles"]
                .as_array()
                .is_some_and(|profiles| profiles.iter().any(|p| p["id"] == agent))
        {
            bail!("Unknown agent");
        }
        let id = uid();
        let native = match agent {
            "codex" => None,
            "opencode" => Some(format!("ses_{}", uid().replace('-', ""))),
            _ => Some(uid()),
        };
        self.sessions.push(Session {
            id: id.clone(),
            item_id: item_id.into(),
            agent: agent.into(),
            workdir: workdir.into(),
            title,
            native_session_id: native,
            model: None,
            created_at: now(),
        });
        Ok(id)
    }
}
