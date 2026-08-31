# Fixed-Sample Multi-Risk Promotion Warrant V1 — Design Only

Status: proposal for owner review after the Focus 1 benchmark protocol was frozen and its CI profile validated.

This document defines a possible optional research method, `fixed_sample_multi_risk_warrant_v1`. It does not implement the method, add it to a registry or CLI, alter a selector, or modify `promotion_decision.json`.

## Goal and boundary

The proposed warrant would control false certification across a frozen family of candidate policies and enabled risks using one fixed, independent confirmatory sample. It would produce a certified set first and apply an operational objective only within that set.

This is a conservative design assembled from established bounded-loss concentration and multiple-testing procedures. No new statistical theorem, Learn-Then-Test novelty, conformal-risk novelty, or sequential-testing novelty is claimed.

## Frozen candidate family

Before confirmatory evidence is collected, freeze and hash:

- candidate policy IDs and immutable policy specifications;
- incumbent identity;
- enabled overall and group risks;
- group definitions;
- loss definitions and finite bounds;
- risk thresholds and noninferiority margins;
- confirmatory sample size and any minimum group counts;
- family-wise error level `alpha`;
- multiplicity method;
- operational objective and tie-breaker; and
- evaluator and evidence schema versions.

Adding a candidate, risk, group, or threshold after evidence is observed creates a new family and requires independent confirmatory evidence or an owner-approved statistical amendment. Development results may choose the family, but cannot certify it.

## Independent fixed confirmatory evidence

Confirmation is a single prespecified fixed sample, independent of development evidence and candidate tuning. All candidates are evaluated on the same paired examples whenever technically possible. The procedure is not adaptive or sequential: it does not stop early, add samples based on interim results, recycle rejected candidates, or spend alpha over time.

Candidate identity and risk definitions are checked against the frozen family hash before analysis. A mismatch produces no warrant.

## Bounded loss definitions

Every tested quantity must have an owner-approved finite support before confirmation.

### Paired quality noninferiority

For candidate `j`, example `i`, and optional group `g`, define paired quality delta:

```text
D(i,j,g) = candidate_quality(i,j,g) - incumbent_quality(i,g)
```

with frozen bounds `[a(j,g), b(j,g)]`. The requirement is:

```text
E[D(j)] >= -quality_noninferiority_margin
E[D(j,g)] >= -group_quality_noninferiority_margin
```

No clipping is allowed. Out-of-range evidence is malformed.

### Binary risks

Safety violation, execution failure, and insufficient evidence are bounded losses in `{0, 1}`. Each requirement is:

```text
E[L(j,r)] <= maximum_risk(r)
```

An enabled group risk uses the corresponding conditional loss and threshold. Other bounded losses may be added only in a versioned protocol.

Cost and latency remain operational objectives unless the owner explicitly defines bounded risk thresholds and includes them in the family.

## One-sided hypotheses

Each candidate/risk pair is a separate null hypothesis representing a safety requirement that has not been established.

For an upper-bounded risk:

```text
H0(j,r): population risk >= threshold(r)
H1(j,r): population risk < threshold(r)
```

For quality noninferiority:

```text
H0(j,q): population quality delta <= -margin(q)
H1(j,q): population quality delta > -margin(q)
```

Exact boundary conventions must be fixed before implementation so the test and truth classifier agree. V1 should use valid one-sided p-values or confidence bounds for bounded observations. A conservative initial option is Hoeffding-style bounds using the declared range; exact binomial methods may be used for Bernoulli risks if introduced without a heavy dependency and frozen in the method version.

For bounded upper-risk observations in `[a,b]`, a design candidate for the one-sided boundary p-value is:

```text
p = exp(-2 * n * max(0, threshold - observed_mean)^2 / (b - a)^2)
```

For quality lower-bound testing:

```text
p = exp(-2 * n * max(0, observed_mean + margin)^2 / (b - a)^2)
```

These formulas and assumptions require an independent statistical implementation review before adoption. Missing group rows cannot be treated as zero loss.

## Multiple candidates and multiple risks

The family contains every enabled candidate-risk hypothesis, including enabled subgroup hypotheses. Let `M` be the frozen count.

Initial conservative options are:

- Bonferroni: reject hypothesis `h` only if `p_h <= alpha / M`.
- Holm step-down: sort p-values and apply Holm's ordered thresholds across the entire frozen family.

Both target family-wise error control under their standard validity conditions. The chosen procedure must be named and hashed in the warrant. No unadjusted per-candidate or per-risk alpha is allowed. Dependence does not justify silently reducing `M`.

## Certified candidate set

A candidate is certified only when every enabled hypothesis for that candidate is rejected by the selected family-wise procedure and every evidence/schema check passes. Certification of one candidate does not imply certification of another.

The output includes:

- the complete frozen family;
- all raw one-sided p-values or bounds;
- adjusted decisions;
- candidate-level failed and missing conditions; and
- the final certified policy IDs.

An empty certified set is a valid fail-closed result.

## Operational selection after certification

Only after the certified set is fixed may the method choose a candidate using the frozen operational objective. Operational cost or latency cannot rescue an uncertified candidate and cannot affect multiplicity correction.

The initial proposed objective is the same predeclared scalar used by the benchmark:

```text
cost_weight * observed_mean_cost + latency_weight * observed_mean_latency
```

