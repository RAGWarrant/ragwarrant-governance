# Fixed-Sample Multi-Risk Warrant v2

Status: additive research implementation. Focus 1 remains frozen at digest `c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e`. The valid zero-power v1 baseline is preserved at local tag `V1_VALID_ZERO_POWER_BASELINE`, commit `bf3b3331b623afbdaed295919b3ac945c10692f6`.

This document freezes the v2 statistical specification before CI-v2 or LOCAL-v2 execution. It does not change scenarios, truths, thresholds, margins, sample sizes, risk definitions, production behavior, FULL entropy, or the v1 implementation. FULL is prohibited and no target drand round is selected.

## Research question and prespecified variants

The research question is whether using the logical structure of all-risks certification can recover useful power while retaining false-promotion control.

| Variant | Multiplicity structure | Quality test | Role |
|---|---|---|---|
| A | Flat Holm across the full candidate-by-risk family | v1 bounded paired Hoeffding | Exact v1 baseline |
| B | Candidate IUT, then Holm across candidates | v1 bounded paired Hoeffding | Logical-structure ablation |
| C | Flat Holm across the full candidate-by-risk family | Hoeffding-Bentkus | Quality-test ablation |
| D | Candidate IUT, then Holm across candidates | Hoeffding-Bentkus | `fixed_sample_multi_risk_warrant_v2` |
| D comparison | Candidate IUT, then Bonferroni across candidates | Hoeffding-Bentkus | Prespecified Holm/Bonferroni comparison |

Variant D is fixed before execution. Results cannot trigger a method switch or a change to the frozen benchmark.

Descriptive criteria are also prespecified. Any nonzero correct promotion in a safe-candidate `n=256` cell is reported as recovery. A LOCAL-v2 false-block reduction is called material only when it is at least 0.10 absolute versus A in a safe cell. These are descriptive research labels, not acceptance gates or guarantees.

## Candidate-level intersection-union test

For candidate `c`, let `K_c` be its complete frozen set of enabled overall, subgroup, and binary-risk components. Frozen truth treats quality equality and binary-risk equality as safe. The logical component violation nulls are therefore

```text
quality: H_cj = {E[D_cj] < -margin_j}
binary:  H_cj = {p_cj > threshold_j}.
```

The candidate is unsafe exactly on the union

```text
H_c = UNION over j in K_c of H_cj,
```

and is safe only on the intersection of all component-safe sets. Component p-values are evaluated at the least-favourable equality boundary. V1 labels the conservative closed supersets (`quality <= boundary`, `binary >= boundary`); v2 preserves those formulas and records that equality remains truth-safe. The closure convention can reduce boundary power but cannot increase false certification of an unsafe candidate.

Given valid component p-values `p_cj`, define

```text
p_candidate(c) = max over j in K_c of p_cj.
```

If `H_c` is true, at least one `H_cj*` is true. The event that the maximum is at most `u` is a subset of the event `p_cj* <= u`, so its probability is at most `u`. Thus the maximum is a valid p-value for the union null. This proof does not require independence among component p-values, and no within-candidate multiplicity penalty is required.

Holm is applied only after one candidate-level p-value has been formed for every member of the complete frozen candidate family. If Holm falsely rejects any true candidate null, the standard sequential Bonferroni argument bounds that event by the familywise level. This strong FWER result allows arbitrary dependence among candidate p-values. Candidate filtering, risk omission, evidence-driven relabeling, or changing the family before Holm would invalidate the design and is prohibited.

Certification means Holm or Bonferroni rejection of the candidate-level max-p null. Such rejection necessarily means every enabled component raw p-value is no larger than the candidate p-value; Holm additionally requires every preceding ordered candidate hypothesis to pass its step-down threshold. A component falling below a candidate's displayed rank threshold is diagnostic only and is not, by itself, certification. Operational cost/latency selection occurs only after certification. An empty certified set returns `INCONCLUSIVE`; malformed evidence fails closed.

## Hoeffding-Bentkus quality test

Let the paired candidate-minus-incumbent quality difference be `D_i` with frozen support `[a,b]`. Define

