# Kubernetes Orchestration Guide: Production-Level RAG

This document provides a comprehensive guide for deploying, configuring, and managing the containerized **Production-Level Financial RAG** system on Kubernetes.

---

## 1. Architectural Overview

The Kubernetes deployment orchestrates all microservices into the dedicated `rag-system` namespace, isolating compute, storage, configuration, and traffic routing.

```mermaid
graph TD
    Client([User Browser]) -->|HTTP / HTTPS| Ingress[rag-ingress: Nginx Ingress]
    
    subgraph "Kubernetes Cluster: rag-system namespace"
        Ingress -->|/api/*, /healthz, /metrics| SvcBackend[backend Service :8000]
        Ingress -->|/* (Static Assets)| SvcFrontend[frontend Service :80]

        subgraph "Application Tier (Stateless / Scalable)"
            SvcFrontend --> PodFrontend1[frontend-pod-1]
            SvcFrontend --> PodFrontend2[frontend-pod-2]

            SvcBackend --> PodBackend1[backend-pod-1]
            SvcBackend --> PodBackend2[backend-pod-2]
        end

        subgraph "Configuration & Secrets"
            ConfigMap[ConfigMap: rag-config] -.->|envFrom| PodBackend1
            ConfigMap -.->|envFrom| PodBackend2
            Secret[Secret: rag-secrets] -.->|envFrom| PodBackend1
            Secret -.->|envFrom| PodBackend2
            Secret -.->|auth| PodNeo4j[neo4j-0 StatefulSet]
        end

        subgraph "Storage & Databases (Stateful)"
            PodBackend1 -->|gRPC / HTTP :6333| SvcQdrant[qdrant Service]
            PodBackend2 -->|gRPC / HTTP :6333| SvcQdrant
            SvcQdrant --> PodQdrant[qdrant-pod]
            PodQdrant --- PVCQdrant[(qdrant-pvc: 10Gi)]

            PodBackend1 -->|Bolt :7687| SvcNeo4j[neo4j Service]
            PodBackend2 -->|Bolt :7687| SvcNeo4j
            SvcNeo4j --> PodNeo4j
            PodNeo4j --- PVCNeo4j[(neo4j-pvc: 10Gi)]

            PodBackend1 --- PVCBackend[(backend-data-pvc: 5Gi)]
            PodBackend2 --- PVCBackend
        end

        subgraph "Telemetry & Observability Tier"
            PodBackend1 -->|OTLP gRPC :4317| SvcOTel[otel-collector Service]
            PodBackend2 -->|OTLP gRPC :4317| SvcOTel
            SvcOTel --> PodOTel[otel-collector-pod]
            PodOTel -->|Prometheus Exporter :8889| SvcProm[prometheus Service]
            SvcProm --> PodProm[prometheus-pod]
            SvcProm --> PodGrafana[grafana-pod]
        end
    end
```

---

## 2. Manifest Directory Structure

