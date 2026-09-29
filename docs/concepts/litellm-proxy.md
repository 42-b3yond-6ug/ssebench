# LiteLLM proxy

::: info
This page is being written.
:::

This page will explain how SSEBench decouples agents from models: every LLM request goes through a LiteLLM proxy, each run gets its own key limited to the selected model, and the spend of each run is recorded with its result. It will also cover how the proxy's model list is built from `models/*.yaml`. To add a model, see [Add a model](/guides/add-a-model).