The owner must approve whether the production objective should use observed confirmation values, separately estimated operational values, or declared planning values. Ties must be deterministic.

## Empty, missing, and malformed behavior

- Empty certified set: block promotion and record `NO_CERTIFIED_CANDIDATE`.
- Empty evidence: no warrant.
- Nonfinite or out-of-range observation: no warrant.
- Missing candidate, risk, group, or incumbent pairing: affected candidate fails closed; a family/schema mismatch invalidates the full warrant.
- Duplicate examples or policies: no warrant.
- Candidate-family hash mismatch: no warrant.
- Insufficient prespecified group count: affected group gate fails closed, or the full warrant is invalid if that behavior was frozen.
- Evaluator or schema version mismatch: no warrant.
- Interrupted or partial computation: write no complete warrant.

Failures must be structured and auditable, not silently coerced to passing values.

## Proposed `promotion_warrant.json` schema

This is a proposed new artifact, not an update to the existing promotion decision schema.

```json
{
  "schema_version": "promotion_warrant.v1.proposed",
  "method_id": "fixed_sample_multi_risk_warrant_v1",
  "status": "CERTIFIED_SET_NONEMPTY | NO_CERTIFIED_CANDIDATE | INVALID_EVIDENCE",
  "deployable": false,
  "research_only": true,
  "family": {
    "family_hash": "sha256:...",
    "candidate_policy_ids": ["..."],
    "incumbent_policy_id": "...",
    "enabled_risks": ["..."],
    "group_ids": ["..."],
    "confirmatory_sample_size": 0
  },
  "error_control": {
    "family_wise_alpha": 0.05,
    "procedure": "bonferroni | holm",
    "hypothesis_count": 0,
    "fixed_sample": true,
    "sequential": false
  },
  "evidence": {
    "evidence_hash": "sha256:...",
    "schema_version": "...",
    "evaluator_versions": ["..."],
    "development_evidence_used_for_certification": false
  },
  "candidate_results": [
    {
      "policy_id": "...",
      "certified": false,
      "tests": [
        {
          "risk_id": "...",
          "null_boundary": 0.0,
          "sample_count": 0,
          "raw_p_value": 1.0,
          "adjusted_rejection": false,
          "failure_reason": null
        }
      ]
    }
  ],
  "certified_policy_ids": [],
  "selected_policy_id": null,
  "operational_objective": {
    "definition": "...",
    "selected_value": null,
    "tie_breaker": "policy_id"
  },
  "claim_boundaries": [
    "research_only",
    "not_production_adopted",
    "no_novel_statistical_theorem_claim"
  ]
}
```

Before implementation, the owner and schema reviewer must decide whether raw p-values, adjusted p-values, confidence bounds, or all three are required for auditability.

## Relationship to `promotion_decision.json`

The proposed warrant is separate evidence. It must not overwrite, reinterpret, or silently extend `promotion_decision.json`. Until explicit adoption approval:

- existing promotion decisions remain authoritative for the current product path;
- the warrant is research-only and `deployable=false`;
- no selector or CLI reads it; and
- no historical artifact is regenerated.

A later integration design must specify whether a valid nonempty warrant is necessary, advisory, or translated into a new versioned public decision. That owner-level semantic choice is out of scope here.

## Benchmark evaluation plan

After implementation approval, register the warrant only as an optional Focus 2 research method and evaluate it against the already frozen Focus 1 protocol.

Required evaluation includes:

- all seven scenario families and both sample sizes;
- trial-level false promotion and false certification;
- false block and correct promotion;
- no-safe-candidate blocking;
- certified-set size and operational regret;
- Bonferroni and Holm as separately identified variants;
- method-order and evidence-digest invariance;
- truth isolation;
- malformed and missing evidence;
- dependence, multiplicity, subgroup harm, and shift; and
- negative or weak outcomes without scenario retuning.

The warrant must not receive development truth or confirmatory population truth. The oracle remains the only truth-using method. Any protocol change after inspecting warrant results creates a new benchmark version.

## Owner adoption questions

1. What family-wise alpha is acceptable, and is it a research default or proposed product default?
2. Should Bonferroni or Holm be the initial primary procedure?
3. What exact quality and loss bounds are defensible for each evaluator?
4. Which subgroup hypotheses are mandatory, and what minimum group count is required?
5. Are risk thresholds strict or inclusive at equality?
6. Which operational values and weights may rank certified candidates?
7. Does any missing candidate/risk invalidate one candidate or the entire family?
8. Which evaluator/schema hashes must be part of the frozen family?
9. What audit fields are required in the proposed warrant artifact?
10. If adopted later, how would the warrant relate to the existing public promotion decision without changing historical semantics?
11. What independent statistical and claim review is required before production consideration?

## Explicit non-novelty boundary

Bonferroni, Holm, bounded-loss concentration, paired noninferiority testing, fixed-sample confirmation, certified sets, and operational selection after statistical gating are established ideas. This proposal does not claim their invention, a new error-control theorem, Learn-Then-Test novelty, conformal-risk novelty, or sequential-testing novelty. Any contribution would be an explicitly scoped RAG governance integration evaluated with the frozen known-truth false-promotion benchmark.

WAITING_FOR_OWNER_APPROVAL_FIXED_SAMPLE_WARRANT_IMPLEMENTATION
