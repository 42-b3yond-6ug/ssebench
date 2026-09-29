//! Contract test between the daemon and `openapi.yaml`, its hand-written API
//! description. It fails when a route, a method, an access rule, the
//! difficulty gate or a response field changes on one side only.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;

use actix_web::http::{Method, StatusCode};
use actix_web::test as actix_test;
use actix_web::{App, web};
use serde_json::Value as Json;
use serde_yaml::Value as Yaml;
use ssebench::api::{Access, AppState, Difficulty, ROUTES, configure_routes};
use ssebench::bench::BenchCore;
use tempfile::TempDir;

const SPEC: &str = include_str!("../openapi.yaml");
const METHODS: [&str; 5] = ["get", "post", "put", "patch", "delete"];
const ACCESS: [&str; 3] = ["any", "admin", "after-agent"];
const LEVELS: [Difficulty; 5] = [
    Difficulty::FullAssistance,
    Difficulty::NoIntentTest,
    Difficulty::NoFutureTest,
    Difficulty::BuildOnly,
    Difficulty::NoBuild,
];
const REFERENCE_PATCH: &str = "--- a/f\n+++ b/f\n";

fn spec() -> Yaml {
    serde_yaml::from_str(SPEC).expect("openapi.yaml is not valid YAML")
}

struct Operation {
    method: String,
    path: String,
    access: String,
    op: Yaml,
}

impl Operation {
    fn statuses(&self) -> BTreeSet<u16> {
        self.op["responses"]
            .as_mapping()
            .unwrap_or_else(|| panic!("{} {} has no responses", self.method, self.path))
            .keys()
            .map(|k| {
                k.as_str()
                    .and_then(|s| s.parse().ok())
                    .expect("status codes are quoted numbers")
            })
            .collect()
    }

    /// Highest difficulty level that runs each gated action, from `x-difficulty-gate`.
    fn gate(&self) -> Option<(String, BTreeMap<String, u8>)> {
        let gate = self.op.get("x-difficulty-gate")?;
        let tool = gate["tool"]
            .as_str()
            .expect("x-difficulty-gate.tool")
            .to_string();
        let actions = gate["actions"]
            .as_mapping()
            .expect("x-difficulty-gate.actions")
            .iter()
            .map(|(k, v)| {
                let level = v.as_u64().expect("a level from 0 to 4");
                (
                    k.as_str().unwrap().to_string(),
                    u8::try_from(level).unwrap(),
                )
            })
            .collect();
        Some((tool, actions))
    }

    /// A concrete URI: `{name}` becomes the gated tool, or `bash`.
    fn uri(&self) -> String {
        let tool = self.gate().map_or("bash".to_string(), |(tool, _)| tool);
        self.path.replace("{name}", &tool)
    }
}

fn operations(spec: &Yaml) -> Vec<Operation> {
    let mut found = Vec::new();
    for (path, item) in spec["paths"].as_mapping().expect("paths") {
        let path = path.as_str().unwrap();
        for (method, op) in item.as_mapping().unwrap() {
            let method = method.as_str().unwrap();
            if !METHODS.contains(&method) {
                continue;
            }
            let access = op["x-access"]
                .as_str()
                .unwrap_or_else(|| panic!("{method} {path} has no x-access"))
                .to_string();
            found.push(Operation {
                method: method.to_string(),
                path: path.to_string(),
                access,
                op: op.clone(),
            });
        }
    }
    found
}

/// A task with a reference patch and no scripts, so no action has side effects.
fn bench() -> (TempDir, BenchCore) {
    let dir = TempDir::new().unwrap();
    let source = dir.path().join("src");
    fs::create_dir(&source).unwrap();
    // An invalid gitfile makes every git command fail at once, instead of
    // finding a repository that happens to enclose the temporary directory.
    fs::write(source.join(".git"), "not a gitdir\n").unwrap();
    fs::write(dir.path().join("patch.diff"), REFERENCE_PATCH).unwrap();
    let config = format!(
        "id: contract\nproject: contract\nlanguage: c\nsource: {}\n\
         task_description:\n  bug_description: test\nscripts: {{}}\nfiles:\n  patch: patch.diff\n",
        source.display()
    );
    fs::write(dir.path().join("config.yaml"), config).unwrap();
    let core = BenchCore::new(dir.path()).unwrap();
    (dir, core)
}

fn app_state(core: &BenchCore, difficulty: Difficulty) -> AppState {
    AppState::new(core.clone(), difficulty)
}

