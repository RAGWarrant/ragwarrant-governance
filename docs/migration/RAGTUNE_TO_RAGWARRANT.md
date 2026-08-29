# RAGTune to RAGWarrant Migration

The active project name is now **RAGWarrant**. The canonical repository is:

https://github.com/RAGWarrant/ragwarrant-governance

RAGWarrant was previously released as RAGTune at `v0.1.0-rc1`; the historical tag and artifacts remain available for reproducibility.

## Repository Migration

- Source repository: `https://github.com/AIM-RAGTune/rag-tuning-governance`
- Legacy public URL: `https://github.com/AIM-RAGTune/rag-tuning-governance-public`
- Destination repository: `https://github.com/RAGWarrant/ragwarrant-governance`
- Migration strategy: native GitHub repository transfer followed by repository rename
- Default branch: `main`
- Visibility: public
- Immutable historical tag: `v0.1.0-rc1` -> `ff529005bf7d00a0c3f79ba991563f3923d63205`

## Active Naming Contract

- Product: `RAGWarrant`
- Python package: `ragwarrant`
- CLI: `ragwarrant`
- Environment prefix: `RAGWARRANT_`
- Repository slug: `ragwarrant-governance`
- Future GHCR image: `ghcr.io/RAGWarrant/ragwarrant-governance`

## Breaking Changes

The active Python import package, console command, environment-variable prefix, suite IDs, deployment names, and container image names changed. No undocumented `ragtune` package or CLI alias is retained.

## Historical Artifact Policy

Historical run IDs, hash-bound artifacts, v0.1.0-rc1 release evidence, old digest records, prior review reports, and preprint copies can retain the former name where editing would falsify provenance or invalidate recorded integrity. See `LEGACY_NAME_EXCEPTIONS.md` and `legacy_name_exceptions.json`.
