# Candidate-level joint warrant power planning

Status: developmental planning simulation; no confirmatory evidence collected.

## Question

For a prespecified representative-core plus conditional-top-up design, what is the probability that the complete preserved warrant certifies at least one truly safe planning candidate? Component-level 50%, 80%, and 90% planning targets do not answer this question because a candidate must pass every enabled component and Holm is applied across the complete frozen candidate family.

## Preserved warrant

The planning adapter changes only evidence routing. It calls the unchanged bounded paired-Hoeffding quality p-value and exact one-sided binomial p-value. For candidate `c`, it uses

`p_candidate = max(p_c,overall-quality, p_c,each-group-quality, p_c,each-overall-binary-risk, p_c,each-enabled-group-binary-risk)`.

It then calls unchanged Holm across all 24 candidate p-values. No candidate is filtered before Holm, missing mandatory evidence yields p-value one or a blocked decision, and truth is unavailable to the method. Overall components receive core data only. Group components receive matching core plus valid top-up data. Operational cost/latency selection occurs only after certification and uses core evidence.

The maximum-p intersection-union test is valid for the null that at least one required component is unacceptable. Holm controls the probability of falsely certifying at least one unsafe candidate when marginal component p-values are valid. Cross-component and cross-candidate dependence is permitted; independence across sampled units remains an assumption of the preserved component tests.

## Planning alternatives and dependence

Inputs are declared in `configs/research/stratified_joint_warrant_power_v1.yaml` before execution. They are not hidden Focus 1 truth. Three planning candidates are safe under a bounded symmetric quality model and explicit binary alternatives. The other 21 candidates remain in the family and each is assigned a prespecified unacceptable component on a rotating schedule. Equality is treated consistently: truth equality is safe, while component tests use least-favourable closed null boundaries.

Low, medium, and high dependence use shared-variation mixture fractions 0.0, 0.5, and 0.9. These are not Pearson correlations. Within one unit, one latent draw and mixture mask are reused across candidates and risks; units remain independent. Core group membership is sampled once and shared across all candidate measurements. Matching core observations are reused in group tests and top-ups bring each group to the frozen quota. No dependence structure is selected after seeing results. The simulator uses prespecified planning truth; the warrant method does not receive it.

The 21 unsafe controls rotate across all eight component-failure scopes: overall quality, each group-quality component, overall safety, execution failure, insufficient evidence, and each group-safety component. The overall-safety control necessarily also violates at least one exhaustive-group safety component; an overall marginal cannot exceed the threshold while every exhaustive group marginal remains below it. Operational cost and latency ranks use frozen modular permutations, so safe candidates are not automatically the cheapest family members.

## Reported quantities

For every core/quota design and dependence level, the study reports:

- marginal component rejection probabilities at the fixed conservative `alpha/24` threshold;
- `max(0, 1 - sum(component miss probabilities))`, a union-bound lower bound for one candidate's joint power;
- the product of marginal powers, labeled only as an independence approximation;
- Monte Carlo probability that each safe planning candidate is certified by the actual IUT/Holm warrant;
- probability that at least one safe candidate is certified;
- probability that at least one unsafe planning candidate is certified;
- expected certified-set size; and
- safe, unsafe, and no-selection probabilities.

The random number of matching core group members is simulated. Each group's test count is `max(core group count, quota)` after the top-up stopping rule. This matters because exact-binomial power is discrete and can be saw-toothed. Monte Carlo Wilson intervals describe planning-simulation uncertainty, not candidate-risk confidence.

## Prespecified designs and selection rule

The grid retains the component-planner points 898/536, 1,383/826, and 1,720/1,028, then adds 2,304/1,380 and 3,072/1,840 as planning-only expansions. The first value is core count and the second is each group quota. This does not alter the frozen Focus 1 sample schedule or collect new benchmark evidence.

For descriptive 50%, 80%, and 90% at-least-one-safe operating points, choose the first prespecified grid design whose point estimate reaches the target at every frozen dependence level. Wilson uncertainty is always reported. This is not a guarantee, pass/fail gate, or permission to collect evidence. If a target is not reached, report that result without weakening a risk, threshold, margin, group, or dependence case.

## Boundaries

The model is a planning mechanism conditional on explicit alternatives, bounded distributions, IID units, group prevalence, and exchangeable top-ups. It does not predict external evaluator drift, recruitment behavior, dependence outside the grid, or production prevalence. False-certification Monte Carlo results do not replace the finite-sample FWER argument. Fewer false certifications alone do not establish operational usefulness.

The original FULL profile remains `FULL_ORIGINAL_BUDGET_NOT_EXECUTED_DEVELOPMENTALLY_UNDERPOWERED`. A future stratified confirmatory study requires a new immutable study digest, new trial identity schedule, owner-completed operational sampling fields, completed exchangeability and cost gates, and a later drand seal. No FULL execution or drand selection is authorized here.
