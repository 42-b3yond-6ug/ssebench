---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "SSEBench"
  text: "Software Security Benchmark for AI Code Agents"
  tagline: "Measure how well AI coding agents fix real security vulnerabilities"
  actions:
    - theme: brand
      text: Get Started
      link: /guide/getting-started
    - theme: alt
      text: What is SSEBench?
      link: /guide/introduction
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
    title: Comprehensive Evaluation
    details: >
      Every patch is graded on build success, PoC reproduction, functional
      tests and the tests that came with the upstream fix.
  - icon: "🔧"
    title: Extensible Architecture
    details: >
      Easy integration of new models via YAML configs and new agents via Docker.
      Supports sandbox and sidecar execution modes.
---
