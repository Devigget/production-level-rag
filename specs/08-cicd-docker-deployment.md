# Spec 08: Production Containerization, Kubernetes Orchestration & CI/CD Pipeline

## 1. Goal & Scope
Package the multi-service system for reproducible, isolated deployment and establish automated CI/CD quality gates across both Docker Compose and Kubernetes environments:
- **Kubernetes Enterprise Orchestration (`k8s/`)**:
  - Declarative orchestration across the dedicated `rag-system` namespace.
  - 8 production microservices (10 total pods):
    1. `backend`: Scalable FastAPI application (2 replicas) with rolling updates, startup/liveness/readiness probes, and shared persistent storage.
    2. `frontend`: High-availability React SPA (2 replicas) served via Nginx.
    3. `qdrant`: Vector database Deployment with dedicated 10Gi PersistentVolumeClaim (`qdrant-pvc`).
    4. `neo4j`: StatefulSet (`neo4j-0`) with APOC plugins, disabled strict validation, `enableServiceLinks: false`, and dedicated 10Gi PVC (`neo4j-pvc`).
    5. `otel-collector`: OpenTelemetry Collector receiving OTLP spans and metrics, routing traces to Tempo and metrics to Prometheus.
    6. `prometheus`: Prometheus TSDB scraping backend `/metrics` and collector metrics with SLO alert rules (`alerts.yml`).
    7. `tempo`: High-volume distributed trace storage with local block persistence.
    8. `grafana`: Pre-provisioned dashboards (`Financial RAG Showcase`, `Financial RAG Reliability`), auto-configured datasources (Infinity, Prometheus, Tempo), and `yesoreyeram-infinity-datasource` plugin.
  - **Cluster Networking & Ingress (`08-ingress.yaml`)**:
    - Nginx Ingress routing `/api`, `/healthz`, and `/metrics` to `backend:8000`, and `/` to `frontend:80`.
    - SSE streaming support (`nginx.ingress.kubernetes.io/proxy-buffering: "off"`), 50MB file uploads, and 300s timeouts.
  - **Zero-Downtime Deployments**: `RollingUpdate` with `maxSurge: 1` and `maxUnavailable: 0`.
- **Multi-Service Docker Compose Orchestration (`docker-compose.yml`)**:
  - Local multi-container development environment matching production network topologies.
- **Production Dockerfiles**:
  - `Dockerfile` (Backend): Multi-stage Python 3.11-slim container with Tesseract OCR OS libraries, pre-warmed HuggingFace model cache, and non-root execution (`appuser`).
  - `frontend/Dockerfile`: Multi-stage build (`node:20-alpine` build -> `nginx:alpine` static serving with `/api/` reverse proxy).
- **Automated CI/CD & Deployment Pipelines**:
  - **GitHub Actions (`.github/workflows/ci.yml`)**: Automated pull request testing, linting (`ruff`), and container validation on pushes to `main`.
  - **Jenkins Production Pipeline (`Jenkinsfile`)**: Declarative enterprise CI/CD pipeline executing `lint/test` → `build images` → `push to registry` → `deploy` with automated healthcheck verification.
  - **Kubernetes Automation Scripts**:
    - `scripts/deploy-k8s.ps1` & `scripts/deploy-k8s.sh`: One-command declarative deployment using Kustomize with secret generation and rollout monitoring.
    - `scripts/test-k8s.ps1`: Automated 5-tier Kubernetes smoke test suite.

## 2. Target File Tree
- `Dockerfile`                     # Multi-stage container build for FastAPI backend
- `frontend/Dockerfile`            # Multi-stage build for React frontend (Vite build + Nginx)
- `frontend/nginx.conf`            # Nginx proxy configuration routing /api to backend
- `docker-compose.yml`             # Full 8-service local stack orchestrator with named volumes
- `k8s/`                           # Production Kubernetes manifests directory
  - `00-namespace.yaml`            # Dedicated 'rag-system' namespace
  - `01-configmap.yaml`            # Non-sensitive runtime environment variables (`rag-config`)
  - `02-secrets.yaml`              # Production secret definitions (`rag-secrets`)
  - `03-storage.yaml`              # PersistentVolumeClaims for Neo4j, Qdrant, backend data
  - `04-qdrant.yaml`               # Qdrant Vector DB Deployment & Service
  - `05-neo4j.yaml`                # Neo4j Graph DB StatefulSet & Service (`enableServiceLinks: false`)
  - `06-backend.yaml`              # FastAPI Backend Deployment (2 replicas) with health probes
  - `07-frontend.yaml`             # React Frontend Deployment (2 replicas) & Service
  - `08-ingress.yaml`              # Nginx Ingress with SSE streaming & 50MB upload support
  - `09-observability.yaml`        # OTel Collector, Tempo, Prometheus, and Grafana with dashboards
  - `kustomization.yaml`           # Kustomize orchestration manifest with common labels
- `scripts/deploy-k8s.ps1`         # PowerShell automated Kubernetes deployment script
- `scripts/deploy-k8s.sh`          # Bash automated Kubernetes deployment script
- `scripts/test-k8s.ps1`           # PowerShell automated Kubernetes 5-phase smoke test script
- `scripts/healthcheck.sh`         # Verification script to validate container endpoints
- `Jenkinsfile`                    # Declarative multi-stage Jenkins CI/CD pipeline
- `.github/workflows/ci.yml`       # Automated GitHub Actions test, lint, and build pipeline

## 3. Configuration Specifications

