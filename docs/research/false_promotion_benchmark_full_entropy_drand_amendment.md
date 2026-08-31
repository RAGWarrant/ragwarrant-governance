# Focus 1 Future-Public-Beacon Entropy Amendment

- Benchmark protocol version: `false_promotion_benchmark_v1` (unchanged)
- Seed schedule version: `2` (unchanged)
- Amendment ID: `FOCUS1-FULL-ENTROPY-DRAND-001`
- Entropy protocol: `DRAND_QUICKNET_FUTURE_ROUND_V1`
- Current FULL status: `PENDING_FUTURE_PUBLIC_BEACON_SEAL`

## Custody decision

The locally generated FULL seed and its SHA-256 commitment are retired because the ignored seed file was accessible to the same operating-system identity used by Codex. The raw file was deleted without its contents being read, printed, hashed, recovered, or copied. Its retired status is:

`FULL_SECRET_SEED_COMMITMENT_RETIRED_AGENT_ACCESSIBLE_CUSTODY`

CI-v1, CI-v2, and LOCAL-v2 remain developmental evidence. FULL-v1 is partially exposed and permanently ineligible for confirmation. This amendment removes human seed custody; it does not upgrade any existing output.

## Frozen Quicknet parameters

The protocol pins League of Entropy Quicknet, rather than discovering parameters at runtime:

- beacon ID: `quicknet`
- chain hash: `52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971`
- public key: `83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a`
- genesis Unix time: `1692803367`
- period: `3` seconds
- scheme: `bls-unchained-g1-rfc9380`

The workflow-only verifier is the official `drand-client` package at exact version `1.4.2`, installed from its integrity-locked npm lockfile. Beacon verification is enabled. Every accepted relay must return the exact sealed round, exact pinned chain metadata, a valid BLS signature, and randomness equal to SHA-256 of the signature bytes. Relay agreement is an availability check, not a substitute for signature verification. The canonical Python FULL runner does not accept a caller-supplied receipt: it invokes the pinned JavaScript verifier itself and consumes the receipt created in that same process path. Before constructing FULL entropy, Python invokes the pinned client again against the receipt offline, so self-asserted JSON flags cannot replace BLS verification. A recorded historical Quicknet round exercises the actual client offline and a tampered signature must be rejected.

## Immutable trial identity and entropy derivation

The canonical evidence-trial identity remains:

`v2|<PROFILE>|<SCENARIO_ID>|<SAMPLE_SIZE>|<TRIAL_INDEX>`

CI and LOCAL retain their public deterministic development seeds. FULL uses only the verified future beacon. Its master seed is the 32-byte SHA-256 digest of the exact byte concatenation:

```text
ASCII("RAGWARRANT_FULL_MASTER_SEED_V1\0")
|| bytes.fromhex(pinned_quicknet_chain_hash)
|| uint64_big_endian(sealed_round)
|| bytes.fromhex(verified_beacon_randomness)
|| bytes.fromhex(benchmark_freeze_digest)
|| bytes.fromhex(focus2_freeze_commit_sha)
```

Each FULL evidence-trial seed is:

```text
SHA256(
  ASCII("RAGWARRANT_TRIAL_SEED_V2\0")
  || full_master_seed
  || UTF8(canonical_trial_identity)
)
```

Under Quicknet's threshold-security assumptions, benchmark operators cannot derive the 32-byte FULL master seed before the sealed future round. After verification it exists only in process memory. It is never printed, written to benchmark output, placed in configuration, or passed as a command-line argument. All public derivation inputs are retained.

## Public seal and automatic execution

The seal stage is eligible only after a tracked confirmation-freeze manifest exists at the exact Focus 2 frozen commit. Its read-only preparation job checks out that commit without persisted credentials, recomputes the manifest hashes, uses the GitHub Actions run start time, and selects the first Quicknet round scheduled at least 30 minutes later. A separate write-only publication job does not check out or execute repository code. It publishes the prepared seal to the deterministic `ragwarrant-full-seal-<subject-sha>` branch and creates a `ragwarrant-full-subject-<subject-sha>` ref pinned to the exact frozen commit. A server-timestamped draft PR must be public before the sealed round. The seal artifact records the exact seal-tree commit SHA, workflow run ID, PR head OID, and frozen-subject ref. Partial recovery may only finish publication of identical already-pushed seal bytes before the target round; it cannot choose a new round.

After the public seal artifact is uploaded, Stage A dispatches Stage B from the frozen-subject ref without an approval gate. Stage B refuses to run unless both `github.sha` and `github.workflow_sha` equal the sealed subject commit. Its read-only execution job downloads the seal artifact from the exact seal workflow run, verifies the current seal branch and draft-PR head still equal the recorded seal commit, retrieves only the exact sealed round from two pinned relays, verifies both responses independently, revalidates the benchmark digest, and then runs FULL. A short-lived GitHub Actions OIDC token binds execution to the canonical repository, frozen subject ref, subject SHA, workflow, event, and seal digest; the token is verified against GitHub's public signing keys and is neither printed nor persisted. The benchmark library refuses FULL outside that attested workflow even if a caller imports internal Python symbols. The write-only publication job is part of the same frozen workflow, checks out no repository code, and publishes either the hash-verified completed output or an `ABORTED_OR_INCOMPLETE` closure regardless of scientific direction. If a hard cancellation prevents that job from starting, the reconciler dispatches a publication-only closure workflow from the same frozen-subject ref to record the cancelled run before deterministic same-seal retries continue. The reconciler can dispatch only that frozen-subject ref, exact seal commit, exact seal workflow run, and original round. If the transient seal artifact has expired, Stage B reconstructs the same publication metadata from the immutable seal commit, public draft PR, successful seal run, and frozen ref; it cannot select a different round.

All third-party actions in the seal and execution workflows are pinned to full Git commit SHAs. Completion requires exact benchmark-output hashes, a complete confirmatory benchmark manifest, and preserved method truth-isolation. Negative, mixed, or inconclusive scientific results use the same successful publication route; failure or cancellation uses the same results branch with an incomplete closure.

The published seal is never rewritten. Execution creates a separate manifest. No path may request `latest`, choose a fallback round, change the frozen commit or digest, or substitute development entropy.

GitHub branch and draft-PR history provide public auditability; without owner-approved branch protection, this protocol does not claim that a repository administrator is physically unable to delete public history. The automation itself has no deletion or force-push path.

## Scientific contract unchanged

This amendment changes only the unavailable-before-seal FULL entropy source and associated provenance. It does not change scenario families, candidate truths, thresholds, margins, enabled risks, governance methods, method mathematics, estimands, event definitions, output metrics, or the benchmark protocol version. It does not implement Focus 2, authorize production integration, establish novelty, or establish safety.
