# Dataset Acquisition

This repository does not redistribute raw CRAG or HotpotQA data.

## CRAG

CRAG fresh live mock-API runs require approved noncommercial research-only access. Configure:

```bash
export RAGWARRANT_CRAG_APPROVED_NONCOMMERCIAL_RESEARCH_ONLY=true
export RAGWARRANT_CRAG_ROOT=<approved-local-path>/CRAG
export RAGWARRANT_CRAG_DATA=<approved-local-path>/crag-data
```

Then run:

```bash
python3 scripts/acquire_crag_live_mock_api_inputs.py --dry-run
python3 scripts/run_fresh_live_crag_behavioral_governance.py
```

Raw CRAG query text, source documents, and API responses must remain outside this repository.

## HotpotQA

HotpotQA should be acquired into `.local_data/hotpotqa` or another approved local data root:

```bash
pip install datasets
python3 scripts/acquire_hotpotqa_public_corpus.py --source huggingface --config distractor --output-root "${RAGWARRANT_DATA_ROOT:-.local_data}/hotpotqa"
python3 scripts/run_hotpotqa_behavioral_governance.py
```

Raw HotpotQA questions, context paragraphs, and supporting-fact sentences must not be committed.

## Generative Validation

Generative validation uses the same local dataset caches but keeps prompts and generated answers out of Git:

```bash
export RAGWARRANT_GENERATOR_PROVIDER=ollama
export RAGWARRANT_OLLAMA_BASE_URL=http://localhost:11434
export RAGWARRANT_GENERATOR_MODEL=qwen3:8b

python3 scripts/run_hotpotqa_generative_llm_validation.py --force
python3 scripts/run_generative_llm_validation_synthesis.py --force
```

Raw prompts and generated answers are local-only under `.local_data/`. Public artifacts include hashes, counts, model identifiers, policy identifiers, and metrics.
## Mini Reproduction Data

The public mini reproduction uses synthetic in-code examples and therefore requires no dataset acquisition.

The external evaluator adapter demo also uses synthetic sanitized evaluator rows. Full CRAG and HotpotQA experiments still require approved local data acquisition outside the public repository.
