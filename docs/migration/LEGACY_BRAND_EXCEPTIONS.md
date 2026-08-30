# Legacy Brand Exceptions

RAGWarrant active surfaces must not contain former-name tokens. The validator permits those tokens only when an exact rule in `legacy_brand_exceptions.json` matches all of these fields:

- exact file path
- exact location type
- blocked-token regular expression
- maximum occurrence count
- narrow classification

Allowed classifications:

- `migration_documentation`: Rename notes, identifier crosswalks, and completion reports that must name old identifiers for review.
- `pre_rename_archive_manifest`: The archive note that points to immutable tag `v0.1.0-rc1`.
- `immutable_historical_object`: A retained exact historical object, only if it is explicitly listed with an exact path.
- `validator_negative_fixture`: Validator source or deliberately negative fixtures that enumerate blocked strings so the gate can reject them.

Disallowed exception shapes:

- `path_prefix`, `path_prefixes`, `path_glob`, `path_globs`, `glob`, or `globs`
- wildcard paths
- README exceptions
- package metadata exceptions
- blanket `artifacts/`, `results/`, `deployment_review/`, lockfile, current-paper, or generated-report exceptions

The blocked former-name set is: `RAGTune`, `ragtune`, `RAGTUNE`, `AIM-RAGTune`, `rag-tuning-governance`, `rag-tuning-governance-public`, `rag_tuning_governance`, and `aim-ragtune`.

Known misspellings are not approved as brand terms. The validator enumerates them only as negative fixtures.
