# Focus 2 diagnostic IUT-Holm comparison

Status: additive research comparison; developmental evidence only.

Method ID: `FIXED_SAMPLE_MULTI_RISK_WARRANT_V2_IUT_HOLM`.

This comparison preserves `fixed_sample_multi_risk_warrant_v1` and every v1 component test exactly. Its only statistical change is hypothesis composition:

1. compute every mandatory v1 component p-value for each frozen candidate;
2. form `p_candidate = max(component p-values)` without dropping missing or difficult risks;
3. apply Holm to the complete frozen candidate family;
4. certify only rejected candidate nulls; and
5. apply the frozen operational selection rule only after certification.

For candidate `c`, the unsafe null is the union of its component violation nulls. If any component null is true, `{max_j p_cj <= u}` is contained in the rejection event of that true component, so the maximum is super-uniform. Holm then controls the probability of falsely rejecting at least one true candidate null across the complete candidate family. The argument allows arbitrary dependence among component p-values and candidates, provided each marginal component p-value is valid. It does not permit dependence across confirmatory observations that invalidates a component test.

This is the multiple-risk construction in Angelopoulos et al., *Learn then Test: Calibrating Predictive Algorithms to Achieve Risk Control*, arXiv:2110.01052v5, Section 2.4, Proposition 6. The intersection-union principle is established prior work and is not claimed as novel.

Frozen truth treats equality as safe. The component tests retain the conservative closed nulls from v1 (`mean quality <= boundary` and `event probability >= threshold`), so equality is not certified. This costs boundary power but does not weaken false-certification control.

The comparison is behaviorally identical to the already executed `B_IUT_HOEFFDING` ablation. The explicit method name was added after those developmental results were observed; it is an alias for auditability, not fresh evaluation evidence. It does not justify drawing replacement evidence or rerunning a redundant Monte Carlo matrix.

## Variance-sensitive quality method: design only

No second quality method is implemented in this slice. A later separately versioned design may evaluate Maurer and Pontil, *Empirical Bernstein Bounds and Sample Variance Penalization*, arXiv:0907.3740, Theorem 4.

For i.i.d. `Z_i in [0,1]` and `n >= 2`, Theorem 4 gives, with probability at least `1-delta`,

`E[Z] <= mean(Z) + sqrt(2 V_n log(2/delta)/n) + 7 log(2/delta)/(3(n-1))`,

where `V_n` is their pairwise-difference sample variance, equal to the usual unbiased sample variance.

Using the public paired-delta support `D in [-0.25,0.25]`, set `Z=(0.25-D)/0.5`. Then `H0: E[D] <= -margin` is equivalent to `H0: E[Z] >= (0.25+margin)/0.5`. A future test would invert the one-sided upper bound and reject only when the bound is strictly below the loss threshold. It would require a monotone numerical inversion, explicit endpoint handling, and multiplicity integration fixed before evidence is viewed.

The theorem's additive `1/(n-1)` term remains large for `n=64` and for realized minority-group counts, even when sample variance is small. The decision to examine this direction is explicitly data-informed by the retained developmental counts, variances, and quality bottlenecks. It is design-only and cannot become a confirmatory method without a separate version frozen before new evidence is used. The diagnostic audit does not assume that empirical Bernstein resolves the observed subgroup bottleneck.

## Boundaries

- Focus 1 remains frozen at `c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e`.
- V1 remains the preserved negative baseline at local tag `V1_VALID_ZERO_POWER_BASELINE`.
- CI and LOCAL evidence is developmental.
- FULL is prohibited and uninspected; no drand round is selected.
- Population truth is available only to post-decision benchmark diagnostics.
- No production selector, promotion-decision schema, workflow, README claim, historical artifact, or historical result is changed.
