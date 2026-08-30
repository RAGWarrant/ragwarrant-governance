# Artifact Integrity

`ragwarrant verify-run --run-dir <path>` generates a manifest and SHA-256 digest for a run directory, then checks required artifacts, promotion-decision shape, hashes, and publication hygiene.

The verifier fails closed for missing artifacts, hash mismatch, schema failure, raw text, secret-like strings, or private-path exposure.
