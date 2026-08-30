#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && /bin/pwd)"
PYTHON_BIN="${PYTHON:-python3}"
MODE="${RAGWARRANT_K8S_VALIDATION_MODE:-auto}"
REPORT_DIR="${RAGWARRANT_KIND_REPORT_DIR:-/tmp/ragwarrant-k8s-kind-validation}"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-ragwarrant-validate}"
NODE_IMAGE="${RAGWARRANT_KIND_NODE_IMAGE:-}"
TIMEOUT="${RAGWARRANT_KIND_TIMEOUT:-180s}"
IMAGE_NAME="ragwarrant-governance:kind-validation"
OVERLAY="$ROOT/deploy/kubernetes-kind-validation"
REPORT_JSON="$REPORT_DIR/k8s_kind_validation_report.json"
REPORT_MD="$REPORT_DIR/k8s_kind_validation_report.md"
RENDERED_MANIFEST="$REPORT_DIR/rendered_manifest.yaml"
POD_SPEC_JSON="$REPORT_DIR/sanitized_pod_spec.json"
JOB_STATUS_JSON="$REPORT_DIR/sanitized_job_status.json"
OUTPUT_COPY="$REPORT_DIR/job_outputs"
COPY_POD_NAME="${CLUSTER_NAME}-output-copy"
CLUSTER_CREATED=0

usage() {
  cat <<'EOF'
Usage: scripts/validate_k8s_kind.sh [--full|--dry-run] [report-dir]

Modes:
  --full     require Docker, kind, kubectl, build the runtime image, and execute the shipped Job.
  --dry-run  render and statically validate Kubernetes manifests without scheduler execution.

Environment:
  RAGWARRANT_K8S_VALIDATION_MODE=full|dry-run
  KIND_CLUSTER_NAME
  RAGWARRANT_KIND_NODE_IMAGE
  RAGWARRANT_KIND_TIMEOUT
  RAGWARRANT_KIND_REPORT_DIR
EOF
}

