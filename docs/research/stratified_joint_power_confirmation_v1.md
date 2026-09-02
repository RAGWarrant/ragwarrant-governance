# Stratified joint-power confirmation v1

`STRATIFIED_JOINT_POWER_CONFIRMATION_V1` is an independent, deterministic,
planning-only confirmation of two designs already selected before this run.
It is not the original FULL benchmark, a future sealed stratified study, or
real-world evidence.

## Frozen comparison

The protocol contains exactly two designs:

1. `COMPONENT_PLANNING_COMPARATOR`: representative core 1,383 and quota 826
   for each required group.
2. `SELECTED_JOINT_PLANNING_CANDIDATE`: representative core 1,720 and quota
   1,028 for each required group.

Each design is evaluated under the already established low, medium, and high
shared-variation conditions with 1,000 planning replicates per cell. Candidate
family, component tests, IUT/Holm warrant, thresholds, margins, protected
groups, planning alternatives, and normalized cost assumptions are inherited
unchanged from `STRATIFIED_CONFIRMATORY_EVIDENCE_V1`.

The two design points, three dependence conditions, and replicate count are
immutable after the local protocol hashes are recorded. No interpolation,
optimization, or additional design may be introduced after observing results.

## Deterministic planning identity

Every planning replicate has the identity:

```text
STRATIFIED_JOINT_POWER_CONFIRMATION_V1|{design_id}|{dependence_condition}|{replicate_index}
```

The additive executor serializes the protocol version, design ID, dependence
condition, and zero-based replicate index canonically. Stage one hashes that
identity with the public development master seed using SHA-256 and converts 64
digest bits to an adapter seed. Stage two passes that seed to exactly one call
of the preserved simulator with `replicates=1`; the preserved deterministic
seed fold then includes the core size, sorted quotas, dependence condition,
and its fixed internal replicate index zero. Thus the evidence RNG seed is a
deterministic function of the complete canonical identity while leaving the
preserved simulator unchanged. Python's built-in `hash()` is prohibited. The
protocol prefix separates this planning namespace from prior CI and LOCAL
planning, the unexecuted original FULL schedule, and every future sealed
stratified confirmation.

## Prespecified interpretation

For each design and dependence condition, the study reports per-safe-candidate
joint certification, at-least-one-safe-candidate certification, false
certification, certified-set size, operational selection, 95% Wilson Monte
Carlo intervals, and the frozen screening/evaluation cost plan.

- `PLANNING_SUPPORTS_80_PERCENT` requires the 95% Wilson lower bound for the
  prespecified family-level probability to be at least 0.80.
- `PLANNING_SUPPORTS_90_PERCENT` requires that lower bound to be at least 0.90.
- `PLANNING_POINT_ESTIMATE_ONLY` means the point estimate reaches the target
  but its Wilson lower bound does not.
- `PLANNING_TARGET_NOT_SUPPORTED` means the point estimate is below the target.

These labels describe conditional simulation planning. They are not power
guarantees, confirmatory evidence, or real-world validation. A negative result
does not authorize another design search.

## Boundary

No evidence is collected. The original FULL profile remains
`FULL_ORIGINAL_BUDGET_NOT_EXECUTED_DEVELOPMENTALLY_UNDERPOWERED`. No drand
round is selected, no public beacon is queried, and no production behavior is
changed. Real execution remains blocked until an owner or deployer supplies
and freezes the operational population, frame, group codebook, recruitment,
privacy, retention, inclusion-probability, cost, cap, and failure fields.
