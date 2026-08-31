# Confirmation provenance and diagnostic amendment v1

Status: amendment contract; no simulation rerun and no scientific-design change.

## Amendment identity

- Amendment ID: `STRATIFIED-JOINT-POWER-CONFIRMATION-PROVENANCE-001`
- Amendment type: `PROVENANCE_BINDING_AND_DERIVED_DIAGNOSTIC_CORRECTION`
- Original protocol ID: `STRATIFIED_JOINT_POWER_CONFIRMATION_V1`

This amendment is additive. The original protocol, configuration, runner, and
confirmation outputs remain immutable. It does not add a design point, change
a seed, or change any sample size, quota, scenario, dependence condition,
threshold, risk, estimand, method, or interpretation rule.

## Why the package was blocked

Final package review found two provenance and reporting defects:

1. The original confirmation materialization was not bound to one canonical,
   repository-relative output identity through an authoritative registry. A
   different output argument could therefore create another materialization
   under the same protocol ID through the historical runner.
2. Two secondary columns in `candidate_results.csv` were named as aggregate
   marginal-power diagnostics even though their values were calculated inside
   one-replicate calls and then averaged. With binary per-replicate component
   indicators, both calculations collapse to an empirical all-components-pass
   indicator rather than the named aggregate formulas.

Neither defect changes the direct Monte Carlo certification counts or their
Wilson intervals. Those direct outcomes remain the authoritative primary
results. In particular, the preserved high-dependence results are:

| Design | Point estimate | Wilson 95% interval |
|---|---:|---:|
| representative core 1,383 / group quota 826 | 0.770 | [0.7429, 0.7950] |
| representative core 1,720 / group quota 1,028 | 0.903 | [0.8831, 0.9198] |

The original confirmation output set has deterministic aggregate SHA-256
`a6ff12e61dc800be65c089cdb7cbe8aca68339a53af08d6ac1bbc95db8a57493`.
The amendment inventory is the authoritative file-by-file record of that
materialization. No original output is renamed, rewritten, or relabeled.

## Deprecated historical diagnostics

The following original columns are preserved byte-for-byte and designated
`DEPRECATED_MISLABELED_SECONDARY_DIAGNOSTIC`:

| Original column | Original calculation | Actual meaning |
|---|---|---|
| `mean_independence_approximation` | Mean across 1,000 outer replicates of the product returned by a one-replicate inner study | Frequency with which every mandatory component passed the fixed diagnostic threshold in the same replicate; not the product of aggregate marginal pass-rate estimates |
| `mean_union_bound_lower_bound` | Mean across 1,000 outer replicates of the union formula returned by a one-replicate inner study | The same all-mandatory-components-pass frequency because every one-replicate component rate is zero or one; not the union-bound formula applied to aggregate marginal pass-rate estimates |

Both names occur in the preserved
`.local_data/research_review/joint_power_confirmation_v1/candidate_results.csv`.
Any verbatim reproduction of the original table remains historical output and
must retain the deprecation label. No primary result or planning label depends
on interpreting either historical column according to its name.

## Corrected derived diagnostics

New amendment artifacts derive diagnostics only from each preserved row's
complete aggregate `marginal_component_powers` mapping. For the exact enabled
component set and aggregate marginal pass-rate estimates `q_i`, they report:

```text
independence_joint_pass_point_estimate_from_marginals = product(q_i)

union_bound_joint_pass_lower_point_estimate_from_marginals =
    max(0, 1 - sum(1 - q_i))
```

The product uses stable multiplication and is an independence approximation,
not observed joint power. The union expression is a lower-bound plug-in
diagnostic based on estimated marginals, not guaranteed planning power.
Components share observations, so neither derived value replaces the direct
simulated joint-certification proportion. Neither receives a Wilson interval
as if it were a direct binomial proportion.

Every mandatory component must be present. A missing mandatory component
produces an explicit unavailable derivation and must not shrink the component
family. An extra, nonfinite, or out-of-range component makes the row malformed
and fails closed. Corrected artifacts record the source column, source file
hash, source output-set hash, component identifiers, implementation hash,
derivation status, and claim boundary.

## Canonical materialization contract

Scientific identity uses repository-relative POSIX paths and content hashes,
not host-specific absolute paths. Host absolute paths are non-authoritative
execution metadata only.

- `canonical_repository_root_identity` binds the repository identity, frozen
  Focus 1 digest, and frozen v1 commit.
- `canonical_protocol_path` is
  `.local_data/research_review/JOINT_POWER_CONFIRMATION_PROTOCOL.json`.
- `canonical_config_path` is
  `configs/research/stratified_joint_power_confirmation_v1.yaml`.
