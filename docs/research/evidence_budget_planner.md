# Evidence-budget planner protocol

Status: research planning protocol, version 1. It does not collect confirmatory evidence, execute FULL, select a beacon round, or change a promotion decision path.

Planner identifier: `RAGWARRANT_EVIDENCE_BUDGET_PLANNER_V1`.

Research framing: `ANALYTICAL_COMPONENT_FEASIBILITY_PLUS_SIMULATED_JOINT_OPERATING_BEHAVIOR`.

The planner answers a pre-data question: whether a declared sample-acquisition plan can make every mandatory component of a requested multi-risk warrant statistically attainable, and what evidence counts bind that plan. Focus 1 remains frozen at digest `c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e`. Existing Focus 2 v1 and IUT/Holm results are inputs to the research motivation only; this planner does not relabel or overwrite them.

## Prespecified inputs and isolation

The versioned configuration declares the candidate count, family-wise error level, hypothesis organization, mandatory risks and groups, public thresholds and margins, documented paired-quality support, explicit planning alternatives, marginal component-power targets, group acquisition target, proposed budgets, and per-row cost. Validation fails if a mandatory risk or group is removed or if a frozen threshold, margin, support bound, or Focus 1 digest changes.

Binary planning alternatives use the prespecified threshold-relative grid 20%, 50%, and 80% of each public threshold. The default operating calculation uses the 50%-of-threshold alternative. Quality calculations use declared mean slack values. Neither source is simulator population truth or an observed confirmatory outcome.

The configured protected groups form an explicitly declared mutually exclusive and exhaustive categorical partition. This is required for the natural-count acquisition model and does not authorize erasing intersectional or overlapping groups in a later protocol version.

## Multiplicity planning convention

This study does not search for another multiple-testing arrangement. It plans the implemented, prespecified candidate-level IUT/Holm method. With family-wise level \(\alpha\) and \(C\) frozen candidates, the effective pre-data component cutoff is the conservative first Holm step \(\alpha/C\). A flattened comparison can be represented only as a separately configured planning organization with \(M\) mandatory component hypotheses and cutoff \(\alpha/M\).

The 50%, 80%, and 90% targets in this study are marginal component planning powers. Component powers are not multiplied, averaged, or presented as joint candidate-certification power. The guarantee under evaluation remains false candidate certification across the frozen candidate family.

## Exact binary-risk planner

For a binary event threshold \(\tau\), the preserved test is

\[
H_0:p\geq\tau,\qquad H_1:p<\tau.
\]

At sample count \(n\), the rejection region is \(X\leq k_n\), where

\[
k_n=\max\{k:\Pr_{\tau}(X\leq k)\leq\alpha_{\mathrm{eff}}\}.
\]

If no such event count exists, the component is `STRUCTURALLY_UNCERTIFIABLE_AT_THIS_N`. The best-case zero-event p-value is \((1-\tau)^n\). Equality at the threshold is retained in the null, so the planning test is conservative relative to the truth rule that treats equality as acceptable.

At unadjusted \(\alpha=0.05\), the first structurally certifiable zero-event sample counts are 59 for threshold 0.05, 99 for threshold 0.03, and 29 for threshold 0.10. Thus the execution-failure component cannot certify at \(n=64\), even with zero failures, and small realized subgroup counts may be structurally incapable of passing an enabled component. These are closed-form, unadjusted component minima—not multiplicity-adjusted budgets, component-power targets, joint-warrant power, or recommended operating points.

For each explicit \(p_{alt}<\tau\), conditional planning power is calculated exactly as

\[
\Pr_{p_{alt}}(X\leq k_n).
\]

Minimum sample counts are found by deterministic enumeration. Exact nonrandomized binomial power can fall at an adjacent \(n\) when the discrete rejection count has not yet advanced, so the implementation does not assume stepwise monotonicity in \(n\). These are conditional planning calculations, not guarantees of future power.

Developmental simulation is retained for behavior that the component calculation does not identify: multiple risks acting jointly, candidate-level IUT and Holm step-down behavior, candidate/risk dependence, random subgroup acquisition, false promotion/certification/blocking, joint warrant power, and operational selection. The simulation did not discover the closed-form structural minima, and the analytical calculation does not replace the joint operating study.

## Bounded paired-quality planner

Let \(D_i\) be the paired candidate-minus-incumbent quality difference with documented public support \([a,b]\), width \(w=b-a\), and noninferiority margin \(m\). The preserved one-sided Hoeffding gate certifies only when

\[
\bar D>-m+w\sqrt{\frac{\log(1/\alpha_{\mathrm{eff}})}{2n}}.
\]

The right side is reported as the minimum certifying observed mean for every analyzed \(n\). The smallest algebraic crossing is separated from a power calculation.

