---
outline: deep
---

# Adding Models

SSEBench supports 100+ LLM providers through LiteLLM. This guide shows how to integrate new models.

## Overview

Models are configured using YAML files in the `models/` directory. SSEBench automatically recognizes any model defined there.

## Quick Start

### 1. Create a Config File

Add a configuration file named `<provider>-<model>.yaml` in the `models/` directory:

```yaml
# models/openai-gpt.yaml
- model_name: gpt-4o
  litellm_params:
    model: openai/gpt-4o
    api_key: os.environ/OPENAI_API_KEY
```

### 2. Set Your API Key

Add the API key to your `.env` file:

```bash
OPENAI_API_KEY=sk-xxx-your-api-key-here
```

### 3. Restart the LiteLLM Proxy

```bash
just launch
```

The model is now available for use.

## Configuration Format

### Basic Structure

```yaml
- model_name: <unique-identifier>
  litellm_params:
    model: <provider>/<model-name>
    api_key: os.environ/<ENV_VAR_NAME>
```

### Configuration Fields

| Field | Description | Required |
|-------|-------------|----------|
| `model_name` | Unique identifier used in CLI | Yes |
| `litellm_params.model` | Provider/model path for LiteLLM | Yes |
| `litellm_params.api_key` | API key reference | Yes |
| `litellm_params.api_base` | Custom API endpoint | No |
| `litellm_params.temperature` | Default temperature | No |
| `litellm_params.max_tokens` | Maximum tokens | No |

## Provider Examples

### OpenAI

```yaml
# models/openai-gpt.yaml
- model_name: gpt-4o
  litellm_params:
    model: openai/gpt-4o
    api_key: os.environ/OPENAI_API_KEY

- model_name: gpt-4-turbo
  litellm_params:
    model: openai/gpt-4-turbo
    api_key: os.environ/OPENAI_API_KEY
```

### Anthropic

```yaml
# models/anthropic-claude.yaml
- model_name: claude-opus-4-5
  litellm_params:
    model: anthropic/claude-sonnet-4-20250514
    api_key: os.environ/ANTHROPIC_API_KEY

- model_name: claude-sonnet-4
  litellm_params:
    model: anthropic/claude-sonnet-4-20250514
    api_key: os.environ/ANTHROPIC_API_KEY
```

### Google

```yaml
# models/google-gemini.yaml
- model_name: gemini-2.0-flash
  litellm_params:
    model: gemini/gemini-2.0-flash
    api_key: os.environ/GOOGLE_API_KEY

- model_name: gemini-1.5-pro
  litellm_params:
    model: gemini/gemini-1.5-pro
    api_key: os.environ/GOOGLE_API_KEY
```

### Azure OpenAI

```yaml
# models/azure-openai.yaml
- model_name: azure-gpt-4
  litellm_params:
    model: azure/gpt-4-deployment
    api_key: os.environ/AZURE_API_KEY
    api_base: https://your-resource.openai.azure.com/
    api_version: "2024-02-01"
```

### Local Models (Ollama)

```yaml
# models/ollama-local.yaml
- model_name: llama3
  litellm_params:
    model: ollama/llama3
    api_base: http://localhost:11434
```

### Hugging Face

```yaml
# models/huggingface.yaml
- model_name: codellama
  litellm_params:
    model: huggingface/codellama/CodeLlama-34b-Instruct-hf
    api_key: os.environ/HF_TOKEN
```

## Multiple Models Per File

You can define multiple models in a single file:

```yaml
# models/anthropic-claude.yaml
- model_name: claude-opus-4-5
  litellm_params:
    model: anthropic/claude-sonnet-4-20250514
    api_key: os.environ/ANTHROPIC_API_KEY

- model_name: claude-sonnet-4
  litellm_params:
    model: anthropic/claude-sonnet-4-20250514
    api_key: os.environ/ANTHROPIC_API_KEY

- model_name: claude-haiku-3.5
  litellm_params:
    model: anthropic/claude-3-5-haiku-20241022
    api_key: os.environ/ANTHROPIC_API_KEY
```

## Advanced Configuration

### Custom Parameters

```yaml
- model_name: gpt-4-custom
  litellm_params:
    model: openai/gpt-4
    api_key: os.environ/OPENAI_API_KEY
    temperature: 0.2
    max_tokens: 4096
    top_p: 0.9
```

### Fallback Models

LiteLLM supports fallback configurations:

```yaml
- model_name: gpt-4-with-fallback
  litellm_params:
    model: openai/gpt-4
    api_key: os.environ/OPENAI_API_KEY
    fallbacks:
      - model: anthropic/claude-3-opus
        api_key: os.environ/ANTHROPIC_API_KEY
```

## Environment Variables

::: warning Security Note
Always use `os.environ/<KEY_NAME>` to reference API keys. Never hard-code secrets in config files.
:::

Add keys to your `.env` file:

```bash
# .env
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
GOOGLE_API_KEY=xxx
AZURE_API_KEY=xxx
HF_TOKEN=hf_xxx
```

## Verifying Configuration

After adding a model, verify it's recognized:

```bash
# Restart LiteLLM proxy
just launch

# Check available models
curl http://localhost:4000/models
```

## Troubleshooting

### Model Not Found

```
Error: Model 'my-model' not found
```

- Verify the YAML file is in `models/` directory
- Check YAML syntax is valid
- Run `just launch` to restart the LiteLLM proxy

### Authentication Failed

```
Error: Invalid API key
```

- Check the environment variable name matches exactly
- Verify the key is set in `.env`
- Restart the LiteLLM proxy after changing keys

### Rate Limiting

```
Error: Rate limit exceeded
```

- LiteLLM handles retries automatically
- Consider adding multiple API keys for rotation
- Check provider-specific rate limits

## Next Steps

- [Getting Started](/guide/getting-started) - Run a task with your model
- [Environment Variables](/guide/environment) - API keys and container variables
- [LiteLLM Docs](https://docs.litellm.ai/) - Full provider list
