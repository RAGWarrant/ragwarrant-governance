# Legacy Brand Exceptions

The brand consistency gate allows former-name references only when they are needed to preserve historical evidence or explain migration.

Allowed categories:

- `migration_documentation`: Explicit migration notes, identifier maps, validator source, and validation reports.
- `legacy_redirect_reference`: Short statements that identify the former repository path so users can follow GitHub redirects to the canonical RAGWarrant repository.
- `historical_run_identifier`: Immutable run IDs, suite IDs, config names, or paths produced before the rename.
- `immutable_historical_artifact`: Archived run outputs, manifests, prior deployment-review packets, and checksums whose content records pre-rename execution history.
- `validator_fixture`: Tests that intentionally assert the former source namespace is absent.

Known misspellings are never approved as brand terms. The validator enumerates them internally so they can be rejected outside the validator itself.
