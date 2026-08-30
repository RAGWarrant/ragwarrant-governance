# Platform Benchmarking Boundary

Local or hosted generative validation is not official platform benchmarking.

This repository distinguishes:

- local generative validation: a locally served model produces answers under a pinned model identifier;
- hosted-model generative validation: a hosted API produces answers under a pinned model identifier;
- official platform benchmarking: platform-native evaluation services run and produce platform-native artifacts.

The current generative validation uses local Ollama for HotpotQA. It is not an official LangSmith, Ragas, DeepEval, RAGChecker, Azure, AWS, GCP, or OpenAI platform benchmark.

Human validation and production validation also remain separate unsupported claims unless real annotations or production evidence are added.
## AIM Hardware Characterization Boundary

The AIM hardware characterization is local runtime documentation only. It is not an official platform benchmark, not a cloud benchmark, and not evidence of production readiness.

## Cloud Deployment Templates

The Docker, Kubernetes, Azure, AWS, GCP, and GitHub Actions files in `deploy/` are portability templates for the finite RAGWarrant governance job. They are not platform-native benchmark artifacts and do not imply live cloud validation.
