use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use crate::bench::BenchCore;
use crate::isolation::TaskRunner;
use crate::tools::ToolRouter;

/// Difficulty level, read once from `SSE_DIFFICULTY` at startup. It decides
/// which `bencher` actions the agent-facing listeners expose. The mapping
/// mirrors the MCP server's `TestConfig` so the two enforcement points agree.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Difficulty {
    FullAssistance = 0,
    NoIntentTest = 1,
    NoFutureTest = 2,
    BuildOnly = 3,
    NoBuild = 4,
}

impl Difficulty {
    /// Read `SSE_DIFFICULTY`: unset means the default, `NO_FUTURE_TEST`.
    pub fn from_env() -> anyhow::Result<Self> {
        Self::parse(std::env::var("SSE_DIFFICULTY").ok().as_deref())
    }

    /// Parse a level from 0 to 4. Any other value is an error rather than the
    /// default, so a run never goes ahead at a level nobody asked for.
    pub fn parse(value: Option<&str>) -> anyhow::Result<Self> {
        let Some(value) = value else {
            return Ok(Difficulty::NoFutureTest);
        };
        match value.trim().parse::<u8>() {
            Ok(0) => Ok(Difficulty::FullAssistance),
            Ok(1) => Ok(Difficulty::NoIntentTest),
            Ok(2) => Ok(Difficulty::NoFutureTest),
            Ok(3) => Ok(Difficulty::BuildOnly),
            Ok(4) => Ok(Difficulty::NoBuild),
            _ => anyhow::bail!("SSE_DIFFICULTY must be an integer from 0 to 4, got {value:?}"),
        }
    }

    /// Whether an agent-facing caller may invoke this `bencher` action at this
    /// level. Non-`bencher` tools (e.g. `bash`) are never gated here.
    pub fn allows_bencher_action(self, action: &str) -> bool {
        match action {
            "build" => self <= Difficulty::BuildOnly,
            "function_test" => self <= Difficulty::NoFutureTest,
            "run_poc" => self <= Difficulty::NoIntentTest,
            "intent_test" => self <= Difficulty::FullAssistance,
            // Unknown actions are left to the tool router to reject.
            _ => true,
        }
    }
}

/// Marks whether a request arrived on a privileged listener. Registered as
/// per-listener application data so the same handlers can serve both the
/// agent-facing listeners (untrusted) and the root-only admin socket.
#[derive(Clone, Copy)]
pub struct Access {
    pub privileged: bool,
}

/// Application state made available to all request handlers. Actix clones this struct once per
/// worker thread, so only fields wrapped in `Arc` are truly shared across the entire application.
/// Other fields would be independently cloned per worker.
///
/// # Note
///
/// ToolRouter is guarded by a Mutex because the daemon’s tool workflow is logically
/// stateful and must run sequentially. Although the API surface looks stateless, tools operate on
/// shared internal state (e.g., a temporary working directory).
///
/// Certain tool sequences, such as `build` followed by `test`, must run on the same underlying
/// state, which requires `&mut self` access inside ToolRouter. Since multiple Actix workers may
/// attempt to invoke tools concurrently, we wrap ToolRouter in `Arc<Mutex<_>>` to ensure
/// exclusive, serialized access to this stateful workflow.
///
/// If we ever support true multi‑agent workflows, this Mutex will need to be replaced with a
/// session‑scoped mechanism (e.g., a per‑agent session token managed by the SDK). Each agent would
/// require isolated tool state rather than contending for a single global ToolRouter lock.
///
/// How multi‑agent isolation should interact with the MCP server model is still an open design
/// question. This is a future exploration topic and not a near‑term requirement.
pub struct AppState {
    pub project: Arc<BenchCore>,
    pub tool_router: Arc<Mutex<ToolRouter>>,
    /// Difficulty gate applied to agent-facing `bencher` calls.
    pub difficulty: Difficulty,
    /// `false` while the agent is working, flipped to `true` (once) by the
    /// entrypoint over the admin socket after the agent exits. The reference
    /// patch is withheld from agent-facing listeners until then.
    pub agent_phase_ended: Arc<AtomicBool>,
}

