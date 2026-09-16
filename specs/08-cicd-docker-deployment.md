# Spec 08: Production Containerization & CI/CD Pipeline

## 1. Goal & Scope
Package the entire multi-service system for reproducible deployment and set up automated quality gates:
- **Container Orchestration**: Multi-container Docker Compose setup managing FastAPI backend, React frontend (or static build served via Nginx), Qdrant vector database, and Neo4j graph database.
- **Production Dockerfiles**: Multi-stage builds for both backend (Python slim) and frontend (Node build -> Nginx static serving).
- **Automated CI/CD Workflow**: GitHub Actions pipeline executing code linting, static type verification, full pytest suite runs, and container build checks on every pull request to `main`.

## 2. Target File Tree
- `Dockerfile`                     # Multi-stage container build for FastAPI backend
- `frontend/Dockerfile`            # Multi-stage build for React frontend (Vite build + Nginx)
- `frontend/nginx.conf`            # Nginx proxy configuration routing /api to backend
- `docker-compose.yml`             # Full stack orchestrator (App, Frontend, Neo4j, Qdrant)
- `.dockerignore`                  # Prevent virtualenvs, logs, and node_modules in build context
- `.github/workflows/ci.yml`       # Automated GitHub Actions test, lint, and build pipeline
- `scripts/healthcheck.sh`         # Shell verification script to validate running containers

## 3. Configuration Specifications

### Docker Services Architecture
- **backend**:
  - Build context: root directory (`Dockerfile`).
  - Environment: `QDRANT_URL=http://qdrant:6333`, `NEO4J_URI=bolt://neo4j:7687`, `NEO4J_USER=neo4j`, `NEO4J_PASSWORD=production_password`.
  - Depends on: `neo4j` (healthy), `qdrant` (healthy).
  - Port: `8000:8000`.
- **frontend**:
  - Build context: `./frontend` (`frontend/Dockerfile`).
  - Port: `3000:80` (or `80:80`).
  - Depends on: `backend`.
- **qdrant**:
  - Image: `qdrant/qdrant:latest`.
  - Port: `6333:6333`.
  - Volumes: `qdrant_storage:/qdrant/storage`.
- **neo4j**:
  - Image: `neo4j:5.20.0-enterprise` (or community `neo4j:5.20.0`).
  - Environment: `NEO4J_AUTH=neo4j/production_password`, `NEO4J_PLUGINS=["apoc"]`.
  - Ports: `7474:7474` (HTTP browser), `7687:7687` (Bolt binary).
  - Volumes: `neo4j_data:/data`.

### GitHub Actions Pipeline (`.github/workflows/ci.yml`)
- Trigger: `push` and `pull_request` against `main` or `master`.
- Jobs:
  1. **lint-and-test**:
     - Python setup (3.11 or 3.12).
     - Dependency caching via `actions/cache`.
     - Install requirements (`pip install -r requirements.txt`).
     - Run linter: `ruff check .` (or `flake8`).
     - Run full automated test suite: `pytest -v`.
  2. **build-check**:
     - Runs after test job passes.
     - Builds Docker containers using `docker compose build` to verify clean builds without image push.

## 4. Implementation Requirements
1. **Root `Dockerfile`**:
   - Base: `python:3.11-slim`.
   - Install minimal OS runtime packages, copy `requirements.txt`, install wheels with `--no-cache-dir`.
   - Copy `src/` and necessary assets.
   - Run as a non-root user (`appuser`).
   - Expose port 8000; entrypoint: `uvicorn src.api.server:app --host 0.0.0.0 --port 8000`.

2. **Frontend `frontend/Dockerfile`**:
   - Stage 1 (`build`): `node:20-alpine`, install npm packages, run `npm run build`.
   - Stage 2 (`serve`): `nginx:alpine`, copy built artifacts from Stage 1 to `/usr/share/nginx/html`.
   - Copy custom `nginx.conf` forwarding `/api/` traffic to `http://backend:8000/`.

3. **`docker-compose.yml`**:
   - Define named volumes for `neo4j_data` and `qdrant_storage`.
   - Include proper health checks for `neo4j` (using `cypher-shell`) and `qdrant` (using `/readyz` endpoint) to enforce startup order.

## 5. Constraints
- The backend image must stay lightweight (under 600MB uncompressed if using CPU-only torch/transformers wheels).
- All secrets in `docker-compose.yml` must support `.env` substitution fallbacks.

## 6. Acceptance Criteria
1. `docker compose config` evaluates without syntax or structural errors.
2. The GitHub Actions YAML passes lint validation.
3. Running `pytest` continues to pass across all prior test modules (Specs 01-07).