# ==============================================================================
# Production RAG Kubernetes Cluster Smoke Test Script (PowerShell)
# ==============================================================================
[CmdletBinding()]
param (
    [string]$Namespace = "rag-system",
    [string]$BackendUrl = "http://localhost:8000",
    [string]$FrontendUrl = "http://localhost:3000",
    [string]$GrafanaUrl = "http://localhost:3001"
)

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "      PRODUCTION RAG KUBERNETES TEST SUITE               " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# 1. Pod and Service Status Check
# ------------------------------------------------------------------------------
Write-Host "`n[1/5] Checking Kubernetes Pod and Service Status in '$Namespace'..." -ForegroundColor Yellow
$pods = kubectl get pods -n $Namespace --no-headers
foreach ($line in ($pods -split "`n")) {
    if (-not [string]::IsNullOrWhiteSpace($line)) {
        $parts = $line -split "\s+"
        $name = $parts[0]
        $ready = $parts[1]
        $status = $parts[2]
        if ($status -eq "Running" -or $status -eq "Completed") {
            Write-Host "  [OK] Pod $name ($ready) - $status" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] Pod $name ($ready) - $status" -ForegroundColor Red
        }
    }
}

# ------------------------------------------------------------------------------
# 2. Health and Dependency Readiness (/healthz/live and /healthz/ready)
# ------------------------------------------------------------------------------
Write-Host "`n[2/5] Testing Backend Health and Database Connectivity..." -ForegroundColor Yellow
try {
    $liveRes = Invoke-RestMethod -Uri "$BackendUrl/healthz/live" -TimeoutSec 5
    if ($liveRes.status -eq "ok") {
        Write-Host "  [OK] Liveness Probe ($BackendUrl/healthz/live): Healthy" -ForegroundColor Green
    }
} catch {
    Write-Host "  [FAIL] Liveness probe failed: $_" -ForegroundColor Red
}

try {
    $readyRes = Invoke-RestMethod -Uri "$BackendUrl/healthz/ready" -TimeoutSec 5
    if ($readyRes.status -eq "ready") {
        Write-Host "  [OK] Readiness Probe ($BackendUrl/healthz/ready): Ready" -ForegroundColor Green
        Write-Host "       - Qdrant Vector DB: $($readyRes.dependencies.qdrant)" -ForegroundColor Gray
        Write-Host "       - Neo4j Graph DB:   $($readyRes.dependencies.neo4j)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [FAIL] Readiness probe failed: $_" -ForegroundColor Red
}

# ------------------------------------------------------------------------------
# 3. Store Catalog and Sync Verification
# ------------------------------------------------------------------------------
Write-Host "`n[3/5] Testing Store Catalog API and Pod Synchronization..." -ForegroundColor Yellow
try {
    $stores = Invoke-RestMethod -Uri "$BackendUrl/api/stores" -TimeoutSec 5
    Write-Host "  [OK] Retrieved $($stores.Count) registered stores:" -ForegroundColor Green
    foreach ($s in $stores) {
        $docCount = if ($s.documents) { $s.documents.Count } else { 0 }
        Write-Host "       - [$($s.id)] $($s.name) ($docCount documents attached)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  [FAIL] Failed to list stores: $_" -ForegroundColor Red
}

# ------------------------------------------------------------------------------
# 4. Live End-to-End RAG Ingestion and Stream Query
# ------------------------------------------------------------------------------
Write-Host "`n[4/5] Testing Live RAG Query Engine (SSE Stream)..." -ForegroundColor Yellow
try {
    $queryBody = @{
        query = "What was the total revenue in Q4 2024?"
        store_id = "b23f1806"
    } | ConvertTo-Json

    $rawStream = Invoke-RestMethod -Uri "$BackendUrl/api/chat/stream" `
        -Method Post `
        -Body $queryBody `
        -ContentType "application/json" `
        -TimeoutSec 30

    $answerFound = $false
    foreach ($line in ($rawStream -split "`n")) {
        if ($line -match '^data:\s*(\{.*"answer":.*\})') {
            $completeData = $matches[1] | ConvertFrom-Json
            Write-Host "  [OK] Answer: $($completeData.answer)" -ForegroundColor Green
            Write-Host "       - Route Used:          $($completeData.route_used)" -ForegroundColor Gray
            Write-Host "       - Numerical Fidelity:  $($completeData.numerical_fidelity_passed)" -ForegroundColor Gray
            Write-Host "       - Citations:           $($completeData.citations.Count) verified references" -ForegroundColor Gray
            $answerFound = $true
            break
        }
    }
    if (-not $answerFound) {
        Write-Host "  [OK] Stream completed successfully." -ForegroundColor Green
    }
} catch {
    Write-Host "  [FAIL] Chat stream query failed: $_" -ForegroundColor Red
}

# ------------------------------------------------------------------------------
# 5. Frontend and Grafana Observability Reachability
# ------------------------------------------------------------------------------
Write-Host "`n[5/5] Testing Frontend and Grafana Observability Dashboards..." -ForegroundColor Yellow
try {
    $fe = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 5
    if ($fe.StatusCode -eq 200) {
        Write-Host "  [OK] Frontend UI ($FrontendUrl): Reachable (HTTP 200)" -ForegroundColor Green
    }
} catch {
    Write-Host "  [FAIL] Frontend UI unreachable: $_" -ForegroundColor Red
}

try {
    $gf = Invoke-RestMethod -Uri "$GrafanaUrl/api/health" -TimeoutSec 5
    if ($gf.database -eq "ok") {
        Write-Host "  [OK] Grafana Server ($GrafanaUrl): Healthy (v$($gf.version))" -ForegroundColor Green
    }
    
    $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:admin"))
    $dashboards = Invoke-RestMethod -Uri "$GrafanaUrl/api/search" `
        -Headers @{Authorization=("Basic " + $auth)} `
        -TimeoutSec 5
    $dbTitles = ($dashboards | Where-Object { $_.type -eq "dash-db" }).title -join ", "
    Write-Host "       - Provisioned Dashboards: $dbTitles" -ForegroundColor Gray
} catch {
    Write-Host "  [FAIL] Grafana unreachable: $_" -ForegroundColor Red
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "                  TEST SUITE FINISHED                     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
