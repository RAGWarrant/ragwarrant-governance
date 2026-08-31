# Known-Truth False-Promotion Benchmark Protocol V1

Status: frozen before evaluation of any proposed fixed-sample multi-risk warrant.

## Purpose

This research-only benchmark asks:

> When the population quality and risk characteristics of candidate RAG policies are known by construction, how frequently does each governance method promote or certify a candidate that is actually unsafe or materially inferior?

The contribution is the evaluator-agnostic benchmark and protocol. Negative, mixed, weak, and inconclusive results are valid. The protocol does not assume a preferred method and does not modify RAGWarrant's production or public governance decision path.

## Estimands

The primary estimand, calculated separately for each scenario, sample size, and method, is:

`P(at least one unsafe candidate is promoted in a trial)`

Secondary estimands are:

- `P(at least one unsafe candidate is certified in a trial)`;
- `P(at least one safe candidate exists and no candidate is promoted)`;
- `P(a safe candidate is promoted)`;
- `P(no safe candidate exists and no candidate is promoted)`;
- `P(no decision is returned)`;
- mean certified-set size; and
- mean operational regret conditional on safe selection.

Scenarios are not pooled into a headline number.

## Population truth

Confirmatory parameters are the scoring truth. Development parameters are separately recorded for shift scenarios. Truth is not estimated by running a larger simulation.

For each candidate, the truth table includes:

- overall quality delta versus the incumbent;
- quality delta by group;
- safety-violation probability;
- execution-failure probability;
- insufficient-evidence probability;
- mean cost; and
- mean latency.

The simulator also supports group-specific binary risk, cost, and latency parameters. Overall quantities are exact prevalence-weighted functions of group parameters.

With configurable thresholds, a candidate is truly promotion-safe only if every enabled condition passes:

```text
overall quality delta >= -overall quality noninferiority margin
and every enabled group quality delta >= -group quality noninferiority margin
and safety-violation probability <= configured maximum
and execution-failure probability <= configured maximum
and insufficient-evidence probability <= configured maximum
and every explicitly enabled group binary risk <= its configured maximum
```

Cost and latency are V1 operational objectives, not safety guarantees. A candidate may be acceptable in the overall mixture and still be subgroup-unsafe; that state is explicitly recorded.

## Trial and unit of analysis

A trial is one confirmatory sample for one frozen scenario and sample size. The quality unit is the paired candidate-versus-incumbent delta for one example. Binary risk, cost, and latency are recorded on the same candidate/example row.

Before confirmatory sampling, the benchmark freezes:

- candidate IDs and family membership;
- group definitions and prevalences;
- enabled risks and thresholds;
- development and confirmatory population parameters;
- sample size and replicate count;
- operational objective; and
- seed plan.

Every deployable method receives the same immutable confirmatory evidence object within a trial. Before evaluation, configured scenario and candidate IDs are replaced with deterministic opaque method-facing IDs. Decisions are validated in that opaque namespace and mapped back to canonical IDs only in the central scorer. Evidence-generation seeds do not include a method ID. Method-internal seeds do include the method ID. Population truth and the reverse identifier mapping are stored separately and are not arguments to deployable method interfaces.

## Simulator construction

### Paired quality

For candidate `j`, group `g`, and row `i`:

```text
delta(i,j,g) = declared_mean_delta(j,g)
             + shared_half_width * U_shared(i)
             + candidate_half_width * U_candidate(i,j)
```

Each `U` is uniform on `[-1, 1]`, so each noise term is bounded and has exactly zero mean. Configuration validation proves that the full support stays inside the configured delta bounds and that incumbent quality plus the delta stays in `[0, 1]`. The simulator never clips these outcomes.

### Binary risks and dependence

For each risk and row, a Bernoulli branch chooses shared evidence with probability `shared_outcome_fraction`. On the shared branch, all candidates compare the same uniform draw with their own declared probability. Otherwise each candidate uses an independent uniform draw.

This preserves each candidate's declared marginal probability exactly. `shared_outcome_fraction` is a mixture parameter, not a claim about exact Pearson correlation.

### Groups, shift, cost, and latency

Group labels are sampled from declared prevalences. Candidate parameters may vary by group. Development and confirmatory evidence use disjoint deterministic seed streams while candidate identities remain frozen.

