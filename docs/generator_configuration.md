# Generator Configuration

Generative validation can use a local or hosted generator. Raw prompts and raw generated answers must remain local-only under `.local_data/`.

## Local Ollama

```bash
export RAGWARRANT_GENERATOR_PROVIDER=ollama
export RAGWARRANT_OLLAMA_BASE_URL=http://localhost:11434
export RAGWARRANT_GENERATOR_MODEL=qwen3:8b
```

For `qwen3*` and `gpt-oss*` models, the Ollama adapter sends `think: false` by default so final answers are emitted into the response field instead of spending the generation budget in hidden reasoning output. For `gpt-oss*`, the adapter also uses Ollama's chat endpoint by default because it gives a cleaner final-answer channel than the plain generate endpoint in the CRAG diagnostic path. Override only for local debugging:

```bash
export RAGWARRANT_OLLAMA_THINK=true
export RAGWARRANT_OLLAMA_ENDPOINT=generate
```

The bounded CRAG answer-emission repair used `llama3.2:3b` as a faster non-thinking instruct model. It repaired blank-answer emission, but did not produce a stable governance cost result.

Run:

```bash
python3 scripts/run_hotpotqa_generative_llm_validation.py \
  --config configs/experiments/ragwarrant_hotpotqa_generative_llm_validation_v1.yaml \
  --output-root artifacts/generative_llm_validation/hotpotqa \
  --force
```

## Local OpenAI-Compatible Runtime

```bash
export RAGWARRANT_GENERATOR_PROVIDER=local_openai_compatible
export RAGWARRANT_LOCAL_OPENAI_BASE_URL=http://localhost:11434/v1
export RAGWARRANT_LOCAL_OPENAI_API_KEY=local-not-secret
export RAGWARRANT_GENERATOR_MODEL=<local-model-name>
```

## Hosted Models

Hosted validation is optional and requires normal provider credentials in the local environment. Do not commit credentials.

```bash
export RAGWARRANT_GENERATOR_PROVIDER=openai
export RAGWARRANT_GENERATOR_MODEL=gpt-4o-mini
```

For Azure OpenAI:

```bash
export RAGWARRANT_GENERATOR_PROVIDER=azure_openai
export AZURE_OPENAI_DEPLOYMENT=<deployment-name>
export AZURE_OPENAI_API_VERSION=2024-10-21
```

Provider secrets are intentionally omitted from this document.