while (($#)); do
  case "$1" in
    --full)
      MODE="full"
      shift
      ;;
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      REPORT_DIR="$1"
      shift
      ;;
  esac
done

REPORT_JSON="$REPORT_DIR/k8s_kind_validation_report.json"
REPORT_MD="$REPORT_DIR/k8s_kind_validation_report.md"
RENDERED_MANIFEST="$REPORT_DIR/rendered_manifest.yaml"
POD_SPEC_JSON="$REPORT_DIR/sanitized_pod_spec.json"
JOB_STATUS_JSON="$REPORT_DIR/sanitized_job_status.json"
OUTPUT_COPY="$REPORT_DIR/job_outputs"

/bin/mkdir -p "$REPORT_DIR"

write_report() {
  local result_class="$1"
  local detail="${2:-}"
  "$PYTHON_BIN" - "$REPORT_JSON" "$REPORT_MD" "$result_class" "$MODE" "$detail" <<'PY'
import json
import sys
from pathlib import Path

report_json, report_md, result_class, mode, detail = sys.argv[1:]
payload = {
    "result_class": result_class,
    "mode": mode,
    "detail": detail,
    "real_cloud_deployment_performed": False,
    "scheduler_execution_performed": result_class == "K8S_KIND_EXECUTION_PASSED",
}
Path(report_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
Path(report_md).write_text(
    f"# Kubernetes Validation\n\nResult: `{result_class}`.\n\nMode: `{mode}`.\n\n{detail}\n",
    encoding="utf-8",
)
PY
}

cleanup() {
  if [[ "$CLUSTER_CREATED" == "1" ]]; then
    kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

have() {
  command -v "$1" >/dev/null 2>&1
}

require_full_tool() {
  local tool="$1"
  if ! have "$tool"; then
    write_report "K8S_KIND_FULL_VALIDATION_FAILED" "Required tool '$tool' is unavailable in explicit full mode."
    exit 1
  fi
}

render_manifests() {
  kubectl kustomize "$OVERLAY" > "$RENDERED_MANIFEST"
}

assert_rendered_security() {
  "$PYTHON_BIN" - "$RENDERED_MANIFEST" "$POD_SPEC_JSON" <<'PY'
import json
import sys
from pathlib import Path

import yaml

manifest = Path(sys.argv[1])
pod_spec_out = Path(sys.argv[2])
docs = [doc for doc in yaml.safe_load_all(manifest.read_text(encoding="utf-8")) if doc]
jobs = [doc for doc in docs if doc.get("kind") == "Job" and doc.get("metadata", {}).get("name") == "ragwarrant-governance-job"]
if len(jobs) != 1:
    raise SystemExit("expected exactly one ragwarrant-governance-job")
spec = jobs[0]["spec"]["template"]["spec"]
container = spec["containers"][0]
security = container.get("securityContext", {})
mounts = {m["mountPath"]: m for m in container.get("volumeMounts", [])}
args = container.get("args", [])
checks = {
    "runAsUser": security.get("runAsUser") == 10001,
    "runAsNonRoot": security.get("runAsNonRoot") is True,
    "readOnlyRootFilesystem": security.get("readOnlyRootFilesystem") is True,
    "allowPrivilegeEscalation": security.get("allowPrivilegeEscalation") is False,
    "capabilitiesDropAll": "ALL" in security.get("capabilities", {}).get("drop", []),
    "inputsReadOnly": mounts.get("/inputs", {}).get("readOnly") is True,
    "outputsMounted": "/outputs" in mounts and mounts.get("/outputs", {}).get("readOnly") is not True,
    "tmpMounted": "/tmp" in mounts,
    "runsGovernanceJob": "run-governance-job" in args,
    "usesPublicMiniConfig": "/inputs/public_mini_governance_job.yaml" in args,
}
if not all(checks.values()):
    raise SystemExit(json.dumps({"failed_checks": {k: v for k, v in checks.items() if not v}}, sort_keys=True))
pod_spec_out.write_text(json.dumps({"container": container, "security_checks": checks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

validate_decision() {
  "$PYTHON_BIN" - "$OUTPUT_COPY/promotion_decision.json" "$ROOT/schemas/promotion_decision.schema.json" <<'PY'
import json
import sys
from pathlib import Path

decision = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
schema = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
missing = [key for key in schema["required"] if key not in decision]
if missing:
    raise SystemExit(f"missing required decision fields: {missing}")
if decision.get("result_class") != "PUBLIC_MINI_REPRODUCTION_FAIL_CLOSED":
    raise SystemExit(f"unexpected result_class: {decision.get('result_class')}")
if decision.get("decision") != "BLOCK":
    raise SystemExit(f"unexpected decision: {decision.get('decision')}")
PY
}

copy_job_outputs_from_pvc() {
  /bin/rm -rf "$OUTPUT_COPY"
  /bin/mkdir -p "$OUTPUT_COPY"
  kubectl delete pod "$COPY_POD_NAME" --ignore-not-found=true >/dev/null
  kubectl apply -f - >/dev/null <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: ${COPY_POD_NAME}
  labels:
    app.kubernetes.io/name: ragwarrant
    app.kubernetes.io/component: output-copy
spec:
  restartPolicy: Never
  containers:
    - name: copy
      image: ${IMAGE_NAME}
      imagePullPolicy: IfNotPresent
      command: ["/bin/sh", "-c", "sleep 300"]
      volumeMounts:
        - name: outputs
          mountPath: /outputs
  volumes:
    - name: outputs
      persistentVolumeClaim:
        claimName: ragwarrant-outputs
YAML
  kubectl wait --for=condition=Ready "pod/$COPY_POD_NAME" --timeout="$TIMEOUT"
  kubectl cp "${COPY_POD_NAME}:/outputs/." "$OUTPUT_COPY"
  kubectl delete pod "$COPY_POD_NAME" --ignore-not-found=true >/dev/null
}

run_dry_run() {
  if ! have kubectl; then
    write_report "FALLBACK_KUBECTL_UNAVAILABLE" "kubectl is required to render Kustomize manifests."
    exit 0
  fi
  render_manifests
  assert_rendered_security
  write_report "K8S_KIND_STATIC_DRY_RUN_PASSED" "Rendered manifests and statically validated security context, mounts, and command contract. Scheduler execution was not performed."
}

if [[ "$MODE" == "auto" ]]; then
  if have docker && have kind && have kubectl && docker info >/dev/null 2>&1; then
    MODE="full"
  else
    MODE="dry-run"
  fi
fi

if [[ "$MODE" == "dry-run" ]]; then
  run_dry_run
  exit 0
fi

if [[ "$MODE" != "full" ]]; then
  write_report "K8S_KIND_VALIDATION_CONFIG_ERROR" "Unknown validation mode: $MODE"
  exit 2
fi

require_full_tool docker
require_full_tool kind
require_full_tool kubectl
if ! docker info >/dev/null 2>&1; then
  write_report "K8S_KIND_FULL_VALIDATION_FAILED" "Docker daemon is unavailable in explicit full mode."
  exit 1
fi

render_manifests
assert_rendered_security

docker build -t "$IMAGE_NAME" "$ROOT"
kind_args=(create cluster --name "$CLUSTER_NAME")
if [[ -n "$NODE_IMAGE" ]]; then
  kind_args+=(--image "$NODE_IMAGE")
fi
kind "${kind_args[@]}"
CLUSTER_CREATED=1
kind load docker-image "$IMAGE_NAME" --name "$CLUSTER_NAME"
kubectl apply -k "$OVERLAY"
kubectl wait --for=condition=complete "job/ragwarrant-governance-job" --timeout="$TIMEOUT"
pod_name="$(kubectl get pods -l job-name=ragwarrant-governance-job -o jsonpath='{.items[0].metadata.name}')"
kubectl get pod "$pod_name" -o json > "$JOB_STATUS_JSON"
"$PYTHON_BIN" - "$JOB_STATUS_JSON" <<'PY'
import json
import sys
from pathlib import Path

pod = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
statuses = pod.get("status", {}).get("containerStatuses", [])
if len(statuses) != 1:
    raise SystemExit("expected exactly one container status")
state = statuses[0].get("state", {}).get("terminated", {})
if state.get("exitCode") != 0:
    raise SystemExit(f"unexpected container exit code: {state.get('exitCode')}")
if state.get("reason") not in {"Completed", None}:
    raise SystemExit(f"unexpected termination reason: {state.get('reason')}")
PY
copy_job_outputs_from_pvc
test -f "$OUTPUT_COPY/promotion_decision.json"
validate_decision
if [[ -d "$OUTPUT_COPY/public_mini_reproduction" ]]; then
  PYTHONPATH="$ROOT/src" "$PYTHON_BIN" "$ROOT/scripts/verify_ragwarrant_run.py" \
    --run-dir "$OUTPUT_COPY/public_mini_reproduction" \
    --output-root "$REPORT_DIR/verify_run" >/dev/null
fi
write_report "K8S_KIND_EXECUTION_PASSED" "Executed the shipped Kubernetes Job through kind, validated pod security, retrieved promotion_decision.json, and confirmed the fail-closed public-mini result."
