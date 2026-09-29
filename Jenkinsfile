pipeline {
    agent any

    environment {
        // --- 1. REGISTRY & IMAGE METADATA ---
        REGISTRY = 'docker.io'
        REGISTRY_USER = 'vgmclaren'  // <-- CHANGE TO YOUR DOCKERHUB USERNAME
        BACKEND_IMAGE = "${REGISTRY_USER}/rag-backend"
        FRONTEND_IMAGE = "${REGISTRY_USER}/rag-frontend"
        IMAGE_TAG = "${env.BUILD_NUMBER}-${env.GIT_COMMIT.take(7)}"

        // --- 2. CREDENTIAL IDENTIFIERS ---
        REGISTRY_CREDS_ID = 'docker-registry-credentials'
        PROD_ENV_SECRET_ID = 'rag-production-env'

        // --- 3. MODEL HOST PATHS (Keeps heavy models OUT of Docker images) ---
        // Matches the host paths where your local models reside
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
                                npm ci
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
                    echo "Building lightweight backend image..."
                    sh """
                        docker build \
                            -t ${BACKEND_IMAGE}:${IMAGE_TAG} \
                            -t ${BACKEND_IMAGE}:latest \
                            -f Dockerfile .
                    """

                    echo "Building frontend image..."
                    sh """
                        docker build \
                            -t ${FRONTEND_IMAGE}:${IMAGE_TAG} \
                            -t ${FRONTEND_IMAGE}:latest \
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
                    withCredentials([usernamePassword(
                        credentialsId: REGISTRY_CREDS_ID, 
                        usernameVariable: 'DOCKER_USER', 
                        passwordVariable: 'DOCKER_PASS'
                    )]) {
                        sh """
                            echo "$DOCKER_PASS" | docker login ${REGISTRY} -u "$DOCKER_USER" --password-stdin
                            
                            docker push ${BACKEND_IMAGE}:${IMAGE_TAG}
                            docker push ${BACKEND_IMAGE}:latest
                            
                            docker push ${FRONTEND_IMAGE}:${IMAGE_TAG}
                            docker push ${FRONTEND_IMAGE}:latest
                        """
                    }
                }
            }
        }

        // ==========================================
        // STAGE 4: DEPLOY (Only Backend & Frontend)
        // ==========================================
        stage('Deploy') {
            steps {
                script {
                    echo "Deploying updated backend & frontend containers..."
                    withCredentials([file(credentialsId: PROD_ENV_SECRET_ID, variable: 'SECRET_ENV_FILE')]) {
                        sh """
                            # 1. Temporarily place production secrets for compose
                            cp \$SECRET_ENV_FILE .env
                            
                            # 2. Export model paths
                            export LOCAL_LLM_HOST_PATH="${LOCAL_LLM_HOST_PATH}"
                            export RERANKER_HOST_MODEL_PATH="${RERANKER_HOST_MODEL_PATH}"
                            
                            # 3. Re-create ONLY backend and frontend. 
                            # Neo4j, Qdrant, Prometheus are LEFT RUNNING UNTOUCHED.
                            docker compose up -d --no-deps backend frontend
                            
                            # 4. Remove temporary .env from workspace
                            rm -f .env
                            
                            # 5. Health verification
                            echo "Verifying backend health..."
                            sleep 10
                            curl --fail http://127.0.0.1:8000/healthz/live || exit 1
                            echo "Deployment successfully verified!"
                        """
                    }
                }
            }
        }
    }

    post {
        always {
            // Clean up unused dangling images to preserve disk space
            sh 'docker image prune -f'
        }
        success {
            echo "Pipeline succeeded! All gates passed and containers updated."
        }
        failure {
            echo "Pipeline failed! Please inspect stage logs."
        }
    }
}