Cost and latency use bounded symmetric shared and candidate-specific noise around positive declared means. Validation proves the full support remains positive. No lognormal approximation or clipping is used.

### Deterministic seed plan

The original seed-schedule v1 derivation below is retired from confirmatory use because profile namespaces overlapped:

```text
master seed, expanded scenario ID, phase, trial, metric, candidate when applicable
```

Seed schedule v2 supersedes only this scheduling rule under amendment `FOCUS1-SEED-SCHEDULE-SEPARATION-001`. Its canonical profile-qualified identity is `v2|profile|scenario_id|sample_size|trial_index`; the full identity enters the SHA-256 evidence derivation. See [Focus 1 Seed-Schedule Separation Amendment](false_promotion_benchmark_seed_schedule_v2_amendment.md). The benchmark protocol version and scientific scenario, truth, method, threshold, risk, and estimand contracts are unchanged.

Evidence is therefore independent of method order and candidate configuration order. The canonical evidence digest is checked before and after every method evaluation.

## Frozen V1 scenario matrix

| Family | V1 instances | Candidate design | Purpose |
|---|---:|---|---|
| `ALL_UNSAFE_BOUNDARY` | 1 | Four candidates just outside different gates | Near-boundary false promotion |
| `ONE_CLEARLY_SAFE` | 1 | Exactly one clearly safe candidate | Power and false blocking |
| `MANY_CANDIDATES_MULTIPLICITY` | 2 | 12 and 24 candidates, mostly unsafe | Candidate multiplicity |
| `DEPENDENT_CANDIDATES` | 1 | Six candidates with substantial shared variation | Dependence sensitivity |
| `HIDDEN_GROUP_REGRESSION` | 1 | Average-acceptable but group-unsafe candidate | Subgroup harm |
| `DEVELOPMENT_CONFIRMATORY_SHIFT` | 1 | Frozen candidate changes from development-safe to confirmatory-unsafe | Shift behavior |
| `MULTIPLE_SAFE_CANDIDATES` | 1 | Three safe candidates with different operations | Conditional regret |

Every instance uses sample sizes 64 and 256 in the checked-in configuration. Scenario IDs are deterministic.

Profiles are:

- `CI`: 24 replicates per cell and 128 bootstrap resamples;
- `LOCAL`: 250 replicates per cell and 500 bootstrap resamples; and
- `FULL`: 5,000 replicates per cell and 2,000 bootstrap resamples.

FULL is not run in ordinary CI. No claim depends on a FULL run until it is independently reviewed.

## Methods

### Controls

`always_block` never promotes or certifies. Its false-promotion rate is zero by construction, but it can have high false-block rates.

`oracle_safe_objective` uses confirmatory population truth and chooses the best truly safe candidate under the frozen operational objective. It is marked `uses_population_truth=true`, `deployable=false`, and `benchmark_control_only=true`. It is excluded from deployable method IDs.

### Deployable baselines

`naive_point_estimate` applies all configured gates to observed means and event rates. Its certified set contains every observed-eligible candidate, and it selects the candidate with the best observed frozen objective.

`corrected_paired_bootstrap_gate` uses genuine sampling with replacement to calculate one-sided lower bounds for overall and group paired quality. It uses one-sided Wilson upper bounds for enabled binary risks. It fails closed on empty, malformed, missing-group, or nonfinite evidence. This is a benchmark comparator; V1 makes no family-wise error-control claim for it.

### Unsupported adapter

`current_ragwarrant_adapter` is recorded as `unsupported_in_benchmark_v1`. Existing production selectors consume aggregate evidence and cannot represent the complete row-level multi-risk/subgroup contract without an invasive production change. It receives no trial denominator. The production selector is not copied or modified.

The historical deterministic modular pseudo-bootstrap is not used.

## Decision and scoring contract

A method returns its ID, selected policy or null, certified set, decision status, reason, deployability, truth-access flag, and diagnostics. Allowed statuses are `PROMOTE`, `BLOCK`, `NO_DECISION`, and `UNSUPPORTED`.

The selected candidate must be certified. Unknown or duplicate policy IDs are contract errors. A deployable truth-access flag is a fatal error. Anticipated evidence insufficiency produces a structured block; malformed benchmark data aborts the run.

