# Container Supply Chain

RAGWarrant uses a finite-job container image for public-mini governance execution.
The image reports job success through process exit status and the schema-valid
`promotion_decision.json` artifact. It intentionally has no Docker
`HEALTHCHECK`; health checks are more appropriate for long-running services and
can produce false failures after a finite job exits normally.

## Base Image Pin

- Source tag: `python:3.11-slim`
- Pinned manifest-list digest: `sha256:a630a63cdb314e2d138a2fca3e375e319e8568346ffafac5b980f888630ac4f1`
- Resolution date: 2026-08-16
- Resolution command: `docker buildx imagetools inspect python:3.11-slim`
- Supported build platforms: `linux/amd64`, `linux/arm64`

The Dockerfile pins both builder and runtime stages to the same manifest-list
digest so multi-architecture builds resolve from one reviewable base reference.

## Dependency Locks

Runtime dependencies are installed from `requirements-runtime.lock`, generated
with:

```bash
python3 -m piptools compile --generate-hashes --resolver=backtracking --output-file requirements-runtime.lock pyproject.toml
```

Development and publication-test dependencies are installed from
`requirements-dev.lock`, generated with:

```bash
python3 -m piptools compile --extra dev --generate-hashes --resolver=backtracking --output-file requirements-dev.lock pyproject.toml
```

The runtime image installs the RAGWarrant wheel with `--no-deps` after the hashed
runtime lock is installed. Test dependencies are not installed in the runtime
image.

## Runtime Contents

The runtime image includes the installed RAGWarrant package, `configs/`, `schemas/`,
and license/citation metadata. It does not copy `tests/`, `paper/`, `docs/`,
`results/`, `artifacts/`, `deployment_review/`, `.git/`, local data caches, or
Docker caches into `/app`.

## GHCR Publication

The publication workflow publishes same-repository candidate images to:

```text
ghcr.io/ragwarrant/ragwarrant-governance
```

GitHub packages may require a one-time visibility change to make anonymous cloud
pulls work. If the package is not public, operators can configure a registry
pull secret or mirror the digest into their native cloud registry. No personal
access token is required by repository automation.

## Digest Record

`deploy/IMAGE_DIGEST` is the repository record for the publishable container
reference. Before the first successful GHCR workflow, it intentionally contains
`PENDING_FIRST_WORKFLOW_RUN`. Deployment templates and runbooks must treat that
sentinel as not deployable.

The GitHub workflow in `.github/workflows/publish-container.yml` builds
`linux/amd64` and `linux/arm64`, requests BuildKit provenance and SBOM
generation, signs the published digest with keyless cosign, and uploads a digest
record artifact. It does not use a `latest` tag.

The release workflow record is the authoritative digest source. Do not infer a
real digest from a stale checkout or from a tag name. Tag-event digests may
differ from an earlier PR-candidate digest, so operators must verify the release
digest against the corresponding workflow run.

Human release sequence:

1. Trigger the publish workflow with `workflow_dispatch` or create the
   authorized release tag.
2. Review and merge the generated digest-record pull request.
3. Set the GHCR package visibility to public, if it is not already public.

If repository settings prevent GitHub Actions from opening the digest-record
pull request, use the workflow artifact containing `deploy/IMAGE_DIGEST` as the
review input and create the digest-record PR manually. Do not commit a digest
that did not come from a successful publish workflow run.
