# External Evaluator Adapters

RAGWarrant does not replace Ragas, DeepEval, TruLens, LangSmith, Phoenix, or platform evaluators.

The adapter layer normalizes exported evaluator metrics into a canonical schema and then uses those metrics as inputs to a promotion-control decision.

The demo uses synthetic sanitized evaluator rows. It commits no raw traces, raw questions, contexts, prompts, generated answers, or secrets.
