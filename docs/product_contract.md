# Product Contract

RAGWarrant is an open-source RAG governance and promotion-control engine. It evaluates proposed RAG policies against quality, evidence, cost, latency, risk, and claim-boundary constraints, then returns an auditable decision: promote, block, reject, or inconclusive.

RAGWarrant is not the chatbot. RAGWarrant is not a model. RAGWarrant is not a replacement for Ragas, DeepEval, LangSmith, Phoenix, Azure AI Foundry, AWS Bedrock, Vertex AI, or other evaluators. It can consume evaluator outputs as governance inputs, but evaluator tools remain the source of their own metrics and platform-native records.

## Workflow

1. Load policy candidates.
2. Load an evaluation dataset, sanitized rows, or external evaluator outputs.
3. Run policy comparison or import evaluator metrics.
4. Apply quality, evidence, cost, latency, regression, and risk gates.
5. Produce a decision: `PROMOTE`, `BLOCK`, `REJECT`, or `INCONCLUSIVE`.
6. Write audit artifacts.
7. Validate claim boundaries.
8. Exit with a machine-readable status code.

## Inputs

- policy configs
- dataset manifests
- sanitized evaluation rows
- external evaluator metrics
- cost and latency telemetry
- governance config
- claim-boundary config

## Outputs

- `promotion_decision.json`
- `run_manifest.json`
- `policy_summary_metrics.csv`
- `selector_comparison.csv`
- `claim_update.json`
- `validation_report.md`
- `validation_report.json`
- optional `audit_bundle/`

## Decisions

- `PROMOTE`: the candidate satisfied configured gates and claim boundaries.
- `BLOCK`: promotion was prevented because required inputs, quality signal, publication hygiene, or risk gates were not adequate.
- `REJECT`: evidence favored rejecting the candidate, commonly because quality loss or negative evidence crossed a configured boundary.
- `INCONCLUSIVE`: evidence was insufficient or mixed.
- `ERROR`: a runtime failure prevented an auditable decision.

This contract supports deployable open-source governance jobs. It does not assert live cloud certification, human validation, official platform benchmarking, or production operation.

The Docker runtime contract is a local deployment validation path. A passing Docker public-mini job shows the container can execute the governance contract locally; it is not a live cloud validation or production certification.
