# CRAG Query Text Sanitization

This publication bundle removes CRAG raw question text from review artifacts. The repository does not include raw CRAG datasets, raw CRAG question wording, raw source documents, or raw API responses.

## Why Text Was Removed

CRAG is used under the original provider terms and a local noncommercial-research-only approval. The repository is intended for scientific review of RAGWarrant governance evidence, not redistribution of licensed dataset rows or reconstructive excerpts.

## Replacement Fields

Raw `query_text` fields in CRAG sample and case-explanation artifacts were removed and replaced with:

- `query_text_redacted`: records that raw wording was intentionally removed.
- `query_text_hash`: SHA-256 hash of normalized raw query text.
- `sanitized_query_summary`: generic non-reconstructive labels such as `dynamic finance simple question`.

The bundle preserves query IDs, run IDs, domains, question types, static/dynamic labels, policy winners, utility metrics, cost metrics, latency metrics, API-call metrics, confidence intervals, and aggregate evidence summaries.

## Hashing Method

Hashes are computed as:

```text
sha256(normalized_text)
```

Normalization trims leading and trailing whitespace and collapses internal whitespace to a single space. Case is preserved. Hashes are unsalted so reviewers with approved CRAG access can reproduce matching checks locally.

## What Remains Excluded

The repository excludes:

- raw CRAG question wording;
- raw source-document passages;
- raw mock-API responses;
- raw licensed dataset rows;
- private annotation answer keys;
- credentials, tokens, or local environment files.

## Reproduction

Reviewers who have obtained CRAG from the original approved source can reproduce the validation in an approved environment, verify the expected hashes, and compare local query hashes against the redacted artifacts. This sanitization does not change numeric validation results because metrics, IDs, policy decisions, aggregate summaries, and statistical outputs are preserved.

## History Caveat

This sanitization was performed on the current repository tree. Prior private Git history may still contain earlier artifact versions. A fresh clean repository or explicit history rewrite is recommended before any public release.
