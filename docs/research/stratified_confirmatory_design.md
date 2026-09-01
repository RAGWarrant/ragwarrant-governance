# Stratified confirmatory evidence design

Status: design only. `STRATIFIED_CONFIRMATORY_EVIDENCE_V1` has not sampled evidence, run FULL, selected a public-beacon round, or changed an existing warrant method.

## Objective

Natural sampling can make a low-prevalence protected-group requirement dominate total evidence acquisition even when the group-specific statistical count is moderate. This design separates representative population evidence from prespecified subgroup quota acquisition without changing the frozen risk thresholds, margins, groups, candidate family, or component tests.

## Two evidence sources

1. A representative IID core of size \(N_0\), sampled from the declared target population, supports the preserved unweighted overall-population quality and binary-risk tests.
2. Conditional-group top-ups continue independently within each required group until its prespecified quota \(n_g\) is reached. Core observations from group \(g\) may count toward \(n_g\) when they satisfy the same measurement and inclusion contract.

The groups in v1 are declared as a mutually exclusive and exhaustive categorical partition. Top-ups must be IID from the same target conditional population as the corresponding core group members. Convenience sampling, adaptive outcome-dependent recruitment, candidate-specific filtering, and stopping based on measured losses are out of scope.

## Estimands and valid use

Group-specific tests estimate conditional risks or quality means such as \(R_g=\mathbb E[L\mid G=g]\). They may use core group members plus valid conditional-group top-ups.

Overall-population tests estimate \(R=\mathbb E[L]\) under the target population mixture. In v1, only the representative core enters these preserved unweighted tests. Subgroup top-ups alter the observed mixture and must not be pooled into an unweighted overall estimate.

The target-prevalence identity

\[
R=\sum_g \pi_g R_g
\]

suggests a future weighted design, but it is not implemented. Such a version would have to freeze target prevalences or their independent estimation procedure, inclusion probabilities, bounded weighted losses, alpha allocation, and a finite-sample upper-bound construction before sampling. Plugging quota-altered rows into the current overall tests would be invalid.

## Quota construction

For a prespecified marginal component-power target, each quota is

\[
n_g=\max_{r\in\mathcal R_g} n_{g,r},
\]

where every mandatory group risk remains represented. The representative core is

\[
N_0=\max_{r\in\mathcal R_{overall}} n_r.
\]

With representative core count \(X_g\sim\operatorname{Binomial}(N_0,\pi_g)\), the realized top-up is \((n_g-X_g)_+\). The planner reports the exact expectation of this shortfall for cost planning and the conservative no-reuse ceiling \(N_0+\sum_g n_g\). The expectation is not a guaranteed maximum.

For natural acquisition, the planner separately finds the smallest total \(N\) for each group-count tail and applies a prespecified union-bound failure allocation. Dividing by prevalence is never labeled as a guarantee.

## Recommended future design from the v1 study

The prespecified operating objective is 80% marginal component planning power at the existing conservative first-step Holm cutoff, plus at least 95% simultaneous group-count acquisition probability. It is not 80% joint warrant power.

The analytical study recommends:

- representative IID core: `n=1383` fully evaluated family rows;
- majority quota: at least `826` valid group observations;
- minority quota: at least `826` valid group observations;
- exact expected total after core reuse and conditional top-ups: approximately `2070.70` rows under the declared 90/10 target prevalences;
- conservative no-reuse ceiling: `3035` rows;
- cost unit: one normalized fully evaluated row across the frozen candidate family and incumbent.

The dominant overall component is execution-failure risk (`n=1383` at the selected alternative). The group quota is set by safety-violation risk (`n=826`), not quality (`n=177`), at the same marginal target. Natural 10% minority acquisition would require total `N=8803` to satisfy the prespecified group-count tail criterion.

These numbers are planning outputs conditional on declared alternatives and assumptions. They do not authorize confirmatory collection and must not be chosen or revised after viewing FULL evidence.

## Execution prerequisites for a future version

Before collection, an owner would need to approve and freeze the sampling frame, group-assignment procedure, conditional recruitment channels, evaluator contract, cost definition, missing-data behavior, candidate family, all risk tests, inclusion/exclusion rules, and a sealed confirmatory seed/beacon protocol. A future protocol must specify whether top-up collection is fixed-quota or has a maximum recruitment budget and how recruitment failure is handled.

No production selector, `promotion_decision.json`, warrant schema, workflow, or public-beacon implementation changes in this design.
