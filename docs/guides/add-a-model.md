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
`google-gemini.yaml` and `openai-gpt.yaml`. `ssebench init` copies them into
the `models/` of your workspace when you run `ssebench` without a clone; edit
that copy.

## Quick start

### 1. Define the model

Add an entry to the provider's file, or create a new file such as
`models/<provider>-<family>.yaml`. The models that are defined already are
listed in [Configuration files](/reference/configuration#models-yaml); for
those, only the key in step 2 is missing. A model of your own:

```yaml
- model_name: gpt-5-mini
  litellm_params:
    model: openai/gpt-5-mini
    api_key: os.environ/OPENAI_API_KEY
  model_info:
    input_cost_per_token: 2.5e-07
    output_cost_per_token: 2.0e-06
```

`model_name` is what you will pass to `--model`. Give it prices in `model_info`
as well; see [Costs and the budget](#costs-and-the-budget).

### 2. Set the API key

Add the key to `.env` in the repository root (or in your workspace):

```sh
OPENAI_API_KEY=sk-...
```

### 3. Rebuild the proxy

The model list is built into the proxy image. `just launch`, which is
`ssebench proxy up`, sees that `models/` changed, rebuilds the image and
recreates the proxy container:

```sh
just launch
```

```text
INFO:ssebench.stack:models/ changed since the LiteLLM image ghcr.io/42-b3yond-6ug/ssebench/litellm:1.0.0-dev was built; rebuilding it
INFO:ssebench.stack:Starting the LiteLLM proxy (project ssebench, http://localhost:4000)
INFO:ssebench.stack:The LiteLLM proxy now serves the current models/
```

`ssebench run` does the same when it starts, so this step is optional. Only
`ssebench proxy up` (or `just launch`) switches a running proxy over: `ssebench
proxy build` builds the image when it is missing or out of date but leaves the
container as it is, and `--rebuild` forces a rebuild of an image that is
current. See [LiteLLM proxy](/concepts/litellm-proxy#the-model-list).

Check that the proxy offers the model, with the master key from `.env`; this is
the request `ssebench run` makes before it starts:

```sh
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "http://localhost:${LITELLM_PORT:-4000}/models" | jq -r '.data[].id'
```

The model is now available:

```sh
uv run ssebench run --local datasets/pilot --task <task-id> --agent claude-code --model gpt-5-mini
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
| `model_info.input_cost_per_token`, `output_cost_per_token`, `cache_read_input_token_cost` | Prices, in US dollars per token, that the proxy charges each run's key | For a model LiteLLM has no prices for; see [below](#costs-and-the-budget) |

The entries are LiteLLM model definitions; the
[LiteLLM documentation](https://docs.litellm.ai/docs/proxy/configs) describes
every field.

## Costs and the budget

Each run gets its own LiteLLM key, which can use only the selected model and
has a budget of 10 US dollars; the CLI records the key's spend as `spend` in the
run's [summary](/concepts/results#the-summary). The proxy computes the spend
from the tokens of each request:

- If you set the costs in `model_info`, the proxy charges those. Keep them in
  line with the provider's prices.
- If you set none and LiteLLM has prices for the model in its own price list,
  as it does for the models of the big providers, it charges those.
- If you set none and LiteLLM does not know the model, as with a self-hosted
  model or a name it has not heard of, every request costs zero. The run's
  `spend` stays 0.0, and the budget can never stop it.

So give a model that LiteLLM does not price its `input_cost_per_token` and
`output_cost_per_token` (and `cache_read_input_token_cost` if the provider
discounts cached input), even when the model is free to you, to get a meaningful
`spend`. In a test with the prices `1.0e-05` and `3.0e-05` dollars per input and
output token, a request of 100 input and 20 output tokens cost 0.0016 dollars;
the same request to an unpriced model cost nothing.

## Provider examples

The first three are the entries that `models/` already has.

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
- model_name: gemini-3.1-pro
  litellm_params:
    model: gemini/gemini-3.1-pro-preview
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
container. Point `api_base` at an address the container can reach: a service
on the proxy's Compose network, by its container name, or a host name that
resolves from inside the container.

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
The proxy container receives the whole file, so a provider that needs another
variable, such as `AZURE_API_KEY`, works the same way: name it in the model
file as `os.environ/AZURE_API_KEY` and set it in `.env`. The proxy reads the
file when its container starts, so after a change to `.env` run `just launch`,
which recreates the container.

## Troubleshooting

### `Model <name> does not exist.`

`ssebench run` checks the model with the proxy before it builds anything, and
stops with a Python traceback that ends in `ValueError: Model <name> does not
exist.` if the proxy doesn't know the name:

- check that the file is in `models/` and ends in `.yaml` or `.yml`;
- check that the YAML is valid and the file is a list of models; a file that
  fails to parse, or is not a list, is skipped without a message;
- check that `--model` is the `model_name`, not the LiteLLM model;
- run `just launch` to rebuild the proxy with your changes.

### Authentication errors

- Check that the variable name in `api_key` matches the one in `.env`.
  `just doctor` lists the variables that `models/` refers to and `.env` lacks.
- Run `just launch` after changing `.env`.

### The run's `spend` is 0.0

The model has no prices. See [Costs and the budget](#costs-and-the-budget).

## Next steps

- [Quickstart](/getting-started/quickstart): run a task with your model
- [Environment variables](/reference/environment): keys and container variables
- [LiteLLM proxy](/concepts/litellm-proxy): how runs get their key and how spend is recorded
- [LiteLLM providers](https://docs.litellm.ai/docs/providers): every provider
  LiteLLM supports
