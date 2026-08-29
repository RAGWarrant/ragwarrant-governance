# Container Security Scans

RAGWarrant records optional container scanner availability for local hardening.

Optional tools:

- `hadolint`
- `trivy`
- `grype`
- `syft`
- `docker scout`

If tools are unavailable, the scan step records a skipped result. Publication validation does not require optional scanner installation. If an operator enables scanners, committed summaries must remain sanitized and must not include secrets, private paths, huge SBOMs, or raw dataset material.