/// One listener: the agent-facing ones are unprivileged, the admin socket is
/// privileged. Listeners made from clones of one state share its phase.
struct Listener {
    state: AppState,
    privileged: bool,
}

impl Listener {
    async fn call(&self, method: &str, uri: &str) -> (StatusCode, Json) {
        let app = actix_test::init_service(
            App::new()
                .app_data(web::Data::new(self.state.clone()))
                .app_data(web::Data::new(Access {
                    privileged: self.privileged,
                }))
                .configure(configure_routes),
        )
        .await;
        let method = Method::from_bytes(method.to_uppercase().as_bytes()).unwrap();
        let mut request = actix_test::TestRequest::default()
            .method(method.clone())
            .uri(uri);
        if method == Method::POST {
            request = request.set_json(serde_json::json!({}));
        }
        let response = actix_test::call_service(&app, request.to_request()).await;
        let status = response.status();
        let body = actix_test::read_body(response).await;
        (status, serde_json::from_slice(&body).unwrap_or(Json::Null))
    }
}

fn listeners(state: &AppState) -> (Listener, Listener) {
    let agent = Listener {
        state: state.clone(),
        privileged: false,
    };
    let admin = Listener {
        state: state.clone(),
        privileged: true,
    };
    (agent, admin)
}

fn resolve<'a>(spec: &'a Yaml, schema: &'a Yaml) -> &'a Yaml {
    match schema.get("$ref").and_then(Yaml::as_str) {
        Some(reference) => {
            let name = reference
                .strip_prefix("#/components/schemas/")
                .expect("local $ref");
            &spec["components"]["schemas"][name]
        }
        None => schema,
    }
}

/// Every field of `value` must be documented in `schema`, and every required
/// field present, recursively through objects and arrays.
fn check_shape(spec: &Yaml, schema: &Yaml, value: &Json, at: &str, problems: &mut Vec<String>) {
    let schema = resolve(spec, schema);
    match value {
        Json::Object(fields) => {
            let Some(properties) = schema.get("properties").and_then(Yaml::as_mapping) else {
                return;
            };
            for (name, field) in fields {
                match properties.get(name.as_str()) {
                    Some(sub) => check_shape(spec, sub, field, &format!("{at}.{name}"), problems),
                    None => problems.push(format!("{at}.{name} is not documented")),
                }
            }
            for required in schema["required"].as_sequence().into_iter().flatten() {
                let required = required.as_str().unwrap();
                if !fields.contains_key(required) {
                    problems.push(format!("{at}.{required} is required but missing"));
                }
            }
        }
        Json::Array(items) => {
            if let Some(item) = schema.get("items") {
                for (i, value) in items.iter().enumerate() {
                    check_shape(spec, item, value, &format!("{at}[{i}]"), problems);
                }
            }
        }
        _ => {}
    }
}

fn response_schema(op: &Operation, status: StatusCode) -> Option<&Yaml> {
    op.op["responses"][status.as_str()]
        .get("content")
        .map(|content| &content["application/json"]["schema"])
}

#[test]
fn every_route_is_described_and_nothing_else() {
    let described: BTreeSet<(String, String)> = operations(&spec())
        .into_iter()
        .map(|op| (op.method, op.path))
        .collect();
    let served: BTreeSet<(String, String)> = ROUTES
        .iter()
        .map(|(method, path)| (method.to_string(), path.to_string()))
        .collect();
    assert_eq!(ROUTES.len(), served.len(), "a route is registered twice");
    let undocumented: Vec<_> = served.difference(&described).collect();
    let unserved: Vec<_> = described.difference(&served).collect();
    assert!(
        undocumented.is_empty() && unserved.is_empty(),
        "openapi.yaml and the routes in src/api/handlers.rs differ.\n\
         Served but not described: {undocumented:?}\nDescribed but not served: {unserved:?}"
    );
}

#[test]
fn access_rules_are_known_and_document_403() {
    for op in operations(&spec()) {
        assert!(
            ACCESS.contains(&op.access.as_str()),
            "{} {}: unknown x-access {:?}",
            op.method,
            op.path,
            op.access
        );
        let refuses = op.access != "any" || op.gate().is_some();
        assert_eq!(
            op.statuses().contains(&403),
            refuses,
            "{} {}: a 403 response must be documented exactly when an agent-facing listener can refuse it",
            op.method,
            op.path
        );
    }
}

