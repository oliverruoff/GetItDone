use serde::Serialize;
use std::path::{Path, PathBuf};
#[derive(Clone, Serialize)]
pub struct Finding {
    pub kind: String,
    pub name: String,
    pub path: String,
    pub scope: String,
    pub state: String,
    pub content: String,
}
pub fn discover(agent: &str, workdir: &Path) -> Vec<Finding> {
    let home = crate::agents::home();
    let mut out = vec![];
    let mut add = |kind: &str,
                   path: &Path,
                   scope: &str,
                   state: &str,
                   name: Option<String>,
                   content: Option<String>| {
        if !path.is_file() {
            return;
        }
        let content = content.unwrap_or_else(|| {
            crate::storage::read_limited(path, 65536)
                .ok()
                .map(|b| String::from_utf8_lossy(&b).into())
                .unwrap_or_else(|| "Preview unavailable (64 KiB limit)".into())
        });
        out.push(Finding {
            kind: kind.into(),
            name: name.unwrap_or_else(|| {
                path.file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .into()
            }),
            path: path.display().to_string(),
            scope: scope.into(),
            state: state.into(),
            content,
        });
    };
    let global = match agent {
        "codex" => crate::agents::codex_root(),
        "pi" => std::env::var_os("PI_CODING_AGENT_DIR")
            .map(PathBuf::from)
            .unwrap_or(home.join(".pi/agent")),
        "claude" => std::env::var_os("CLAUDE_CONFIG_DIR")
            .map(PathBuf::from)
            .unwrap_or(home.join(".claude")),
        _ => std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .unwrap_or(home.join(".config"))
            .join("opencode"),
    };
    let global_names = match agent {
        "codex" => vec!["AGENTS.override.md", "AGENTS.md"],
        "claude" => vec!["CLAUDE.md"],
        "pi" => vec![
            "AGENTS.md",
            "AGENTS.MD",
            "CLAUDE.md",
            "CLAUDE.MD",
            "SYSTEM.md",
            "APPEND_SYSTEM.md",
        ],
        _ => vec!["AGENTS.md"],
    };
    for name in global_names {
        add(
            "Instructions",
            &global.join(name),
            "Global",
            if agent == "codex"
                && name == "AGENTS.md"
                && global.join("AGENTS.override.md").is_file()
            {
                "Overridden"
            } else {
                "Discovered"
            },
            None,
            None,
        );
    }
    let mut roots = vec![workdir.to_path_buf()];
    for p in workdir.ancestors().skip(1) {
        if agent == "codex" && roots.last().is_some_and(|p| p.join(".git").exists()) {
            break;
        }
        roots.push(p.to_path_buf());
    }
    if agent == "codex" && !roots.iter().any(|p| p.join(".git").exists()) {
        roots = vec![workdir.to_path_buf()];
    }
    roots.reverse();
    for root in &roots {
        let override_exists = agent == "codex" && root.join("AGENTS.override.md").is_file();
        for name in match agent {
            "claude" => vec!["CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"],
            "codex" => vec!["AGENTS.override.md", "AGENTS.md"],
            "pi" => vec![
                "AGENTS.md",
                "AGENTS.MD",
                "CLAUDE.md",
                "CLAUDE.MD",
                ".pi/SYSTEM.md",
                ".pi/APPEND_SYSTEM.md",
            ],
            _ => vec!["AGENTS.md"],
        } {
            add(
                "Instructions",
                &root.join(name),
                if root == workdir {
                    "Project"
                } else {
                    "Inherited"
                },
                if override_exists && name == "AGENTS.md" {
                    "Overridden"
                } else {
                    "Applies on next session start"
                },
                None,
                None,
            );
        }
    }
    let mut skills = vec![home.join(".agents/skills"), global.join("skills")];
    for root in &roots {
        skills.extend(match agent {
            "codex" => vec![root.join(".agents/skills")],
            "claude" => vec![root.join(".claude/skills")],
            "pi" => vec![root.join(".pi/skills")],
            _ => vec![root.join(".opencode/skills"), root.join(".agents/skills")],
        });
    }
    for root in skills {
        for e in walkdir::WalkDir::new(&root)
            .max_depth(5)
            .into_iter()
            .filter_map(Result::ok)
            .filter(|e| e.file_name() == "SKILL.md")
            .take(1000)
        {
            let p = e.path();
            add(
                "Skill",
                p,
                if p.starts_with(&global) || p.starts_with(home.join(".agents")) {
                    "Global"
                } else {
                    "Project"
                },
                "Available",
                p.parent()
                    .and_then(Path::file_name)
                    .map(|s| s.to_string_lossy().into()),
                None,
            );
        }
    }
    let mut configs: Vec<PathBuf> = match agent {
        "codex" => vec![global.join("config.toml")],
        "claude" => vec![home.join(".claude.json")],
        "pi" => vec![global.join("mcp.json")],
        _ => vec![global.join("opencode.json"), global.join("opencode.jsonc")],
    };
    for root in &roots {
        configs.extend(match agent {
            "codex" => vec![root.join(".codex/config.toml")],
            "claude" => vec![root.join(".mcp.json")],
            "pi" => vec![],
            _ => vec![root.join("opencode.json"), root.join("opencode.jsonc")],
        });
    }
    for path in configs {
        let Ok(raw) = crate::storage::read_limited(&path, 2 * 1024 * 1024) else {
            continue;
        };
        let text = String::from_utf8_lossy(&raw);
        let parsed: Option<serde_json::Value> = if path.extension().is_some_and(|s| s == "toml") {
            toml::from_str::<toml::Value>(&text)
                .ok()
                .and_then(|v| serde_json::to_value(v).ok())
        } else {
            json5::from_str(&text).ok()
        };
        if let Some(v) = parsed {
            for key in ["mcp_servers", "mcpServers", "mcp"] {
                if let Some(map) = v[key].as_object() {
                    for (name, value) in map {
                        let disabled = value["enabled"] == false || value["disabled"] == true;
                        add("MCP",&path,"Configuration",if disabled{"Disabled"}else{"Configured"},Some(name.clone()),Some("Connection and authentication have not been verified. Commands, URLs, arguments and credentials are hidden.".into()));
                    }
                }
            }
        }
    }
    let mut seen = std::collections::HashSet::new();
    out.retain(|f| seen.insert((f.kind.clone(), f.path.clone(), f.name.clone())));
    out
}

