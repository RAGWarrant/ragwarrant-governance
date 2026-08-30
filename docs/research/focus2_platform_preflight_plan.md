# Focus 2 Non-FULL Platform Preflight Plan

Status: design only; not executed.

This plan qualifies the GitHub control plane needed for a later, separately approved public-beacon seal. It must not select a real FULL drand round, fetch beacon entropy, generate benchmark evidence, or execute any CI, LOCAL, or FULL benchmark profile.

## Preconditions and disposable scope

An owner creates a clearly named disposable branch and authorizes a dedicated preflight workflow on that branch only. The workflow and every object it creates must carry a `NON_FULL_PREFLIGHT_DISPOSABLE` marker. It may publish only synthetic fixed strings and their hashes. It may not import or invoke the simulator, benchmark runner, sealed FULL runner, drand client, or production governance code.

The branch-protection and environment rules used for the intended seal path must be identified before the preflight. Cleanup is a separate owner-authorized action after receipts are retained.

## Permission checks

The preflight declares the minimum permissions needed by each isolated job:

- `id-token: write` permits requesting a GitHub OIDC token. It does not grant repository-content or pull-request write access.
- `contents: write` is separately required to create or update a disposable ref or publish repository content.
- `pull-requests: write` is separately required to open or update a draft pull request.
- `actions: read` may be used for bounded run-status inspection when needed.

Each job should declare only its own permissions. A successful OIDC request must not be treated as proof of contents or pull-request write permission, and the converse is also false.

## Preflight sequence

1. On the disposable ref, create a synthetic seal payload containing no drand round, seed, evidence, or scientific result.
2. Request a GitHub OIDC token with a predeclared nonproduction audience. Record only nonsecret claim metadata needed to verify repository, ref, workflow, actor, run ID, run attempt, and audience. Never persist the token.
3. Verify the token signature and claims using the already pinned verifier path. Treat mismatch, missing claims, or an untrusted ref as failure.
4. Publish the synthetic public-seal object to the disposable ref using `contents: write`. Verify its retrieved bytes and commit object ID.
5. Open a draft pull request from the disposable ref using `pull-requests: write`. The title and body must state that it is a non-FULL permission preflight and contains no benchmark evidence.
6. Publish an immutable synthetic execution receipt bound to the workflow run ID, attempt, subject commit, and synthetic seal hash. Retrieve it independently and verify exact bytes and object identity.
7. Close no pull request and delete no ref automatically unless the owner separately authorizes cleanup. Report the exact disposable objects for review.

## Retry, queue, and cancellation rules

- A retry must reuse the same synthetic seal object and synthetic round placeholder. It may not select a fallback or new round.
- A re-run must distinguish `run_id` from `run_attempt` and append a new immutable attempt receipt rather than overwriting the prior receipt.
- A queued run publishes no success receipt. Its status remains `QUEUED_PREFLIGHT_NOT_QUALIFIED`.
- A cancelled run publishes or records a terminal cancellation audit object only if that write occurs in a separate bounded finalizer; it must never publish a success receipt.
- Concurrent runs use a preflight-only concurrency group. Cancellation of an older queued or running attempt cannot authorize the newer attempt automatically.
- Partial publication, permission denial, OIDC failure, receipt mismatch, or draft-PR failure leaves the platform preflight unqualified and requires owner review.

## Success criteria

Success proves only that the disposable GitHub path can request and verify OIDC identity, write a public synthetic seal, open a draft pull request, and publish an immutable synthetic receipt with controlled retry semantics. It does not qualify drand timing, FULL evidence execution, scientific results, production integration, or cleanup permissions.

No preflight may select a real FULL round. No preflight may run benchmark evidence. No preflight described here has been executed.
