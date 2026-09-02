# Stratified confirmatory evidence v1

Status: prospective planning contract frozen; real evidence collection is not authorized.

Contract ID: `STRATIFIED_CONFIRMATORY_EVIDENCE_V1`. This is additive to the frozen Focus 1 benchmark and the preserved warrant baselines. It does not change scientific thresholds, risks, margins, candidate tests, production behavior, or historical results.

## Scope and execution boundary

The versioned contract currently applies to `STRATIFIED_PLANNING_SUPERPOPULATION_V1`: independently sampled eligible synthetic evaluation events from `SYNTHETIC_ELIGIBLE_EVENT_FRAME_V1`. One observation is one independently sampled eligible event with one immutable unit ID. The opaque `majority` and `minority` labels are planning strata with declared proportions 0.90 and 0.10; they are not demographic claims.

Real collection remains `BLOCKED_PENDING_OWNER_OPERATIONAL_FIELDS` until the owner freezes and hashes a real target population, probability sampling frame, independent unit or cluster definition, inclusion/exclusion codebook, categorical group codebook and authoritative label source, recruitment channels and sites, absolute time window, screening mechanism, privacy rules, and stage-specific cost inputs. Filling these fields requires a new study digest. It must not silently reinterpret this synthetic contract.

No observation may be acquired under this document. `execution_authorized=false`, `FULL=false`, and no drand round is selected.

## Frozen eligibility and group contract

Eligibility and group assignment must be available from immutable pre-evaluation metadata. Inclusion is presence in the frozen frame and satisfaction of the frozen eligibility rule. Duplicates, units without eligibility evidence, and missing, ambiguous, multiple, or out-of-codebook group labels are excluded and counted as unusable. Group assignment must not use candidate output, evaluator score, quality, a safety or execution event, insufficient evidence, a p-value, certification, or selection.

Groups form a mutually exclusive and exhaustive categorical partition. The group codebook, assignment implementation, and label-source version freeze before sampling identities are derived. They cannot change after recruitment begins. Low-cost screening is permitted only if every eligible unit retains a known probability of entering the within-group draw. Imperfect positive-only routing is not authorized: sensitivity/specificity cost correction does not repair selection bias.

Privacy is synthetic-input-only for this planning version. A future operational contract must freeze retention, access, de-identification, and aggregate-publication boundaries before collection.

## Candidate and measurement freeze

Before sampling identities are derived, freeze the complete candidate family, incumbent, model and retrieval configuration, evaluator implementation, risk definitions, measurement support, thresholds, margins, and evidence pipeline. Every admitted unit is exposed to every candidate under the same pipeline. Candidate filtering after confirmatory outcomes is forbidden.

## Representative IID core

The core is an IID probability sample from the frozen superpopulation. The v1 mechanism is equal-probability random selection from the pre-existing frame, without replacement of unit IDs and with duplicate rejection. This superpopulation interpretation and cross-unit independence are assumptions of the preserved component tests; a fixed finite-frame claim would require separate review.

Sampling stops at the frozen valid-core count, not at a favorable outcome. Recruitment failures, unusable measurements, and duplicates are replaced only through the next prespecified random identity until the frozen cap or deadline. Outcome-dependent replacement is forbidden. A cap or deadline shortfall returns `BLOCKED_INSUFFICIENT_GROUP_EVIDENCE`.

The representative core is the sole source for unweighted overall-population quality and binary-risk tests. Conditional top-ups never enter those tests. Core cost and latency are the sole source for post-certification operational selection in this version.

## Conditional group top-ups

For each required group, top-ups are sampled randomly and without replacement from the same target population conditional on the frozen group label. Eligibility may depend only on the target-population rule and label. Core members in a group count once toward that group's quota. Top-up sampling stops when the frozen valid quota is reached. Quotas and groups cannot be lowered or removed after recruitment starts.

Core and top-up collection must use the same 14-day relative regime, candidate exposure, model/evaluator versions, measurement pipeline, and outcome-missingness rules. Unit IDs must be unique across the core and every top-up. A missing quota at the 50,000-unit screening cap or 14-day deadline returns `BLOCKED_INSUFFICIENT_GROUP_EVIDENCE`.

## Estimands and evidence routing

- Overall-population tests use representative-core observations only.
- A group-specific test uses all valid matching core observations plus valid exchangeable top-up observations for that group.
- Top-ups do not alter target-population prevalence.
- Overall and group tests may share core observations; the candidate IUT and Holm procedure permit this dependence when marginal component p-values remain valid.
- No unweighted pooled statistic over core plus top-ups is an overall-population estimate.

A future design-weighted overall estimator is out of scope. Such a version must freeze unit inclusion probabilities, target group proportions, inverse-probability weights, finite-population or superpopulation variance estimation, missing-label handling, and prevalence-error sensitivity before evidence exists.

## Exchangeability gate

Pooling group-matching core and top-up observations for a group test is allowed only when they have the same target group and eligibility rules; arise under the same bounded time regime, sites/domains, source frame, screening channel, candidate exposure, and measurement pipeline; are randomly sampled within group; contain no duplicate unit; and were recruited without outcome access.

Before analysis, compare by source: frame coverage, calendar distribution, site/domain, screening channel, eligibility and missingness, candidate exposure, evaluator/model hashes, unusable-rate, and measurement-support violations. Diagnostics are gates, not covariates selected after results. Any material unexplained source difference returns `STRATIFIED_DESIGN_BLOCKED_TOPUP_EXCHANGEABILITY`. The estimand must not be weakened to bypass this gate.

## Costs and recruitment

Workload reporting separates group screening, eligibility screening, acquisition, full family evaluation, manual review, duplicates, unusable observations, and failed recruitment. The preserved 2,070.70 value is an expected number of valid full-family evaluated rows for core 1,383 and quota 826 per group under ideal routing. It is not total workload. The preserved 3,035 value is the no-core-reuse maximum of valid evaluated rows, not attempted evaluations or screened units.

Expected and high-probability screening counts must use declared eligibility, usability, duplicate, prevalence, and routing probabilities. The planning implementation reports a simultaneous conservative bound using a union allocation across the core and each group requirement; group bounds take no credit for the random core and are therefore deliberately conservative. Every stage also requires an operational cap; a deadline alone is not a numerical workload bound.

## Failure states

- `BLOCKED_PENDING_OWNER_OPERATIONAL_FIELDS`: the real operational population/frame/codebook is not frozen.
- `BLOCKED_INSUFFICIENT_GROUP_EVIDENCE`: a core or group quota is short at its cap/deadline.
- `STRATIFIED_DESIGN_BLOCKED_TOPUP_EXCHANGEABILITY`: required source-equivalence conditions fail.
- Invalid, missing, nonfinite, duplicated, outcome-selected, or version-mismatched evidence fails closed.

This contract does not establish that exchangeability holds in future data. It specifies what must be true and audited before the group evidence can be combined.
