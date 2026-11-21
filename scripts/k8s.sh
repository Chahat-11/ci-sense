#!/usr/bin/env bash
# Run CI-Sense on a local Kubernetes cluster (kind). Needs Docker Desktop running.
#   scripts/k8s.sh up      build images, create cluster, deploy
#   scripts/k8s.sh open    port-forward the UI to http://localhost:8080
#   scripts/k8s.sh down    delete the cluster
set -euo pipefail
cd "$(dirname "$0")/.."
CLUSTER=ci-sense

case "${1:-up}" in
  up)
    docker info >/dev/null 2>&1 || { echo "Docker isn't running. Open Docker Desktop first."; exit 1; }
    [ -f .env ] || { echo "Missing .env (copy .env.example and fill it in)."; exit 1; }
    kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER"
    docker build -t ci-sense-api:latest .
    docker build -t ci-sense-web:latest web
    kind load docker-image ci-sense-api:latest ci-sense-web:latest --name "$CLUSTER"
    # Parse .env the same way the app does (quotes and spaces stripped); kubectl's own parser keeps them.
    python3 - <<'PY' | kubectl apply -f -
import subprocess
from dotenv import dotenv_values
vals = {k: v.strip() for k, v in dotenv_values(".env").items() if v and v.strip()}
args = ["kubectl", "create", "secret", "generic", "ci-sense-env", "--dry-run=client", "-o", "yaml"]
args += [f"--from-literal={k}={v}" for k, v in vals.items()]
print(subprocess.run(args, check=True, capture_output=True, text=True).stdout)
PY
    kubectl apply -k k8s
    kubectl rollout restart deployment/ci-sense-api deployment/ci-sense-web
    kubectl rollout status deployment/ci-sense-api deployment/ci-sense-web --timeout=120s
    echo; echo "Deployed. Run: scripts/k8s.sh open"
    ;;
  open)
    echo "UI on http://localhost:8080 (Ctrl+C to stop)"
    kubectl port-forward svc/ci-sense-web 8080:80
    ;;
  down)
    kind delete cluster --name "$CLUSTER"
    ;;
  *) echo "usage: $0 up|open|down"; exit 1 ;;
esac
