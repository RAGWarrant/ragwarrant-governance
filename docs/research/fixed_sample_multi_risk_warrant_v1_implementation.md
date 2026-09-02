# Fixed-Sample Multi-Risk Warrant V1

Status: `IMPLEMENTED_RESEARCH_CANDIDATE_PENDING_OWNER_AND_STATISTICAL_REVIEW`.

This document records an implemented research candidate pending repository-owner acceptance and visible statistical review. It supplements, but does not edit, the historical Focus 2 design hashed into Focus 1. The warrant consumes permitted confirmatory observations without population truth, is `research_only=true`, is `production_integrated=false`, and does not modify `promotion_decision.json` or any current selector.

Status mapping:

- Design record: `SUPERSEDED_BY_IMPLEMENTATION_CANDIDATE`
- Implementation: `IMPLEMENTED_PENDING_HUMAN_REVIEW`
- Merge approval: `NOT_GRANTED`

## Frozen dependency

The method is evaluated only against Focus 1 freeze digest `c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e` and seed schedule version 2. The additive runner must verify every frozen input hash before it creates a candidate family or samples evidence. A mismatch stops the run.

The candidate IDs, incumbent research ID, enabled risks, groups, margins, thresholds, sample size, quality support, family-wise error level, multiplicity procedure, and selection objective are fixed before confirmatory evidence is generated. Development evidence is never used for certification.

## Hypotheses and p-values

For a Bernoulli event risk with prohibited boundary `tau`, event count `k`, and fixed sample count `n`:

```text
H0: p >= tau
H1: p < tau
p_raw = P(Binomial(n, tau) <= k)
```

The lower-tail boundary probability is an exact valid p-value because the probability of `X <= k` is greatest over the null at `p = tau`. It is calculated with the Python standard library. Wilson bounds are not used as hypothesis tests.

For paired quality deltas `D_i` in the prespecified support `[a,b]`:

```text
H0: E[D] <= -margin
H1: E[D] > -margin
p_raw = exp(-2 n max(0, mean(D) + margin)^2 / (b-a)^2)
```

This is the one-sided Hoeffding p-value frozen by the design and covered by automated reference-case tests and agent-assisted review passes. Visible human statistical approval remains pending. V1 uses support `[-0.25,0.25]`, the declared bound shared by every frozen scenario. Bounds are method metadata, never estimated from observed evidence or obtained from population truth. Out-of-support values are invalid; clipping is forbidden. Overall quality uses all paired rows. Protected-group quality uses the prespecified rows for each group.

Equality belongs to each null. This is conservative relative to the truth classifier, which treats equality at a promotion boundary as safe.

## Whole-family multiplicity

The family contains, for every frozen candidate:

- one overall-quality hypothesis when enabled;
- one protected-group-quality hypothesis for every configured group when enabled;
- one overall hypothesis for every enabled binary risk; and
- one hypothesis per configured group for each enabled group-specific binary risk.

No candidate, risk, group, failure, or unavailable test is filtered before `M` is known. A structural family/evidence mismatch invalidates the warrant. An unavailable prespecified group test remains a non-rejection and cannot reduce `M`.

Bonferroni uses adjusted p-value `min(1, M p)` and rejection at `p <= alpha/M`. Holm sorts the complete family by `(raw_p_value, hypothesis_id)`, compares ordered p-values to `alpha/(M-i+1)`, stops after the first failure, and records monotone adjusted p-values. Both procedures are valid under arbitrary dependence when the underlying p-values are valid.

## Certification and selection

A candidate is certified only if every one of its enabled hypotheses is rejected. The complete certified set is fixed before operational values are considered.

The research default is `minimize_cost`. `minimize_latency` is also supported. Ties are resolved by the other operational metric and then lexical policy ID. Cost and latency are observed confirmatory objectives, not certified risks.

If the certified set is empty, the warrant decision is `INCONCLUSIVE` and no policy is selected. Malformed or family-mismatched evidence yields `BLOCKED_INVALID_EVIDENCE`. The frozen benchmark adapter maps either no-selection decision to `NO_DECISION` while retaining the exact warrant decision in diagnostics.

## Artifact and claims boundary

`promotion_warrant.json` is governed only by `schemas/research/promotion_warrant_v1.schema.json`. It records the full family, raw and adjusted p-values, thresholds, rejection decisions, certified set, operational selection, evidence/family hashes, truth-isolation flags, and the Focus 1 digest. It never overwrites or extends a production artifact.

Public research artifacts use `observed_evidence_only`, `truth_isolated`, `benchmark_control_only`, `research_only`, and `production_integrated`; they never use `deployable=true` as a production-readiness signal. The frozen v1 Python object retains its original internal `deployable` compatibility flag, and public output writers translate it at the serialization boundary without changing the statistical implementation. `naive_point_estimate` and `corrected_paired_bootstrap_gate` are benchmark controls only: both remain executed in false-promotion and false-block comparisons, and neither makes a family-wise error-control claim.

Frozen historical source and protocol records may retain the legacy internal words `reviewed` or `deployable`. In those records, `reviewed` refers only to prior automated or agent-assisted review passes, and `deployable` refers only to an observed-evidence method contract. Neither term records visible human approval, repository-owner acceptance, production integration, or production readiness.

This implementation does not claim a new statistical theorem, universal false-promotion control, production readiness, human or clinical validation, evaluator-platform validation, RAG Compass superiority, or universal governance superiority. Holm, Bonferroni, exact binomial tests, Hoeffding bounds, fixed-sample certification, and post-certification selection are established methods.
