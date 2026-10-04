# ==============================================================================
# Production RAG Kubernetes Deployment Script (PowerShell)
# ==============================================================================
[CmdletBinding()]
param (
    [string]$Namespace = "rag-system"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

Write-Host "=== Deploying Production RAG Stack to Kubernetes ===" -ForegroundColor Cyan
Write-Host "Target Namespace: $Namespace" -ForegroundColor Cyan

# 1. Verify kubectl
try {
    kubectl version --client | Out-Null
} catch {
    Write-Error "kubectl is not installed or not available in PATH."
    exit 1
}

# 2. Ensure Namespace exists
Write-Host "--> Ensuring namespace '$Namespace' exists..." -ForegroundColor Yellow
kubectl apply -f "$RootDir/k8s/00-namespace.yaml"

# 3. Create secrets from .env if present and rag-secrets doesn't exist
$secretExists = $false
try {
    kubectl get secret rag-secrets -n $Namespace 2>$null | Out-Null
    $secretExists = ($LASTEXITCODE -eq 0)
} catch {
    $secretExists = $false
}

$envPath = Join-Path $RootDir ".env"
if (Test-Path $envPath -and -not $secretExists) {
    Write-Host "--> Populating '$Namespace/rag-secrets' from local .env file..." -ForegroundColor Yellow
    $envLines = Get-Content $envPath
    
    function Get-EnvVal($key, $defaultVal = "") {
        $line = $envLines | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
        if ($line) {
            return ($line -split "=", 2)[1].Trim(' "''')
        }
        return $defaultVal
    }

    $neo4jPw = Get-EnvVal "NEO4J_PASSWORD" "production_password"
    $groqKey = Get-EnvVal "GROQ_API_KEY" ""
    $geminiKey = Get-EnvVal "GEMINI_API_KEY" ""
    $nvidiaKey = Get-EnvVal "NVIDIA_API_KEY" ""
    $hfToken = Get-EnvVal "HF_TOKEN" ""
    $lfPub = Get-EnvVal "LANGFUSE_PUBLIC_KEY" ""
    $lfSec = Get-EnvVal "LANGFUSE_SECRET_KEY" ""

    kubectl create secret generic rag-secrets `
        --namespace=$Namespace `
        --from-literal=NEO4J_PASSWORD="$neo4jPw" `
        --from-literal=GROQ_API_KEY="$groqKey" `
        --from-literal=GEMINI_API_KEY="$geminiKey" `
        --from-literal=NVIDIA_API_KEY="$nvidiaKey" `
        --from-literal=HF_TOKEN="$hfToken" `
        --from-literal=LANGFUSE_PUBLIC_KEY="$lfPub" `
        --from-literal=LANGFUSE_SECRET_KEY="$lfSec" `
        --dry-run=client -o yaml | kubectl apply -f -
}

# 4. Apply all manifests via Kustomize
Write-Host "--> Applying declarative manifests via Kustomize..." -ForegroundColor Yellow
kubectl apply -k "$RootDir/k8s"

# 5. Monitor rollout progress
Write-Host "--> Awaiting database availability..." -ForegroundColor Yellow
kubectl rollout status deployment/qdrant -n $Namespace --timeout=120s
kubectl rollout status statefulset/neo4j -n $Namespace --timeout=180s

Write-Host "--> Awaiting application rollout..." -ForegroundColor Yellow
kubectl rollout status deployment/backend -n $Namespace --timeout=120s
kubectl rollout status deployment/frontend -n $Namespace --timeout=120s

Write-Host "`n=== Deployment Completed Successfully! ===" -ForegroundColor Green
Write-Host "`nPod Status:" -ForegroundColor Cyan
kubectl get pods -n $Namespace

Write-Host "`nService Endpoints:" -ForegroundColor Cyan
kubectl get svc -n $Namespace

Write-Host "`nIngress:" -ForegroundColor Cyan
kubectl get ingress -n $Namespace

Write-Host "`nAccess Options:" -ForegroundColor Yellow
Write-Host "1. Ingress (requires ingress controller): http://rag.local (add to C:\Windows\System32\drivers\etc\hosts)"
Write-Host "2. Port Forward Frontend:  kubectl port-forward svc/frontend -n $Namespace 3000:80"
Write-Host "3. Port Forward Backend:   kubectl port-forward svc/backend -n $Namespace 8000:8000"
Write-Host "4. Port Forward Grafana:   kubectl port-forward svc/grafana -n $Namespace 3001:3000"
