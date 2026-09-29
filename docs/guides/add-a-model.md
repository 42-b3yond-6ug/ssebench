---
outline: deep
---

# Add a model

SSEBench reaches models through a [LiteLLM proxy](/concepts/litellm-proxy), so
it can use any provider LiteLLM supports. This guide adds a model to the proxy.

## Overview

Models are defined in YAML files in `models/`. When the proxy image is built,
every `.yaml` or `.yml` file there is read and all the models they define are
offered under their `model_name`. That name is what you pass to
`ssebench run --model`.

The repository has one file per provider: `anthropic-claude.yaml`,
`google-gemini.yaml` and `openai-gpt.yaml`.

## Quick start

### 1. Define the model

Add an entry to the provider's file, or create a new file such as
`models/<provider>-<family>.yaml`:

```yaml
- model_name: gpt-5.1
  litellm_params:
    model: openai/gpt-5.1
    api_key: os.environ/OPENAI_API_KEY
```

### 2. Set the API key

Add the key to `.env` in the repository root:

```sh
OPENAI_API_KEY=sk-...
```

### 3. Rebuild the proxy

The model list is built into the proxy image, so rebuild and restart it:

```sh
just launch
```

The model is now available:

```sh
uv run ssebench run --local datasets/pilot --task <task-id> --agent claude-code --model gpt-5.1
```

## Configuration format

Each file holds a list of models:

```yaml
- model_name: <name used with --model>
  litellm_params:
    model: <provider>/<model id>
    api_key: os.environ/<ENV_VAR_NAME>
  model_info:
    input_cost_per_token: <USD>
    output_cost_per_token: <USD>
```

| Field | Description | Required |
|-------|-------------|----------|
| `model_name` | Unique name, used with `--model` | Yes |
| `litellm_params.model` | The provider and model, in LiteLLM's `<provider>/<model>` form | Yes |
| `litellm_params.api_key` | The key, as a reference to a variable in `.env` | For most providers |
| `litellm_params.api_base` | A custom API endpoint | No |
| `litellm_params.api_version` | API version, for providers that need one | No |
| `litellm_params.temperature`, `max_tokens`, ... | Default request parameters | No |
| `model_info.input_cost_per_token`, `output_cost_per_token`, `cache_read_input_token_cost` | Prices used to track the spend of each run | No |

The entries are LiteLLM model definitions; the
[LiteLLM documentation](https://docs.litellm.ai/docs/proxy/configs) describes
every field.

## Provider examples

### OpenAI

```yaml
- model_name: gpt-5.1
  litellm_params:
    model: openai/gpt-5.1
    api_key: os.environ/OPENAI_API_KEY
```

### Anthropic

```yaml
- model_name: claude-sonnet-4-6
  litellm_params:
    model: anthropic/claude-sonnet-4-6
    api_key: os.environ/ANTHROPIC_API_KEY
```

### Google

```yaml
- model_name: gemini-3-pro
  litellm_params:
    model: gemini/gemini-3-pro-preview
    api_key: os.environ/GOOGLE_API_KEY
```

### Azure OpenAI

```yaml
- model_name: azure-gpt-4o
  litellm_params:
    model: azure/<deployment-name>
    api_key: os.environ/AZURE_API_KEY
    api_base: os.environ/AZURE_API_BASE
    api_version: "2024-02-01"
```

### Ollama

```yaml
- model_name: llama3
  litellm_params:
    model: ollama/llama3
    api_base: http://<ollama-host>:11434
```

The proxy runs in a container, so `localhost` there means the proxy's own
container. Point `api_base` at an address the container can reach.

### Hugging Face

```yaml
- model_name: codellama
  litellm_params:
    model: huggingface/codellama/CodeLlama-34b-Instruct-hf
    api_key: os.environ/HF_TOKEN
```

## Default parameters

Parameters in `litellm_params` apply to every request made with that model:

```yaml
- model_name: gpt-5.1-low-temp
  litellm_params:
    model: openai/gpt-5.1
    api_key: os.environ/OPENAI_API_KEY
    temperature: 0.2
    max_tokens: 4096
```

## API keys

::: warning
Always refer to keys with `os.environ/<NAME>`. Never write a key into a model
file.
:::

Put the keys in `.env`; see [Environment variables](/reference/environment#provider-keys).

## Troubleshooting

### `Model <name> does not exist.`

`ssebench run` checks the model with the proxy before it builds anything. If
the proxy doesn't know the name:

- check that the file is in `models/` and ends in `.yaml` or `.yml`;
- check that the YAML is valid and the file is a list of models; a file that
  fails to parse is skipped;
- run `just launch` to rebuild the proxy with your changes.

### Authentication errors

- Check that the variable name in `api_key` matches the one in `.env`.
- Run `just launch` after changing `.env`.

## Next steps

- [Quickstart](/getting-started/quickstart): run a task with your model
- [Environment variables](/reference/environment): keys and container variables
- [LiteLLM providers](https://docs.litellm.ai/docs/providers): every provider
  LiteLLM supports
