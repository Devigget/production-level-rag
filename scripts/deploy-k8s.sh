#!/usr/bin/env bash
# ==============================================================================
# Production RAG Kubernetes Deployment Script
# ==============================================================================
set -euo pipefail

NAMESPACE="rag-system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Deploying Production RAG Stack to Kubernetes ==="
echo "Target Namespace: ${NAMESPACE}"

# 1. Verify kubectl CLI
if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl is not installed or not in PATH." >&2
    exit 1
fi

# 2. Create namespace if not present
echo "--> Ensuring namespace '${NAMESPACE}' exists..."
kubectl apply -f "${ROOT_DIR}/k8s/00-namespace.yaml"

# 3. Create secrets from .env if present and rag-secrets doesn't exist
if [ -f "${ROOT_DIR}/.env" ] && ! kubectl get secret rag-secrets -n "${NAMESPACE}" &> /dev/null; then
    echo "--> Populating '${NAMESPACE}/rag-secrets' from local .env file..."
    # Extract keys safely
    NEO4J_PW=$(grep -E '^NEO4J_PASSWORD=' "${ROOT_DIR}/.env" | cut -d '=' -f2- | tr -d '\r"' || echo "production_password")
    GROQ_KEY=$(grep -E '^GROQ_API_KEY=' "${ROOT_DIR}/.env" | cut -d '=' -f2- | tr -d '\r"' || echo "")
    GEMINI_KEY=$(grep -E '^GEMINI_API_KEY=' "${ROOT_DIR}/.env" | cut -d '=' -f2- | tr -d '\r"' || echo "")
    NVIDIA_KEY=$(grep -E '^NVIDIA_API_KEY=' "${ROOT_DIR}/.env" | cut -d '=' -f2- | tr -d '\r"' || echo "")
    HF_TOK=$(grep -E '^HF_TOKEN=' "${ROOT_DIR}/.env" | cut -d '=' -f2- | tr -d '\r"' || echo "")
    LF_PUB=$(grep -E '^LANGFUSE_PUBLIC_KEY=' "${ROOT_DIR}/.env" | cut -d '=' -f2- | tr -d '\r"' || echo "")
    LF_SEC=$(grep -E '^LANGFUSE_SECRET_KEY=' "${ROOT_DIR}/.env" | cut -d '=' -f2- | tr -d '\r"' || echo "")

    kubectl create secret generic rag-secrets \
        --namespace="${NAMESPACE}" \
        --from-literal=NEO4J_PASSWORD="${NEO4J_PW}" \
        --from-literal=GROQ_API_KEY="${GROQ_KEY}" \
        --from-literal=GEMINI_API_KEY="${GEMINI_KEY}" \
        --from-literal=NVIDIA_API_KEY="${NVIDIA_KEY}" \
        --from-literal=HF_TOKEN="${HF_TOK}" \
        --from-literal=LANGFUSE_PUBLIC_KEY="${LF_PUB}" \
        --from-literal=LANGFUSE_SECRET_KEY="${LF_SEC}" \
        --dry-run=client -o yaml | kubectl apply -f -
fi

# 4. Apply all manifests via Kustomize
echo "--> Applying declarative manifests via Kustomize..."
kubectl apply -k "${ROOT_DIR}/k8s"

# 5. Monitor rollout progress
echo "--> Awaiting database availability..."
kubectl rollout status deployment/qdrant -n "${NAMESPACE}" --timeout=120s
kubectl rollout status statefulset/neo4j -n "${NAMESPACE}" --timeout=180s

echo "--> Awaiting application rollout..."
kubectl rollout status deployment/backend -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/frontend -n "${NAMESPACE}" --timeout=120s

echo "=== Deployment Completed Successfully! ==="
echo ""
echo "Pod Status:"
kubectl get pods -n "${NAMESPACE}"
echo ""
echo "Service Endpoints:"
kubectl get svc -n "${NAMESPACE}"
echo ""
echo "Ingress:"
kubectl get ingress -n "${NAMESPACE}"
echo ""
echo "Access Options:"
echo "1. Ingress (requires ingress controller): http://rag.local (add to /etc/hosts)"
echo "2. Port Forward Frontend:  kubectl port-forward svc/frontend -n ${NAMESPACE} 3000:80"
echo "3. Port Forward Backend:   kubectl port-forward svc/backend -n ${NAMESPACE} 8000:8000"
echo "4. Port Forward Grafana:   kubectl port-forward svc/grafana -n ${NAMESPACE} 3001:3000"
