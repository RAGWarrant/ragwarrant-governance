# Artifact Storage

RAGWarrant supports a small artifact-sink abstraction so the governance engine can write local artifacts and optionally hand them to cloud storage.

Supported modes:

```text
local
azure_blob
s3
gcs
disabled
```

Environment variables:

```text
RAGWARRANT_STORAGE_MODE=local|azure_blob|s3|gcs|disabled
RAGWARRANT_OUTPUT_ROOT=/outputs
RAGWARRANT_AZURE_BLOB_CONTAINER=<container>
RAGWARRANT_AZURE_BLOB_PREFIX=<prefix>
RAGWARRANT_S3_BUCKET=<bucket>
RAGWARRANT_S3_PREFIX=<prefix>
RAGWARRANT_GCS_BUCKET=<bucket>
RAGWARRANT_GCS_PREFIX=<prefix>
```

`local` mode works without cloud SDKs or credentials. Cloud modes fail closed if optional SDKs or required configuration are unavailable. RAGWarrant writes a local copy of `promotion_decision.json` before any optional upload attempt.

## Emulator Validation

Object-storage staging is protocol-tested against local emulators through:

```bash
scripts/run_storage_emulator_tests.sh
```

The runner starts MinIO, Azurite, and fake-gcs-server containers pinned by digest, runs the public-mini governance job through the storage staging wrapper, verifies `promotion_decision.json` in each emulated object store, and confirms wrapped process failure exit codes are preserved. These tests require Docker and optional storage SDK dependencies. They do not execute real AWS, Azure, or GCP deployments and do not claim platform-native cloud validation.

Storage sinks must not log secrets. Public artifacts should contain only metrics, hashes, IDs, sanitized summaries, and claim-boundary metadata.