pub fn runtime_discover(agent: &str, workdir: &Path) -> Vec<Finding> {
    let mut findings = discover(agent, workdir);
    if agent == "codex" {
        match crate::agents::codex_rpc(
            "skills/list",
            serde_json::json!({"cwds":[workdir],"forceReload":false}),
        ) {
            Ok(result) => {
                if let Some(groups) = result["data"].as_array() {
                    findings.retain(|f| f.kind != "Skill");
                    for group in groups {
                        if let Some(skills) = group["skills"].as_array() {
                            for skill in skills {
                                let name = skill["name"].as_str().unwrap_or("Unnamed skill");
                                let path = skill["path"].as_str().unwrap_or("");
                                let content = crate::storage::read_limited(Path::new(path), 65536)
                                    .map(|b| String::from_utf8_lossy(&b).into_owned())
                                    .unwrap_or_default();
                                findings.push(Finding {
                                    kind: "Skill".into(),
                                    name: name.into(),
                                    path: path.into(),
                                    scope: format!(
                                        "Codex registry · {}",
                                        skill["scope"].as_str().unwrap_or("Registered")
                                    ),
                                    state: if skill["enabled"] == false {
                                        "Disabled"
                                    } else {
                                        "Registered · loads on demand"
                                    }
                                    .into(),
                                    content: format!(
                                        "{}\n\n{content}",
                                        skill["description"].as_str().unwrap_or("")
                                    ),
                                });
                            }
                        }
                    }
                }
            }
            Err(_) => findings.push(Finding {
                kind: "Notice".into(),
                name: "Codex skill registry unavailable; showing local sources".into(),
                path: String::new(),
                scope: "Local".into(),
                state: "Unknown".into(),
                content: String::new(),
            }),
        }
    } else if agent == "opencode" {
        for (operation, kind) in [("skill.list", "Skill"), ("mcp.list", "MCP")] {
            let result = crate::agents::opencode_api(
                operation,
                &[format!("location.directory={}", workdir.display())],
            );
            if let Ok(result) = result {
                let entries: Vec<(String, serde_json::Value)> = match result {
                    serde_json::Value::Array(list) => list
                        .into_iter()
                        .map(|v| {
                            (
                                v["name"]
                                    .as_str()
                                    .or(v["id"].as_str())
                                    .unwrap_or("Unknown")
                                    .to_owned(),
                                v,
                            )
                        })
                        .collect(),
                    serde_json::Value::Object(map) => map.into_iter().collect(),
                    _ => vec![],
                };
                for (name, value) in entries {
                    let state = if kind == "Skill" {
                        "Registered · loads on demand".into()
                    } else {
                        value["status"]["type"]
                            .as_str()
                            .or(value["status"].as_str())
                            .unwrap_or("Unknown")
                            .to_owned()
                    };
                    if let Some(f) = findings
                        .iter_mut()
                        .find(|f| f.kind == kind && f.name == name)
                    {
                        f.state = state;
                    } else {
                        findings.push(Finding {
                            kind: kind.into(),
                            name,
                            path: value["path"].as_str().unwrap_or("").into(),
                            scope: "OpenCode runtime".into(),
                            state,
                            content: if kind == "Skill" {
                                value["content"]
                                    .as_str()
                                    .or(value["description"].as_str())
                                    .unwrap_or("")
                                    .into()
                            } else {
                                "Commands, URLs and credentials are hidden.".into()
                            },
                        });
                    }
                }
            }
        }
    }
    findings
}