impl AppState {
    /// A state whose checks run as the daemon's own user, in a temporary
    /// scratch directory: for tests and a daemon that is not root.
    pub fn new(project: BenchCore, difficulty: Difficulty) -> Self {
        let scratch = tempfile::Builder::new()
            .prefix("ssebench-runner-")
            .tempdir()
            .map(|dir| dir.keep())
            .expect("failed to create a scratch directory");
        let runner = TaskRunner::unprivileged(&scratch).expect("failed to prepare the task runner");
        Self::with_runner(project, difficulty, runner)
    }

    /// A state whose checks run through `runner`.
    pub fn with_runner(project: BenchCore, difficulty: Difficulty, runner: TaskRunner) -> Self {
        let project = Arc::new(project);
        let router = ToolRouter::new(Arc::clone(&project), runner);
        Self {
            project,
            tool_router: Arc::new(Mutex::new(router)),
            difficulty,
            agent_phase_ended: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Report whether the agent phase has ended.
    pub fn agent_phase_ended(&self) -> bool {
        self.agent_phase_ended.load(Ordering::SeqCst)
    }

    /// Mark the agent phase as ended. Idempotent.
    pub fn end_agent_phase(&self) {
        self.agent_phase_ended.store(true, Ordering::SeqCst);
    }
}

impl Clone for AppState {
    fn clone(&self) -> Self {
        Self {
            project: Arc::clone(&self.project),
            tool_router: Arc::clone(&self.tool_router),
            difficulty: self.difficulty,
            agent_phase_ended: Arc::clone(&self.agent_phase_ended),
        }
    }
}

#[cfg(test)]
mod difficulty_tests {
    use super::Difficulty;

    // Actions the agent-facing `bencher` tool can request.
    const ACTIONS: [&str; 4] = ["build", "function_test", "run_poc", "intent_test"];

    fn allowed(level: Difficulty) -> Vec<&'static str> {
        ACTIONS
            .into_iter()
            .filter(|a| level.allows_bencher_action(a))
            .collect()
    }

    #[test]
    fn full_assistance_allows_everything() {
        assert_eq!(
            allowed(Difficulty::FullAssistance),
            vec!["build", "function_test", "run_poc", "intent_test"],
        );
    }

    #[test]
    fn no_intent_test_hides_intent() {
        assert_eq!(
            allowed(Difficulty::NoIntentTest),
            vec!["build", "function_test", "run_poc"],
        );
    }

    #[test]
    fn default_no_future_test_hides_poc_and_intent() {
        assert_eq!(
            allowed(Difficulty::NoFutureTest),
            vec!["build", "function_test"],
        );
    }

    #[test]
    fn build_only_hides_all_tests() {
        assert_eq!(allowed(Difficulty::BuildOnly), vec!["build"]);
    }

    #[test]
    fn no_build_hides_everything() {
        assert!(allowed(Difficulty::NoBuild).is_empty());
    }

    #[test]
    fn unset_level_is_the_default() {
        assert_eq!(Difficulty::parse(None).unwrap(), Difficulty::NoFutureTest);
    }

    #[test]
    fn levels_zero_to_four_parse() {
        let levels: Vec<Difficulty> = ["0", "1", " 2 ", "3", "4"]
            .into_iter()
            .map(|v| Difficulty::parse(Some(v)).unwrap())
            .collect();
        assert_eq!(
            levels,
            vec![
                Difficulty::FullAssistance,
                Difficulty::NoIntentTest,
                Difficulty::NoFutureTest,
                Difficulty::BuildOnly,
                Difficulty::NoBuild,
            ],
        );
    }

    #[test]
    fn invalid_levels_are_rejected() {
        for value in ["", "5", "-1", "256", "two", "2.0"] {
            let err = Difficulty::parse(Some(value)).unwrap_err();
            assert!(err.to_string().contains("0 to 4"), "{value:?}: {err}");
        }
    }

    #[test]
    fn unknown_actions_are_not_gated_here() {
        // Non-bencher tools (e.g. bash) and unknown actions pass through the
        // gate; the tool router is responsible for rejecting invalid ones.
        for level in [Difficulty::NoBuild, Difficulty::FullAssistance] {
            assert!(level.allows_bencher_action("bash"));
        }
    }
}