For a declared planning effect \(\mathbb E[D]=-m+s\), \(s>0\), a distribution-free lower bound on component power is available when \(s\) exceeds the Hoeffding radius:

\[
1-\exp\left(-\frac{2n(s-r_n)^2}{w^2}\right),
\qquad
r_n=w\sqrt{\frac{\log(1/\alpha_{\mathrm{eff}})}{2n}}.
\]

The reported minimum \(n\) for a target lower bound is the deterministic inversion of this expression. It depends on the declared mean slack and bounded-IID contract; it is not a claim about an unspecified data distribution.

## Empirical-Bernstein planning/test alternative

The variance-sensitive alternative follows Theorem 4 of Maurer and Pontil, [Empirical Bernstein Bounds and Sample Variance Penalization](https://arxiv.org/abs/0907.3740). It is preserved alongside Hoeffding rather than selected because it looks favorable.

Normalize paired differences to bounded losses:

\[
L_i=\frac{b-D_i}{b-a}\in[0,1],
\qquad
q=\frac{b+m}{b-a}.
\]

Then \(\mathbb E[D]>-m\) is equivalent to \(\mathbb E[L]<q\). For \(n\geq2\), unbiased sample variance \(V_n\), and fixed level \(\delta\), the implemented conservative one-sided upper bound is

\[
U_\delta=\bar L+
\sqrt{\frac{2V_n\log(2/\delta)}{n}}+
\frac{7\log(2/\delta)}{3(n-1)}.
\]

Certification is strict: \(U_\delta<q\). Values outside \([0,1]\), nonfinite inputs, and \(n<2\) fail closed. At zero sample variance the additive term remains; the radius is not zero. The report's variance rows are conditional crossing sensitivities under prespecified sample-variance values. Mean and variance alone do not identify a finite-sample power distribution, so the planner does not report empirical-Bernstein 50/80/90% power.

## Protected-group acquisition

Every required group gets its own statistical count requirement. Under natural sampling with target prevalence \(\pi_g\), `required_group_n / prevalence` is reported only as an expected-total diagnostic. A high-probability total is instead the smallest \(N\) satisfying

\[
\Pr\{\operatorname{Binomial}(N,\pi_g)\geq n_g\}\geq 1-\eta_g.
\]

The v1 planner divides a prespecified total acquisition-failure allowance across mandatory groups and uses a union bound. This provides a dependence-robust lower bound for acquiring every required group count; it is distinct from statistical power after those counts are acquired.

## Allocation and statuses

For each marginal component-power target, the planner takes the maximum required \(n\) across all mandatory overall risks and separately across all mandatory risks within each group. It never drops a group or risk. The reported binding constraint is the largest natural-acquisition requirement.

The recommended stratified design uses a representative IID core for all unweighted population-level estimands and conditional-IID group top-ups for group-specific estimands. Expected top-up cost is calculated exactly from the binomial core-count shortfall. A conservative no-reuse maximum is also reported. Cost is measured per fully evaluated evidence row across the frozen candidate family and incumbent.

Statuses are:

- `CERTIFICATION_STRUCTURALLY_INFEASIBLE`: a best-case rejection region cannot exist at the declared count.
- `CERTIFICATION_BUDGET_UNDERPOWERED`: structural crossing exists, but a prespecified marginal component-power/acquisition plan is not met.
- `CERTIFICATION_BUDGET_MARGINAL`: the lower prespecified component target and acquisition target are met.
- `CERTIFICATION_BUDGET_FEASIBLE`: the desired prespecified component target and acquisition target are met.

None is a guarantee that a candidate will certify.

## Outputs and limitations

The runner writes only ignored local planning reports and refuses a FULL flag. It never imports the simulator, public-beacon machinery, or confirmatory benchmark runner. The CSV preserves per-budget and per-risk rows, structural feasibility, conditional powers or lower bounds, expected group counts, and exact acquisition probabilities.

This version assumes IID observations within each target population or conditional group, valid fixed candidate/risk families, documented bounded quality support, explicit planning alternatives, and the existing component tests. It does not model evaluator drift, clustering, label error, overlapping group memberships, recruitment failure, dependence across observations, or joint candidate-certification power. Protocol changes require a new version before any future confirmatory execution.

## Related-work boundary

The planner integrates established ingredients: Learn-Then-Test risk control ([Angelopoulos et al.](https://arxiv.org/abs/2110.01052)), adaptive LTT ([arXiv:2409.15844](https://arxiv.org/abs/2409.15844)), finite-sample empirical-Bernstein bounds, group-conditional risk-control work, and classical stratified sample allocation. The end-to-end RAG governance integration is a provisional engineering/research framing, not a novel theorem or established novelty claim.
