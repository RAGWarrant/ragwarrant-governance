# Focus 1 Seed-Schedule Separation Amendment

> Entropy-custody note: the local-secret commitment mechanism described below was retired by `FOCUS1-FULL-ENTROPY-DRAND-001`. The v2 profile-qualified identity schedule remains in force; FULL now requires the separately documented future-public-beacon protocol.

- Benchmark protocol version: `false_promotion_benchmark_v1` (unchanged)
- Seed schedule version: `2`
- Amendment ID: `FOCUS1-SEED-SCHEDULE-SEPARATION-001`

## Reason for amendment

Seed-schedule v1 used one public master seed and restarted trial indices at zero for CI, LOCAL, and FULL while omitting the profile from evidence-seed derivation. CI-v1 therefore exposed the first 24 nominal FULL-v1 evidence trials per scenario/sample-size cell. FULL-v1 is partially exposed developmental evidence and is permanently retired from confirmatory use.

CI-v1 outputs remain readable exploratory evidence. They must not be relabeled as confirmatory evidence, rewritten, or used to support confirmatory Focus 2 claims.

## V2 identity and derivation

Every evidence trial has the immutable identity:

`v{seed_schedule_version}|{profile}|{scenario_id}|{sample_size}|{trial_index}`

Profile names are `CI`, `LOCAL`, and `FULL`. Scenario IDs are the validated, portable configured IDs serialized exactly as stored. The `|` delimiter is forbidden by the scenario-ID validation rule. Python's built-in `hash()` is not used.

The complete identity enters a domain-separated SHA-256 derivation. The full 256-bit digest supplies the evidence-trial entropy. Phase, metric, shared/candidate, and candidate identifiers remain domain-separated substreams beneath that trial seed. Method-internal seeds also include the canonical trial identity. All methods within one trial continue to receive one identical immutable evidence object.

CI and LOCAL use the existing public deterministic development master seed. FULL uses an independently generated 256-bit secret supplied only through an ignored local seed file. Source control, configuration snapshots, schedule manifests, and reports store only `sha256(raw_32_byte_full_seed)`. FULL fails before evidence generation unless an explicit seed file is supplied and its reveal matches the committed digest.

## Static separation proof

Schedule enumeration operates only on configuration metadata. It does not import or invoke the simulator. The freeze review records:

- pairwise-disjoint identity sets for CI, LOCAL, and FULL;
- full SHA-256 identity-set hashes;
- a complete-schedule hash;
- commitment-bound public seed fingerprints for collision defense; and
- zero generated or inspected FULL evidence.

The public schedule fingerprints are not secret-derived FULL PRNG seeds. On an eventual authorized FULL reveal, commitment verification and an in-memory uniqueness check of the actual secret-derived trial-seed digests occur before any evidence generation.

## Scientific contract unchanged

This amendment changes only evidence scheduling and provenance. It does not change:

- scenario families or parameters;
- candidate families or population truths;
- thresholds, margins, or enabled risks;
- governance methods or method mathematics;
- estimands, event definitions, output metrics, or operational objectives; or
- the benchmark protocol version.

All new benchmark outputs must record `seed_schedule_version`, amendment ID, canonical trial identities, evidence role, and the applicable seed commitment metadata. CI and LOCAL are developmental. FULL can become confirmatory only after a verified reveal and explicit owner authorization. This amendment neither implements nor authorizes Focus 2.
