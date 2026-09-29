# Check https://github.com/openai/codex/blob/main/docs/example-config.md
# for the full config template
CONFIG_TEMPLATE = {
    "model": "",
    "review_model": "",
    "model_provider": "ssebench",
    "approval_policy": "never",
    "sandbox_mode": "workspace-write",
    # The run container reaches the LiteLLM proxy only.
    "check_for_update_on_startup": False,
    "analytics": {"enabled": False},
    "otel": {"metrics_exporter": "none"},
    "mcp_servers": {
        "ssebench": {
            "url": "",
            "startup_timeout_sec": 300.0,
            "tool_timeout_sec": 3600.0,
        }
    },
    "model_providers": {
        "ssebench": {
            "name": "SSE-Bench",
            "base_url": "",
            "wire_api": "responses",
            "env_key": "SSE_API_KEY",
        }
    },
}