```text
L_i = (b - D_i) / (b - a)
tau = (b + margin) / (b - a).
```

Then `L_i` is in `[0,1]` and

```text
E[D] <  -margin  iff E[L] >  tau,
E[D] =  -margin  iff E[L] =  tau,
E[D] >= -margin  iff E[L] <= tau.
```

For the illustrative `D in [-1,1]` case, this reduces to `L=(1-D)/2` and `tau=(1+margin)/2`. The frozen benchmark does not use those bounds. Its actual support is `[-0.25,0.25]`, so v2 uses `L=(0.25-D)/0.50`, with `tau=0.54` for overall quality and `tau=0.56` for group quality.

For `n` independent bounded confirmatory losses, empirical risk `r_hat`, and fixed `tau` in `(0,1)`, the primary Learn-Then-Test specification gives

```text
x = min(r_hat, tau)
h1(x,tau) = x log(x/tau) + (1-x) log((1-x)/(1-tau))
k = ceil(n * r_hat)
p_H = exp(-n * h1(x,tau))
p_B = e * Pr(Binomial(n,tau) <= k)
p_HB = min(1, p_H, p_B).
```

The ceiling is required for bounded non-Bernoulli losses. The implementation uses explicit KL endpoint limits, stable log-sum-exp binomial tails, deterministic floating-point arithmetic, and a least-positive-float floor if exponentiation would underflow. It rejects empty, nonfinite, out-of-support, or invalid-bound evidence rather than clipping it. At `r_hat=0` the Hoeffding branch is `(1-tau)^n`; at `r_hat=1` the result is one.

Binary-risk tests are the exact v1 lower-binomial-tail implementation without behavioral change.

## Assumptions and claim boundary

Component validity assumes independent confirmatory units and prespecified bounded losses/thresholds. Pairing within a unit and arbitrary dependence among candidates or risks within a unit are allowed. A prespecified subgroup test is conditional on its realized count; missing subgroup evidence contributes p-value one. Development evidence is never used for certification, and truth-isolated benchmark variants never receive population truth.

The intersection-union principle, Hoeffding-Bentkus inequality, Learn-Then-Test construction, Holm, and Bonferroni are established methods and are not claimed as novel. CI-v2 and LOCAL-v2 are developmental Monte Carlo evidence. Their Wilson intervals quantify Monte Carlo estimation uncertainty, not candidate-risk uncertainty. No empirical result alone proves finite-sample control, universal superiority, production readiness, or human/clinical validity.

## Primary sources

- Angelopoulos, Bates, Candès, Jordan, and Lei, “Learn then test: Calibrating predictive algorithms to achieve risk control,” *Annals of Applied Statistics* 19(2), 1641–1662 (2025), [DOI 10.1214/24-AOAS1998](https://doi.org/10.1214/24-AOAS1998), especially Propositions 2.2 and 2.10.
- Angelopoulos et al., archived [arXiv 2110.01052v5](https://arxiv.org/pdf/2110.01052v5) and the authors' [official implementation at commit 3ad7a64](https://github.com/aangelopoulos/ltt/blob/3ad7a64adad9f356e29f40e73935a6114f896396/core/bounds.py).
- Berger and Hsu, “Bioequivalence Trials, Intersection-Union Tests and Equivalence Confidence Sets,” *Statistical Science* 11(4), 283–302 (1996), [DOI 10.1214/ss/1032280304](https://doi.org/10.1214/ss/1032280304).
- Bentkus, “On Hoeffding's inequalities,” *Annals of Probability* 32(2), 1650–1673 (2004), [DOI 10.1214/009117904000000360](https://doi.org/10.1214/009117904000000360).
- Hoeffding, “Probability Inequalities for Sums of Bounded Random Variables,” *JASA* 58(301), 13–30 (1963), [DOI 10.1080/01621459.1963.10500830](https://doi.org/10.1080/01621459.1963.10500830).
- Holm, “A Simple Sequentially Rejective Multiple Test Procedure,” *Scandinavian Journal of Statistics* 6(2), 65–70 (1979), [JSTOR 4615733](https://www.jstor.org/stable/4615733).