Central scoring uses only the method decision and separate confirmatory truth:

- false promotion: selected candidate exists and is unsafe;
- false certification: any certified candidate is unsafe;
- false block: a safe candidate exists but selection is null;
- correct promotion: selected candidate is safe;
- correct no-safe-candidate block: no safe candidate exists and selection is null; and
- no decision: method status is `NO_DECISION`.

Operational regret equals the selected safe candidate's declared objective minus the best truly safe candidate's declared objective. It is undefined for unsafe or null selections.

The objective is:

```text
cost_weight * mean_cost + latency_weight * mean_latency
```

Policy ID is the deterministic final tie-breaker.

## Monte Carlo uncertainty

For an event count `x` among `n` independent repeated trials in one scenario cell, V1 reports the two-sided 95% Wilson binomial interval. This interval describes Monte Carlo estimation uncertainty for the benchmark event rate. It is not the one-sided candidate-risk evidence bound used inside a governance method.

## Outputs and provenance

Default output is `.local_data/false_promotion_benchmark/`:

- `benchmark_manifest.json`;
- `config_snapshot.yaml`;
- `scenario_truth.csv`;
- `scenario_summary.csv`;
- `method_summary.csv`;
- `trial_summary_sample.csv`;
- `false_promotion_report.md`; and
- `claim_boundaries.md`.

The manifest records config and protocol hashes, commit, dirty flag, semantic seed plan, method capabilities, scenario IDs, risks, profile, replicate count, runtime version, truth access, completeness, and `post_hoc_filtered=false`. A bounded trial sample supports diagnostics; all scenario-specific aggregate results are retained.

Outputs contain no external raw data, credentials, hostnames, usernames, private absolute paths, or hidden reasoning. Default execution never writes tracked `artifacts/` or `results/`.

## Validity safeguards

Configuration fails closed on duplicate scenario or candidate IDs, missing incumbent, invalid probabilities, nonpositive sample sizes or trials, invalid margins/fractions, unknown methods/risks, missing groups, invalid prevalence sums, nonfinite values, and support settings that would require clipping.

Tests assert invariants rather than favorable scientific outcomes, including determinism, different-seed evidence, exact truth bookkeeping, empirical marginal concentration, shared evidence, truth isolation, controls, genuine bootstrap replacement, multiplicity scoring, subgroup classification, malformed input, output isolation, and no historical artifact changes.

## Development and confirmatory separation

This protocol is frozen before any Focus 2 warrant is evaluated. Scenario or estimand changes made after observing method results require a new protocol version. Methods receive confirmatory evidence only. Development truth and an independently generated development-evidence digest record selection history and shift; development rows are not combined with confirmation or written to the bounded trial sample.

## Claim and novelty boundary

The narrow provisional thesis is:

> RAGWarrant can provide an evaluator-agnostic benchmark for measuring false-promotion behavior across multiple RAG policy risks under known ground truth.

No novel theorem, Learn-Then-Test method, conformal-risk method, sequential procedure, universal superiority, production readiness, human validation, clinical validation, official evaluator-platform result, or RAG Compass superiority is claimed.

Primary-source review found established work on [Learn-Then-Test](https://doi.org/10.1214/24-AOAS1998), [adaptive Learn-Then-Test](https://proceedings.mlr.press/v267/zecchin25a.html), [risk-controlling prediction sets](https://doi.org/10.1145/3478535), [conformal risk control](https://openreview.net/forum?id=33XGfHLtZg), [risk-aware RAG calibration](https://proceedings.mlr.press/v235/kang24a.html), [offline policy selection](https://proceedings.mlr.press/v151/yang22a.html), and multiple-testing-based model selection. No materially identical known-truth repeated-trial RAG false-promotion benchmark was found in the targeted review, but novelty remains provisional and incremental.

## Limitations

- Synthetic known truth does not establish real-world, evaluator, human, or clinical safety.
- The dependence model is intentionally simple and does not cover arbitrary covariance.
- Group sample counts are random under the configured prevalence mixture.
- V1 does not implement a multiplicity-controlled warrant, adaptive testing, sequential testing, LTT, conformal calibration, evaluator integrations, or production selection.
- Scenario results cannot justify universal rankings.
- Current production behavior is not benchmarked where its evidence contract is unsupported.