#[actix_web::test]
async fn listeners_enforce_the_documented_access() {
    let spec = spec();
    let (_dir, core) = bench();
    let mut problems = Vec::new();
    for op in operations(&spec) {
        // A fresh state each time: POST /admin/agent_exited must not unlock later operations.
        let (agent, admin) = listeners(&app_state(&core, Difficulty::FullAssistance));
        let uri = op.uri();
        let (status, body) = agent.call(&op.method, &uri).await;
        let refused = status == StatusCode::FORBIDDEN;
        match op.access.as_str() {
            "any" if refused => problems.push(format!("{} {uri}: agent-facing 403", op.method)),
            "admin" | "after-agent" if !refused => problems.push(format!(
                "{} {uri}: agent-facing {status}, expected 403",
                op.method
            )),
            _ => {}
        }
        if matches!(
            status,
            StatusCode::NOT_FOUND | StatusCode::METHOD_NOT_ALLOWED
        ) {
            problems.push(format!("{} {uri}: agent-facing {status}", op.method));
        }
        if !op.statuses().contains(&status.as_u16()) {
            problems.push(format!("{} {uri}: {status} is not documented", op.method));
        } else if let Some(schema) = response_schema(&op, status) {
            check_shape(
                &spec,
                schema,
                &body,
                &format!("{} {uri} {status}", op.method),
                &mut problems,
            );
        }

        let (status, _) = admin.call(&op.method, &uri).await;
        if status == StatusCode::FORBIDDEN {
            problems.push(format!("{} {uri}: admin socket 403", op.method));
        }
    }
    assert!(
        problems.is_empty(),
        "the daemon and openapi.yaml differ:\n{}",
        problems.join("\n")
    );
}

#[actix_web::test]
async fn reference_patch_unlocks_when_the_agent_exits() {
    let spec = spec();
    let (_dir, core) = bench();
    let (agent, admin) = listeners(&app_state(&core, Difficulty::NoFutureTest));

    let unlocking: Vec<_> = operations(&spec)
        .into_iter()
        .filter(|op| op.access == "after-agent")
        .collect();
    assert!(
        !unlocking.is_empty(),
        "no operation is x-access: after-agent"
    );
    for op in &unlocking {
        let (status, _) = agent.call(&op.method, &op.uri()).await;
        assert_eq!(
            status,
            StatusCode::FORBIDDEN,
            "{} {} before the agent exits",
            op.method,
            op.path
        );
    }

    let (status, _) = admin.call("post", "/admin/agent_exited").await;
    assert_eq!(status, StatusCode::OK);

    for op in &unlocking {
        let (status, body) = agent.call(&op.method, &op.uri()).await;
        assert_eq!(
            status,
            StatusCode::OK,
            "{} {} after the agent exits",
            op.method,
            op.path
        );
        let mut problems = Vec::new();
        let schema = response_schema(op, status).expect("a documented 200 body");
        check_shape(&spec, schema, &body, &op.path, &mut problems);
        assert!(problems.is_empty(), "{}", problems.join("\n"));
    }
    let (_, body) = agent.call("get", "/reference/patch").await;
    assert_eq!(body["diff"], REFERENCE_PATCH);

    for op in operations(&spec)
        .into_iter()
        .filter(|op| op.access == "admin")
    {
        let (status, _) = agent.call(&op.method, &op.uri()).await;
        assert_eq!(
            status,
            StatusCode::FORBIDDEN,
            "{} {} after the agent exits",
            op.method,
            op.path
        );
    }
}

#[actix_web::test]
async fn difficulty_gate_matches_the_description() {
    let spec = spec();
    let gated: Vec<_> = operations(&spec)
        .into_iter()
        .filter(|op| op.gate().is_some())
        .collect();
    assert!(!gated.is_empty(), "no operation has x-difficulty-gate");
    let (_dir, core) = bench();

    for op in gated {
        let (tool, actions) = op.gate().unwrap();
        for level in LEVELS {
            let (agent, admin) = listeners(&app_state(&core, level));
            for (action, highest) in &actions {
                let uri = format!("{}?action={action}", op.path.replace("{name}", &tool));
                let (status, _) = agent.call(&op.method, &uri).await;
                let withheld = level as u8 > *highest;
                assert_eq!(
                    status == StatusCode::FORBIDDEN,
                    withheld,
                    "{uri} at difficulty {level:?} on an agent-facing listener answered {status}"
                );
                assert_eq!(
                    level.allows_bencher_action(action),
                    !withheld,
                    "{action} at {level:?}"
                );
                let (status, _) = admin.call(&op.method, &uri).await;
                assert_ne!(
                    status,
                    StatusCode::FORBIDDEN,
                    "{uri} at {level:?} on the admin socket"
                );
            }
        }
    }
}