All Kubernetes resources are located in the [`k8s/`](file:///k8s/) directory:

```text
k8s/
├── 00-namespace.yaml          # Isolated 'rag-system' namespace
├── 01-configmap.yaml          # Non-sensitive runtime environment variables
├── 02-secrets.yaml            # Sensitive API keys and database credentials template
├── 03-storage.yaml            # PersistentVolumeClaims (PVC) for Neo4j, Qdrant, backend
├── 04-qdrant.yaml             # Qdrant Vector DB Deployment & ClusterIP Service
├── 05-neo4j.yaml              # Neo4j Graph DB StatefulSet & ClusterIP Service
├── 06-backend.yaml            # FastAPI Backend Deployment (2 replicas) & Service
├── 07-frontend.yaml           # React Nginx Frontend Deployment (2 replicas) & Service
├── 08-ingress.yaml            # Nginx Ingress with SSE streaming & 50MB upload support
├── 09-observability.yaml      # OpenTelemetry Collector, Prometheus, and Grafana
├── kustomization.yaml         # Declarative Kustomize orchestration manifest
└── secrets.example.yaml       # Example secret definitions and CLI commands
```

---

## 3. Core Component Specifications

### 3.1. ConfigMap & Secrets Separation
- **`rag-config` ([`01-configmap.yaml`](file:///k8s/01-configmap.yaml))**:
  - Vector & Graph database endpoints (`http://qdrant:6333`, `bolt://neo4j:7687`)
  - LLM providers & default models (`groq`, `gemini-2.5-flash`, `openai/gpt-oss-120b`, `google/gemma-4-31b-it`)
  - Reranker configuration (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
  - OpenTelemetry telemetry endpoint (`http://otel-collector:4317`)
  - Langfuse environment tag (`production`)
- **`rag-secrets` ([`02-secrets.yaml`](file:///k8s/02-secrets.yaml))**:
  - `NEO4J_PASSWORD`
  - `GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `HF_TOKEN`
  - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`

### 3.2. Workloads & High Availability
- **Backend Deployment ([`06-backend.yaml`](file:///k8s/06-backend.yaml))**:
  - Scaled across **2 replicas** with a zero-downtime `RollingUpdate` strategy (`maxSurge: 1`, `maxUnavailable: 0`).
  - Tri-probe health checking:
    - **Startup Probe**: Tolerates model cache initialization up to 150 seconds (`/healthz/live`).
    - **Liveness Probe**: Monitors process responsiveness every 15s (`/healthz/live`).
    - **Readiness Probe**: Queries active dependencies (Qdrant & Neo4j) every 10s (`/healthz/ready`).
  - Resource requests: `500m CPU / 1Gi RAM`, limits: `2000m CPU / 2Gi RAM`.
- **Frontend Deployment ([`07-frontend.yaml`](file:///k8s/07-frontend.yaml))**:
  - Scaled across **2 replicas** with Nginx serving static bundle and fallback routes.
  - Liveness & readiness probes checking root HTTP status 200.

### 3.3. Persistent Storage
- **`neo4j-pvc`**: 10Gi volume storing the property graph, Cypher blueprints, and entity links.
- **`qdrant-pvc`**: 10Gi volume storing HNSW vector embeddings and payload indices.
- **`backend-data-pvc`**: 5Gi volume storing store registries (`data/stores_registry.json`) and uploaded datasets.

### 3.4. Ingress Routing & Financial RAG Specializations ([`08-ingress.yaml`](file:///k8s/08-ingress.yaml))
- **File Upload Support**: `nginx.ingress.kubernetes.io/proxy-body-size: "50m"` enables uploading multi-megabyte 10-K PDFs and multi-sheet financial Excel workbooks without HTTP 413 errors.
- **Real-Time Token Streaming**: `nginx.ingress.kubernetes.io/proxy-buffering: "off"` ensures Server-Sent Events (SSE) from `/api/chat/stream` stream immediately to the UI without chunk buffering delays.
- **Generation Timeouts**: `proxy-read-timeout: "300"` accommodates multi-hop entity expansion and cross-encoder reranking latency.

---

## 4. Deployment Instructions

### Prerequisites
- A functional Kubernetes cluster (Docker Desktop Kubernetes, Minikube, Kind, or Cloud EKS/GKE/AKS).
- `kubectl` CLI installed and configured.
- (Optional) Nginx Ingress Controller installed:
  ```bash
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.0/deploy/static/provider/cloud/deploy.yaml
  ```

### Method 1: Automated Script (Recommended)

#### On Windows (PowerShell):
```powershell
.\scripts\deploy-k8s.ps1
```

#### On Linux / macOS / Git Bash:
```bash
chmod +x ./scripts/deploy-k8s.sh
./scripts/deploy-k8s.sh
```

The script automatically:
1. Creates the `rag-system` namespace.
2. Imports secrets from your local `.env` file into `rag-secrets`.
3. Applies all manifests via Kustomize (`kubectl apply -k k8s/`).
4. Awaits database readiness and application pod rollout status.

---

### Method 2: Manual Step-by-Step Deployment

#### Step 1: Create Namespace
```bash
kubectl apply -f k8s/00-namespace.yaml
```

#### Step 2: Configure Secrets
Create the secret from your existing `.env` file:
```bash
kubectl create secret generic rag-secrets \
  --namespace=rag-system \
  --from-literal=NEO4J_PASSWORD="production_password" \
  --from-literal=GROQ_API_KEY="gsk_..." \
  --from-literal=GEMINI_API_KEY="AIza..." \
  --from-literal=NVIDIA_API_KEY="nvapi-..." \
  --from-literal=LANGFUSE_PUBLIC_KEY="pk-lf-..." \
  --from-literal=LANGFUSE_SECRET_KEY="sk-lf-..." \
  --from-literal=HF_TOKEN="hf_..."
```
*(Or edit `k8s/02-secrets.yaml` and run `kubectl apply -f k8s/02-secrets.yaml`)*

#### Step 3: Apply All Manifests via Kustomize
```bash
kubectl apply -k k8s/
```

#### Step 4: Verify Rollout Status
```bash
# Verify database services
kubectl rollout status deployment/qdrant -n rag-system
kubectl rollout status statefulset/neo4j -n rag-system

# Verify backend & frontend pods
kubectl rollout status deployment/backend -n rag-system
kubectl rollout status deployment/frontend -n rag-system
```

---

## 5. Accessing the Application

### Option A: Ingress (Domain Host)
1. Add `rag.local` to your local hosts file:
   - **Windows**: `C:\Windows\System32\drivers\etc\hosts`
   - **Linux / macOS**: `/etc/hosts`
   ```text
   127.0.0.1  rag.local
   ```
2. Navigate to `http://rag.local` in your browser.

### Option B: Port Forwarding (Direct Cluster Access)
If an Ingress controller is not installed, port-forward the services:

```bash
# Frontend UI (Port 3000)
kubectl port-forward svc/frontend -n rag-system 3000:80

# Backend API & Docs (Port 8000)
kubectl port-forward svc/backend -n rag-system 8000:8000

# Grafana Dashboards (Port 3001)
kubectl port-forward svc/grafana -n rag-system 3001:3000

# Neo4j Browser (Port 7474)
kubectl port-forward svc/neo4j -n rag-system 7474:7474
```

---

## 6. Operational & Day-2 Management

### Scaling Pods Horizontally
```bash
# Scale backend to 5 replicas during high traffic
kubectl scale deployment/backend -n rag-system --replicas=5

# Enable Horizontal Pod Autoscaling (HPA)
kubectl autoscale deployment backend -n rag-system --cpu-percent=75 --min=2 --max=10
```

### Inspecting Pod Logs
```bash
# Stream backend logs
kubectl logs -n rag-system -l app=backend -f --tail=100

# Stream Qdrant vector DB logs
kubectl logs -n rag-system -l app=qdrant -f

# Stream Neo4j graph DB logs
kubectl logs -n rag-system statefulset/neo4j -f
```

### Zero-Downtime Rolling Update
When a new container image is pushed to Docker Hub:
```bash
# Update backend image
kubectl set image deployment/backend backend=vgmclaren/rag-backend:1.1.0 -n rag-system

# Monitor zero-downtime rollout
kubectl rollout status deployment/backend -n rag-system

# Rollback if an issue is detected
kubectl rollout undo deployment/backend -n rag-system
```

---

## 7. CI/CD Integration (Jenkins & GitHub Actions)

In your automated delivery pipeline, add a Kubernetes deployment stage after image push:

```groovy
stage('Deploy to Kubernetes') {
    steps {
        sh '''
            kubectl set image deployment/backend backend=${BACKEND_IMAGE}:${imageTag} -n rag-system
            kubectl set image deployment/frontend frontend=${FRONTEND_IMAGE}:${imageTag} -n rag-system
            kubectl rollout status deployment/backend -n rag-system --timeout=180s
            kubectl rollout status deployment/frontend -n rag-system --timeout=180s
        '''
    }
}
```
