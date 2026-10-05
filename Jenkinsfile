pipeline {
    agent any

    environment {
        // --- 1. REGISTRY & IMAGE METADATA ---
        REGISTRY = 'docker.io'
        REGISTRY_USER = 'vgmclaren'  // <-- Change to your Docker Hub username
        BACKEND_IMAGE = "${REGISTRY_USER}/rag-backend"
        FRONTEND_IMAGE = "${REGISTRY_USER}/rag-frontend"
        K8S_NAMESPACE = 'rag-system'
        COMPOSE_PROJECT_NAME = 'productionlevelrag'

        // --- 2. CREDENTIAL IDENTIFIERS ---
        REGISTRY_CREDS_ID = 'docker-registry-credentials'
        PROD_ENV_SECRET_ID = 'rag-production-env'

        // --- 3. MODEL HOST PATHS (Keeps heavy models OUT of Docker images) ---
        LOCAL_LLM_HOST_PATH = "C:/Users/VigneshPandurangGaun/OneDrive - McLaren Strategic Solutions US Inc/Documents/models/llm/Qwen2.5-1.5B-Instruct"
        RERANKER_HOST_MODEL_PATH = "C:/Users/VigneshPandurangGaun/OneDrive - McLaren Strategic Solutions US Inc/Documents/models/Reranker models"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        // ==========================================
        // STAGE 1: LINT & TEST (Isolated with Mocks)
        // ==========================================
        stage('Lint & Test') {
            environment {
                // Mocked environment variables so tests don't attempt live DB connections
                TESTING = "true"
                PYTHONPATH = "."
                NEO4J_URI = "bolt://mock:7687"
                NEO4J_USER = "neo4j"
                NEO4J_PASSWORD = "mock_password"
                QDRANT_URL = ":memory:"
                GROQ_API_KEY = "mock-key"
                GEMINI_API_KEY = "mock-key"
                RERANKER_ENABLED = "false"
            }
            parallel {
                stage('Backend: Lint & Pytest') {
                    steps {
                        sh '''
                            python3 -m venv .venv
                            . .venv/bin/activate
                            pip install --upgrade pip
                            pip install -r requirements.txt ruff pytest pytest-mock
                            
                            # 1. Syntax & Style Linting
                            ruff check .
                            
                            # 2. Run automated test suite (uses in-memory Qdrant & mocks)
                            pytest -v tests/
                        '''
                    }
                }
                stage('Frontend: Build Validation') {
                    steps {
                        dir('frontend') {
                            sh '''
                                npm ci || npm install
                                npm run build
                            '''
                        }
                    }
                }
            }
        }

        // ==========================================
        // STAGE 2: BUILD IMAGES
        // ==========================================
        stage('Build Images') {
            steps {
                script {
                    def commitSha = env.GIT_COMMIT ? env.GIT_COMMIT.take(7) : "latest"
                    def imageTag = "${env.BUILD_NUMBER}-${commitSha}"

                    echo "Building lightweight backend image..."
                    sh """
                        docker build \
                            -t ${BACKEND_IMAGE}:${imageTag} \
                            -t ${BACKEND_IMAGE}:latest \
                            -t productionlevelrag-backend:latest \
                            -f Dockerfile .
                    """

                    echo "Building frontend image..."
                    sh """
                        docker build \
                            -t ${FRONTEND_IMAGE}:${imageTag} \
                            -t ${FRONTEND_IMAGE}:latest \
                            -t productionlevelrag-frontend:latest \
                            -f frontend/Dockerfile ./frontend
                    """
                }
            }
        }

        // ==========================================
        // STAGE 3: PUSH TO REGISTRY (Docker Hub)
        // ==========================================
        stage('Push to Registry') {
            steps {
                script {
                    def commitSha = env.GIT_COMMIT ? env.GIT_COMMIT.take(7) : "latest"
                    def imageTag = "${env.BUILD_NUMBER}-${commitSha}"

                    withCredentials([usernamePassword(
                        credentialsId: REGISTRY_CREDS_ID, 
                        usernameVariable: 'DOCKER_USER', 
                        passwordVariable: 'DOCKER_PASS'
                    )]) {
                        sh """
                            echo "$DOCKER_PASS" | docker login ${REGISTRY} -u "$DOCKER_USER" --password-stdin
                            
                            docker push ${BACKEND_IMAGE}:${imageTag}
                            docker push ${BACKEND_IMAGE}:latest
                            
                            docker push ${FRONTEND_IMAGE}:${imageTag}
                            docker push ${FRONTEND_IMAGE}:latest
                        """
                    }
                }
            }
        }

        // ==========================================
        // STAGE 4: DEPLOY TO KUBERNETES
        // ==========================================
        stage('Deploy to Kubernetes') {
            steps {
                script {
                    def commitSha = env.GIT_COMMIT ? env.GIT_COMMIT.take(7) : "latest"
                    def imageTag = "${env.BUILD_NUMBER}-${commitSha}"
                    echo "Deploying updated backend & frontend to Kubernetes (${K8S_NAMESPACE})..."
                    sh """
                        # 1. Update deployment images with newly pushed image tag
                        kubectl set image deployment/backend backend=${BACKEND_IMAGE}:${imageTag} -n ${K8S_NAMESPACE}
                        kubectl set image deployment/frontend frontend=${FRONTEND_IMAGE}:${imageTag} -n ${K8S_NAMESPACE}
                        
                        # 2. Wait for zero-downtime rolling update completion
                        echo "Waiting for backend rollout to finish..."
                        kubectl rollout status deployment/backend -n ${K8S_NAMESPACE} --timeout=180s
                        
                        echo "Waiting for frontend rollout to finish..."
                        kubectl rollout status deployment/frontend -n ${K8S_NAMESPACE} --timeout=180s
                        
                        echo "Kubernetes rolling deployment successfully verified!"
                    """
                }
            }
        }
    }

    post {
        always {
            // Clean up unused dangling images to preserve disk space
            sh 'docker image prune -f || true'
        }
        success {
            echo "Pipeline succeeded! All gates passed and containers updated."
        }
        failure {
            echo "Pipeline failed! Please inspect stage logs."
        }
    }
}
