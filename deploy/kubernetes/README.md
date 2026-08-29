# Kubernetes

These examples run RAGWarrant as a finite Kubernetes Job or CronJob. Replace placeholder image and storage values before use.

```bash
kubectl apply -k deploy/kubernetes
```

The examples do not include raw datasets or credentials. Mount approved data separately when a job requires it.

## Validation

Static validation renders the validation overlay and checks the shipped Job security context, volume mounts, and command contract without claiming scheduler execution:

```bash
scripts/validate_k8s_kind.sh --dry-run
```

Executed validation requires Docker, kind, and kubectl. It builds the local runtime image, creates a disposable kind cluster, loads the image, runs the shipped `ragwarrant-governance-job`, retrieves `promotion_decision.json`, validates the fail-closed public-mini result, and deletes the cluster through a trap:

```bash
scripts/validate_k8s_kind.sh --full
```

The validation-only overlay is under `deploy/kubernetes-kind-validation/`. It is not the default production example and does not perform a real cloud deployment.