- `canonical_runner_path` is
  `scripts/run_joint_power_confirmation.py`.
- `canonical_output_root` is
  `.local_data/research_review/joint_power_confirmation_v1`.
- `canonical_materialization_id` is derived deterministically from the
  canonical repository identity, protocol ID, protocol hash, configuration
  hash, and output-set hash.
- `materialization_scope` is
  `AUTHORITATIVE_WITHIN_DECLARED_REPOSITORY_WORKSPACE`.

Tracked inputs bind repository-relative POSIX path, SHA-256, and the applicable
frozen commit or Focus 1 digest. Ignored outputs bind the canonical output root,
protocol ID, materialization ID, protocol/configuration hashes, exact file set,
and deterministic output-set hash. Existing path components must resolve
inside the declared repository root. Drive-qualified, UNC/device, absolute,
empty, dot, dot-dot, alternate-data-stream, trailing-dot/space, symlink, and
reparse-point aliases fail closed. Host-specific case behavior is made
explicit, while stored scientific paths preserve their exact canonical case.

The scope is deliberately local. It does not claim to discover or prevent
arbitrary external copies, materializations in unrelated directories, or
changes made outside repository controls.

## Authoritative registry and future guard

The amendment registers the preserved output set as the sole authoritative
materialization of `STRATIFIED_JOINT_POWER_CONFIRMATION_V1` within the declared
workspace scope. Registration uses exclusive creation after complete hash and
path verification. An incomplete or stale registration fails closed.

The approved amendment-aware entry point refuses before evidence generation
when:

- the original protocol ID is requested again;
- a different output root is supplied;
- a relative, separator, case, traversal, symlink, junction, reparse-point, or
  other path alias is used;
- source hashes differ;
- the existing output set is missing, changed, or has unexpected files; or
- another authoritative registry is present in the declared registry scope.

Existing files are never overwritten. A future execution requires a new
protocol version and new protocol ID. Any supported resume may address only
the same canonical materialization and exact source hashes.

This guard governs the approved entry point and declared repository workspace.
The preserved historical runner cannot be modified without changing its
frozen hash, so direct invocation of that legacy runner is outside the guarded
contract. The amendment therefore does not claim operating-system-enforced or
global uniqueness. Review and automation must use the amendment-aware entry
point for future protocol invocations.

## Read-only verification statuses

The verification utility resolves the repository root, verifies every declared
input and output hash, checks the exact output-set aggregate hash and canonical
paths, validates the registry, and reproduces corrected diagnostics from the
preserved aggregate marginals. It never rewrites an original output. Its
machine-readable terminal status is one of:

- `CONFIRMATION_PROVENANCE_VERIFIED`
- `CONFIRMATION_PROVENANCE_HASH_MISMATCH`
- `CONFIRMATION_PROVENANCE_PATH_MISMATCH`
- `CONFIRMATION_DUPLICATE_MATERIALIZATION`
- `CONFIRMATION_DERIVED_DIAGNOSTIC_MISMATCH`
- `CONFIRMATION_PROVENANCE_INCOMPLETE`

Extra files under the exact canonical output root are not silently admitted to
the output set. Missing or extra files make the declared materialization
incomplete unless a later, separately versioned contract defines a different
policy.

## Claim and execution boundaries

This amendment corrects provenance binding and secondary diagnostic semantics
only. It does not change primary simulated counts, Wilson intervals, planning
labels, or scientific interpretations. It does not establish real-world power,
production readiness, a novel statistical theorem, or global prevention of
duplicate files.

No evidence is collected. The simulator is not rerun. FULL is not executed or
inspected. No drand round or public beacon is selected. Production selectors,
deployment paths, workflows, historical `artifacts/` and `results/`, and the
frozen Focus 1 benchmark remain untouched.

## Package restart gate

Owner-handoff and local commit packaging may resume only after independent
provenance, statistical, adversarial, QA/security, and claims reviews confirm
all of the following:

1. Every original primary output byte and hash is preserved.
2. The deterministic original output-set hash verifies.
3. One authoritative materialization is registered within the declared scope.
4. The approved entry point blocks a second invocation under the original
   protocol ID before simulation.
5. Both mislabeled historical columns are explicitly deprecated.
6. Corrected diagnostics reproduce from the exact aggregate marginal inputs.
7. The direct Monte Carlo joint results remain authoritative and unchanged.
8. Focus 1, v1, historical artifacts/results, production behavior, and all
   scientific-design inputs remain unchanged.
9. P0 and P1 amendment findings are closed.

Questions about post-evaluation usability costs and screening-cap scope may
remain explicit P2 owner decisions. They must not be answered by inventing
operational inputs.
