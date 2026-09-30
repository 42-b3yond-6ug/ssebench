---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "SSEBench"
  text: "RL Environments for AI Coding Agents on Real Vulnerabilities"
  tagline: "Train agents to fix security bugs with verifiable rewards, and benchmark how well they do it"
  actions:
    - theme: brand
      text: Get started
      link: /getting-started/installation
    - theme: alt
      text: What is SSEBench?
      link: /getting-started/introduction
    - theme: alt
      text: View on GitHub
      link: https://github.com/42-b3yond-6ug/ssebench

features:
  - icon: "🔒"
    title: Real-World Vulnerability Tasks
    details: >
      Every task is a publicly disclosed bug in an open-source C, Go or Rust
      project, paired with its upstream fix.
  - icon: "🐳"
    title: Docker-Based Infrastructure
    details: >
      Isolated, reproducible environments using layered Docker images.
      Seamless model/agent decoupling through LiteLLM proxy.
  - icon: "🤖"
    title: Multi-Agent Support
    details: >
      Run Claude Code, Codex, OpenCode or your own agent against any model.
  - icon: "📊"
    title: Verifiable Rewards
    details: >
      Every patch is graded by running code: build success, PoC reproduction,
      functional tests and the tests that came with the upstream fix.
  - icon: "🛡️"
    title: Hard to Game
    details: >
      The agent never sees the reference fix or the hidden tests and cannot
      touch its own grade; a bypass suite attacks these defenses.
  - icon: "🔧"
    title: Extensible Architecture
    details: >
      Easy integration of new models via YAML configs and new agents via Docker.
      Supports sandbox and sidecar execution modes.
---
