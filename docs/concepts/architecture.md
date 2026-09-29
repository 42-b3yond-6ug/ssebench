---
outline: deep
---

# Architecture

SSEBench uses a layered Docker architecture to provide isolated, reproducible benchmark environments.

## System Overview

```
┌────────────────────────────────────────────────────────────┐
│                     SSEBench Infrastructure                │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   LiteLLM    │    │   Task       │    │   Report     │  │
│  │   Proxy      │◄───│   Runner     │───►│   Generator  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                   │                              │
│         ▼                   ▼                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Docker Container (Task)                 │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │              Agent Layer                       │  │  │
│  │  │  (Claude Code / Codex / Custom Agent)          │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │              Tool Layer                        │  │  │
│  │  │  (MCP Server, SDK, Rust Daemon)                │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │              Case Layer                        │  │  │
│  │  │  (Vulnerable Project + Dependencies)           │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │              Base Layer                        │  │  │
│  │  │  (gcc, jvm, cargo, Python, etc.)               │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Docker Image Layers

### Base Image

The foundation layer providing the toolchain for the task's language:

- Compilers: `gcc`, `clang`, `rustc`, `go`
- Build tools: `make`, `cmake`, `cargo`
- Utilities: `git`, `curl`, `wget`

Base images are defined in `images/base-images/` (`generic-c`, `generic-go`, `generic-rust`) and shared across all tasks. They are named `ghcr.io/42-b3yond-6ug/ssebench/base-<type>`, for example `ghcr.io/42-b3yond-6ug/ssebench/base-generic-go`.

### Case Image

Contains the vulnerable project and its specific dependencies:

- Project source code at a specific vulnerable commit
- Build dependencies (libraries, headers)
- Test suites (functional tests, PoC exploits)
- Build scripts and configuration

Case images are built from the `Dockerfile` in each task folder of a dataset, such as `datasets/pilot/<task-id>/`.

### Tool Image

Provides the SSEBench SDK and MCP server:

- **Python SDK (`sse`)**: APIs for build, test, and metadata access
- **MCP Server**: Model Context Protocol server exposing the [`test_patch`](/reference/mcp-server) tool
- **Rust Daemon**: Handles build/test operations via Unix socket

### Agent Image

The final layer installing the code agent:

- Agent binaries and dependencies
- Agent-specific configuration
- Entry point scripts

## LiteLLM Proxy

SSEBench uses LiteLLM as a proxy to decouple agents from specific LLM providers:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent     │────►│   LiteLLM   │────►│   LLM API   │
│             │     │   Proxy     │     │  (OpenAI,   │
│             │◄────│             │◄────│  Anthropic) │
└─────────────┘     └─────────────┘     └─────────────┘
```

Benefits:
- **Transparent switching**: Change models without modifying agent code
- **Unified API**: All agents use the same OpenAI-compatible interface
- **Rate limiting**: Built-in request throttling and retries
- **Cost tracking**: Monitor API usage across runs

## Running Modes

### Sandbox Mode

Agent and task run in the **same container**:

```
┌────────────────────────────────────┐
│         Docker Container           │
│  ┌──────────┐    ┌──────────────┐  │
│  │  Agent   │◄──►│   Project    │  │
│  │          │    │   (Source)   │  │
│  └──────────┘    └──────────────┘  │
│       Direct filesystem access     │
└────────────────────────────────────┘
```

- Agent has native OS-level access to the project
- Direct file read/write operations
- Faster execution
- **Use when**: Agent dependencies are compatible with task environment

### Sidecar Mode

Agent and task run in **separate containers**:

```
┌───────────────────┐     ┌──────────────────┐
│  Agent Container  │     │  Task Container  │
│  ┌───────────┐    │     │  ┌───────────┐   │
│  │   Agent   │    │◄───►│  │  Daemon   │   │
│  └───────────┘    │     │  └───────────┘   │
│                   │     │                  │
└───────────────────┘     └──────────────────┘
```

- The source tree is shared between the two containers through a Docker volume
- The agent edits files directly, but builds and tests run in the task container, through the daemon
- The MCP server and evaluator run in the agent container
- **Use when**: Agent requires different dependencies than task

Sidecar mode is experimental; sandbox mode is the default.

## Project Structure

See [Project Structure](/contributing/project-structure) for the repository layout.

## Data Flow

1. **Task Selection**: User selects task, model, agent, and mode
2. **Image Building**: Pipeline builds layered Docker image
3. **Container Launch**: Task container starts with agent
4. **Agent Execution**: Agent receives task description and works on fix
5. **Tool Interaction**: Agent calls `test_patch` to build and test its patch
6. **Result Collection**: Patches and logs archived
7. **Evaluation**: Evaluator grades the patch
8. **Report Generation**: Results compiled into reports

## Benchmark Integrity

SSEBench implements several measures to ensure fair evaluation and prevent agents from "cheating" by accessing information they shouldn't have.

### User Isolation

Agents run as a non-root user (`model`, uid 1000) with restricted access:

```
┌─────────────────────────────────────────────────────────┐
│                   Container                             │
│                                                         │
│  Root-owned (inaccessible to agent):                    │
│  ├── /ssebench/config.yaml      # Contains patch path   │
│  ├── /ssebench/diffs/patch.diff # Ground truth patch    │
│  └── /ssebench/diffs/test.diff  # Post-patch tests      │
│                                                         │
│  Model-owned (agent can access):                        │
│  ├── /src/<project>/            # Source code           │
│  ├── /home/model/               # Agent home directory  │
│  └── /tmp/sse-archive/          # Results directory     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

This prevents agents from:
- Reading the ground truth patch directly
- Accessing post-patch test files that reveal the fix
- Modifying benchmark configuration

### Git History Reset

The original git history is **removed** during image build and replaced with a fresh repository:

```bash
# What happens at build time:
1. Delete all .git directories (including submodules)
2. Initialize fresh git repo
3. Commit all files as "buggy commit"
```

This prevents agents from:
- Using `git log` to find the patch commit
- Using `git blame` to see when/how code was changed
- Using `git diff` against historical commits to reverse-engineer the fix
- Accessing submodule history

The agent sees only:
```
$ git log --oneline
abc1234 buggy commit
```

### Protected Files

The SDK daemon only exposes safe metadata to agents. Protected information includes:

| Protected | Reason |
|-----------|--------|
| Ground truth patch | Direct answer to the task |
| Post-patch tests | Reveals expected behavior after fix |
| Patch commit hash | Could be used to look up the fix online |
| Original git history | Contains the fix commit |

### Difficulty Levels

The `SSE_DIFFICULTY` environment variable controls which checks the agent's [`test_patch`](/reference/mcp-server) tool runs. Final grading always runs every check the task has.

| Level | Build | Regression | PoC | Intent |
|-------|-------|------------|-----|--------|
| 0 (Full) | ✓ | ✓ | ✓ | ✓ |
| 1 | ✓ | ✓ | ✓ | ✗ |
| 2 (Default) | ✓ | ✓ | ✗ | ✗ |
| 3 | ✓ | ✗ | ✗ | ✗ |
| 4 | ✗ | ✗ | ✗ | ✗ |

At difficulty level 2 (default), PoC validation and intent tests are hidden to prevent agents from using test assertions to infer the fix.

## Next Steps

- [Adding Models](/guides/add-a-model) - Configure LLM providers
- [MCP Server](/reference/mcp-server) - The `test_patch` tool
- [Dialog Protocol](/reference/dialog-protocol) - Integrate your agent with the Web UI