### 3.1. Kubernetes Orchestration Architecture
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
            PodOTel -->|OTLP gRPC :4317| SvcTempo[tempo Service]
            SvcTempo --> PodTempo[tempo-pod]
            PodOTel -->|Metrics Exporter :8889| SvcProm[prometheus Service]
            SvcProm --> PodProm[prometheus-pod]
            PodGrafana[grafana-pod] --> SvcProm
            PodGrafana --> SvcTempo
            PodGrafana --> SvcBackend
        end
    end
```

### 3.2. Workload Specifications Table

| Service | Type | Replicas | Ports | Storage / Mounts | Probes / Notes |
|---|---|---|---|---|---|
| `backend` | Deployment | 2 | 8000 | `backend-data-pvc` (5Gi) at `/app/data` | Startup, Liveness, Readiness on `/healthz/*` |
| `frontend` | Deployment | 2 | 80 | None (Stateless React SPA) | HTTP GET `/` on port 80 |
| `qdrant` | Deployment | 1 | 6333, 6334 | `qdrant-pvc` (10Gi) at `/qdrant/storage` | Readiness on `/readyz` |
| `neo4j` | StatefulSet | 1 | 7474, 7687 | `neo4j-pvc` (10Gi) at `/data` | `enableServiceLinks: false`, Cypher check |
| `otel-collector`| Deployment | 1 | 4317, 4318, 8889 | ConfigMap mounted to `/etc/otelcol-contrib` | Pipelines: Metrics -> Prom, Traces -> Tempo |
| `prometheus` | Deployment | 1 | 9090 | ConfigMap mounted to `/etc/prometheus` | Readiness on `/-/ready`, evaluates alerts |
| `tempo` | Deployment | 1 | 3200, 4317 | `emptyDir` at `/var/tempo` | Readiness on `/ready` |
| `grafana` | Deployment | 1 | 3000 | ConfigMaps: datasources, providers, dashboards | Auto-provisions Infinity, Prometheus, Tempo |

### 3.3. Neo4j StatefulSet Specialization (`05-neo4j.yaml`)
To prevent environment variable collision between Kubernetes service link injection and Neo4j 5.x configuration parsing:
```yaml
spec:
  template:
    spec:
      enableServiceLinks: false  # Disables NEO4J_PORT_7687_TCP_PORT collision
      containers:
        - name: neo4j
          env:
            - name: NEO4J_server_config_strict__validation_enabled
              value: "false"
```

### 3.4. Root Dockerfile Specifications
```dockerfile
FROM python:3.11-slim AS runtime

# Install system dependencies including Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install wheels
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root app user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser . .

EXPOSE 8000
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.5. Frontend Dockerfile Specifications
```dockerfile
# Stage 1: Build static bundle
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve via Nginx
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 3.6. Jenkins Production CI/CD Pipeline (`Jenkinsfile`)
Declarative multi-stage pipeline designed for production continuous delivery with quality gates and zero-downtime rolling service updates:

- **Pipeline Stages**:
  1. `Lint & Test`:
     - **Backend**: Runs inside virtualenv; executes `ruff check .` and isolated `pytest -v tests/`. Mocks external databases with `TESTING=true`, `QDRANT_URL=":memory:"`, and `NEO4J_URI="bolt://mock:7687"` to avoid live service coupling.
     - **Frontend**: Runs `npm ci` and `npm run build` validating production JavaScript bundles and TypeScript type safety.
  2. `Build Images`:
     - Multi-stage Docker builds generating `rag-backend` and `rag-frontend` images tagged with `${BUILD_NUMBER}-${GIT_COMMIT}` and `latest`.
     - Excludes large HuggingFace model caches and LLM binaries to keep containers lightweight and portable.
  3. `Push to Registry`:
     - Authenticates to Docker Hub using Jenkins credentials (`docker-registry-credentials`).
     - Pushes versioned tags and `latest` for both backend and frontend images to the container registry.
  4. `Deploy`:
     - Injects production environment secrets dynamically via Jenkins Secret File (`rag-production-env`) without exposing secrets on disk.
     - Deploys updated application services via `docker compose -p productionlevelrag up -d --no-deps backend frontend` or `kubectl set image`.
     - Preserves stateful services (`neo4j`, `qdrant`, `prometheus`, `tempo`, `grafana`) and persistent named volumes (`backend_data`, `neo4j_data`, `qdrant_storage`).
     - Automatically verifies deployment health via HTTP 200 checks on `/healthz/live`.
  5. `Post Actions`:
     - Prunes dangling Docker images (`docker image prune -f`) to conserve disk space.
     - Emits success/failure notifications.

## 4. Verification & Acceptance Criteria
1. `kubectl apply -k k8s/` provisions all 10 pods, 8 services, 3 PVCs, and Ingress with 0 errors.
2. `powershell -ExecutionPolicy Bypass -File scripts\test-k8s.ps1` executes and passes all 5 verification phases:
   - Pod and Service status verification in `rag-system`.
   - Backend `/healthz/live` and `/healthz/ready` connectivity to Qdrant and Neo4j.
   - Store catalog and multi-pod file synchronization.
   - Live end-to-end SSE streaming query generation with numerical fidelity and citations.
   - Frontend and Grafana observability reachability.
3. Pod termination resilience test (`kubectl delete pod <pod-name> -n rag-system`) proves automatic self-healing within 5 seconds without user service disruption.
4. Cluster service load balancing distributes HTTP requests evenly across both backend pod replicas.
5. Jenkins declarative pipeline (`Jenkinsfile`) executes end-to-end passing all quality gates.