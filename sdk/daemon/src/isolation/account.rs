use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use anyhow::{Context, Result, anyhow};

/// A local user account that the daemon runs commands as.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Account {
    pub name: String,
    pub uid: u32,
    pub gid: u32,
    pub home: PathBuf,
}

impl Account {
    /// Look `name` up in `/etc/passwd`.
    pub fn lookup(name: &str) -> Result<Self> {
        Self::lookup_in(Path::new("/etc/passwd"), name)
    }

    pub fn lookup_in(passwd: &Path, name: &str) -> Result<Self> {
        let content = std::fs::read_to_string(passwd)
            .with_context(|| format!("failed to read {}", passwd.display()))?;
        parse_passwd(&content, name)
            .ok_or_else(|| anyhow!("no user named {name} in {}", passwd.display()))
    }

    /// Whether this is the superuser, or the account the daemon runs as.
    /// Commands must never be "dropped" to either.
    pub fn is_privileged_or_self(&self) -> bool {
        self.uid == 0 || self.uid == effective_uid()
    }
}

/// Find `name` in the contents of a passwd file.
pub fn parse_passwd(content: &str, name: &str) -> Option<Account> {
    content.lines().find_map(|line| {
        let fields: Vec<&str> = line.split(':').collect();
        if fields.len() < 7 || fields[0] != name {
            return None;
        }
        Some(Account {
            name: name.to_string(),
            uid: fields[2].parse().ok()?,
            gid: fields[3].parse().ok()?,
            home: PathBuf::from(fields[5]),
        })
    })
}

pub fn effective_uid() -> u32 {
    // SAFETY: geteuid has no preconditions and cannot fail.
    unsafe { libc::geteuid() }
}

pub fn is_root() -> bool {
    effective_uid() == 0
}

/// The user the agent runs as (`SSE_AGENT_USER`, default `model`), whose
/// processes the daemon kills when the agent phase ends.
pub fn agent_account() -> &'static Account {
    static AGENT: OnceLock<Account> = OnceLock::new();
    AGENT.get_or_init(|| {
        let name = std::env::var("SSE_AGENT_USER").unwrap_or_else(|_| "model".to_string());
        Account::lookup(&name).unwrap_or_else(|e| {
            log::warn!("{e}; using uid 1000 for the agent user");
            Account {
                name,
                uid: 1000,
                gid: 1000,
                home: PathBuf::from("/home/model"),
            }
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const PASSWD: &str = "\
root:x:0:0:root:/root:/bin/bash
model:x:1000:1000::/home/model:/bin/bash
sse-runner:x:999:999::/nonexistent:/usr/sbin/nologin
broken:x:notanumber:5::/x:/bin/sh
short:x:1
";

    #[test]
    fn finds_an_account_by_name() {
        assert_eq!(
            parse_passwd(PASSWD, "sse-runner"),
            Some(Account {
                name: "sse-runner".into(),
                uid: 999,
                gid: 999,
                home: PathBuf::from("/nonexistent"),
            })
        );
        assert_eq!(parse_passwd(PASSWD, "model").map(|a| a.uid), Some(1000));
    }

    #[test]
    fn rejects_missing_and_malformed_entries() {
        assert_eq!(parse_passwd(PASSWD, "nobody"), None);
        assert_eq!(parse_passwd(PASSWD, "broken"), None);
        assert_eq!(parse_passwd(PASSWD, "short"), None);
        // A prefix of a name is not the name.
        assert_eq!(parse_passwd(PASSWD, "sse"), None);
    }

    #[test]
    fn lookup_reports_the_missing_user() {
        let dir = tempfile::tempdir().unwrap();
        let passwd = dir.path().join("passwd");
        std::fs::write(&passwd, PASSWD).unwrap();
        assert_eq!(Account::lookup_in(&passwd, "root").unwrap().uid, 0);
        let err = Account::lookup_in(&passwd, "ghost").unwrap_err();
        assert!(err.to_string().contains("ghost"), "{err}");
    }

    #[test]
    fn root_and_self_are_never_drop_targets() {
        let root = parse_passwd(PASSWD, "root").unwrap();
        assert!(root.is_privileged_or_self());
        let me = Account {
            name: "me".into(),
            uid: effective_uid(),
            gid: 0,
            home: PathBuf::new(),
        };
        assert!(me.is_privileged_or_self());
    }
}
