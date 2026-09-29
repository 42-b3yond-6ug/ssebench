# Add an agent

::: info
This page is being written.
:::

This guide will walk through adding an agent: its `agent.yaml`, the contract its Dockerfile follows to build on the tool layer, how it receives the task and reaches the model through the [LiteLLM proxy](/concepts/litellm-proxy), how it checks its work with the [`test_patch` tool](/reference/mcp-server), and how it reports its session to the web UI with the [dialog protocol](/reference/dialog-protocol). The agents in `agents/` are working examples; `agents/reference`, which applies the task's known fix, is the smallest one that uses the SDK.
