# ==============================================================================
# Environment Switcher: Toggle between Docker Compose and Kubernetes (PowerShell)
# ==============================================================================
[CmdletBinding()]
param (
    [ValidateSet("k8s", "docker", "status")]
    [string]$Target = "status",
    [string]$Namespace = "rag-system"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

function Stop-K8sPortForwards {
    Write-Host "Stopping any running kubectl port-forward processes..." -ForegroundColor Yellow
    Get-Process -Name kubectl -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "port-forward"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    # Also stop any PowerShell background jobs running port-forward
    Get-Job | Where-Object { $_.Name -like "*k8s-pf*" } | Stop-Job -ErrorAction SilentlyContinue | Remove-Job -Force -ErrorAction SilentlyContinue
}

if ($Target -eq "k8s") {
    Write-Host "`n=== Switching to KUBERNETES Development ===" -ForegroundColor Cyan

    # 1. Stop Docker Compose containers to free host ports (keeps data intact)
    Write-Host "--> Pausing local Docker Compose containers..." -ForegroundColor Yellow
    Push-Location $RootDir
    docker compose stop
    Pop-Location

    # 2. Stop any stale port-forwards
    Stop-K8sPortForwards

    # 3. Verify Kubernetes pods are running
    Write-Host "--> Checking Kubernetes pods in '$Namespace'..." -ForegroundColor Yellow
    kubectl get pods -n $Namespace

    # 4. Start port-forwards in background
    Write-Host "--> Starting Kubernetes port-forwarding to localhost..." -ForegroundColor Green
    Start-Job -Name "k8s-pf-frontend" -ScriptBlock {
        param($ns)
        kubectl port-forward svc/frontend -n $ns 3000:80
    } -ArgumentList $Namespace | Out-Null

    Start-Job -Name "k8s-pf-backend" -ScriptBlock {
        param($ns)
        kubectl port-forward svc/backend -n $ns 8000:8000
    } -ArgumentList $Namespace | Out-Null

    Start-Sleep -Seconds 2

    Write-Host "`n[SUCCESS] Kubernetes environment is ACTIVE!" -ForegroundColor Green
    Write-Host "  Frontend: http://localhost:3000  -> k8s svc/frontend (rag-system)" -ForegroundColor Cyan
    Write-Host "  Backend:  http://localhost:8000  -> k8s svc/backend  (rag-system)" -ForegroundColor Cyan
    Write-Host "  To switch back: .\scripts\switch-env.ps1 -Target docker`n" -ForegroundColor DarkGray
}
elseif ($Target -eq "docker") {
    Write-Host "`n=== Switching to DOCKER COMPOSE Development ===" -ForegroundColor Cyan

    # 1. Stop Kubernetes port-forwards to free host ports
    Stop-K8sPortForwards

    # 2. Start Docker Compose containers
    Write-Host "--> Starting local Docker Compose containers..." -ForegroundColor Yellow
    Push-Location $RootDir
    docker compose start
    Pop-Location

    Write-Host "`n[SUCCESS] Docker Compose environment is ACTIVE!" -ForegroundColor Green
    Write-Host "  Frontend: http://localhost:3000  -> Docker container productionlevelrag-frontend-1" -ForegroundColor Cyan
    Write-Host "  Backend:  http://localhost:8000  -> Docker container productionlevelrag-backend-1" -ForegroundColor Cyan
    Write-Host "  To switch to k8s: .\scripts\switch-env.ps1 -Target k8s`n" -ForegroundColor DarkGray
}
else {
    Write-Host "`n=== Current Environment Status ===" -ForegroundColor Cyan
    $pfJobs = Get-Job | Where-Object { $_.Name -like "*k8s-pf*" -and $_.State -eq "Running" }
    if ($pfJobs) {
        Write-Host "Active Mode: KUBERNETES (Port-forwards active)" -ForegroundColor Green
        Get-Job | Where-Object { $_.Name -like "*k8s-pf*" } | Format-Table Id, Name, State
    } else {
        Write-Host "Active Mode: DOCKER COMPOSE (or no port-forwards active)" -ForegroundColor Yellow
    }

    Write-Host "`nDocker Containers:" -ForegroundColor Cyan
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

    Write-Host "`nKubernetes Pods ($Namespace):" -ForegroundColor Cyan
    kubectl get pods -n $Namespace
}
