# RAGWarrant Brand Migration

This repository was formerly published as RAGTune and is now RAGWarrant.

Current active code, README content, package metadata, documentation outside `docs/migration/`, manuscript sources, figures, generated artifacts, deployment templates, and command examples use:

- Product name: `RAGWarrant`
- Python import package: `ragwarrant`
- CLI command: `ragwarrant`
- Environment prefix: `RAGWARRANT_`
- Repository slug: `ragwarrant-governance`
- Canonical repository URL: `https://github.com/RAGWarrant/ragwarrant-governance`
- Container image path: `ghcr.io/ragwarrant/ragwarrant-governance`

Legacy identifiers remain only in exact migration/provenance files that explain the rename, map old evidence identifiers, or identify immutable historical evidence. The brand validator classifies those references through `docs/migration/legacy_brand_exceptions.json` and fails any unclassified former-name reference.

The migration intentionally does not rename `RAG Compass`; that is a distinct evaluation harness name.
