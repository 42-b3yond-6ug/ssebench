---
outline: deep
---

# What is SSEBench?

SSEBench (Software Security Evaluation Benchmark) is a comprehensive benchmark for evaluating the security capabilities of AI code agents on vulnerability patching tasks.

## Overview

SSEBench provides:

- **Real-world vulnerability tasks**: All tests represent real bugs from open-source projects, human-verified and aligned with developer expectations
- **Model evaluation**: Test language models across various dimensions including tool-calling abilities, reasoning skills, and security knowledge
- **Agent evaluation**: Test code agents on their ability to plan, call tools, analyze code, and adapt to diverse vulnerabilities
- **Detailed reports**: Generate comprehensive reports assessing performance across multiple dimensions

## Key Features

### Docker-based Infrastructure

SSEBench runs all benchmark tasks in Docker containers, providing:

- Isolated, reproducible environments
- Consistent dependencies across tasks
- Easy scaling and deployment

### LiteLLM Proxy

Models and agents are decoupled through a LiteLLM proxy, allowing:

- Transparent model switching
- Support for 100+ LLM providers
- Unified API interface

### Multi-layer Docker Architecture

Tasks are built using a layered Docker image approach:

| Layer | Description |
|-------|-------------|
| **Base Image** | Language toolchain (C, Go or Rust) shared across tasks |
| **Case Image** | Project source code + build dependencies |
| **Tool Image** | MCP server and SDK tooling |
| **Agent Image** | Agent installation (Claude Code, Codex, etc.) |

## Supported Agents

SSEBench includes state-of-the-art code agents:

- **Claude Code** - Anthropic's CLI coding assistant
- **Codex** - OpenAI's code generation agent
- **OpenCode** - Open-source terminal coding agent
- **dummy** - A no-op agent for testing the pipeline

## Use Cases

### For Researchers

- Evaluate new models on security-related coding tasks
- Compare agent architectures and strategies
- Publish reproducible benchmark results

### For Developers

- Test code agents before deployment
- Identify weaknesses in vulnerability detection
- Validate security patches

### For Organizations

- Assess AI readiness for security workflows
- Compare commercial vs open-source solutions
- Track improvements over time

## Next Steps

- [Getting Started](/guide/getting-started) - Set up SSEBench on your machine
- [Architecture](/guide/architecture) - Understand how SSEBench works
- [Adding Models](/guide/models) - Integrate new LLM models
- [MCP Server](/guide/mcp-server) - The `test_patch` tool agents use to check their work
