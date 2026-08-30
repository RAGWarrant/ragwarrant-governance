# Generative LLM Validation Preflight Report

- Starting commit: `e8e228820ed51d7e907bf25eccdefad4c41d797d`
- Branch: `generative-llm-validation-v1`
- Remote: `https://github.com/RAGWarrant/ragwarrant-governance.git`
- Working tree before edits: clean
- Publication validator: passed
- `pytest -q tests/publication`: 34 passed
- `make validate-publication`: passed
- `make test`: 34 passed
- `python3 -m compileall src scripts`: passed
- Large-file scan: only local `.local_data` HotpotQA cache exceeded 50 MB; it is untracked local data
- Raw text scan: expected sanitizer/test/audit references only
- Secret scan: expected scanner-pattern references only
- Private path scan: passed
- Overclaim scan: expected unsupported-claim statements only
