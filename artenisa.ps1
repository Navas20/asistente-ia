param([string]$Command = "start")

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RootDir "backend"
$CliDir = Join-Path $RootDir "cli"
$DataDir = Join-Path $RootDir "data"
$PidFile = Join-Path $DataDir "backend.pid"

$null = New-Item -ItemType Directory -Force -Path $DataDir

function Test-Backend {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8765/health" -TimeoutSec 3 -ErrorAction Stop
        return $r.status -eq "healthy"
    } catch {
        return $false
    }
}

function Start-Backend {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "python"
    $psi.Arguments = "-m uvicorn main:app --host 0.0.0.0 --port 8765"
    $psi.WorkingDirectory = $BackendDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["AUTH_TOKEN"] = "artenisa-secret-token-2026"
    $psi.EnvironmentVariables["PORT"] = "8765"
    $psi.EnvironmentVariables["MAX_SUBAGENTS"] = "10"

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    $p.Start() | Out-Null
    $p.Id | Out-File -FilePath $PidFile -Encoding utf8 -NoNewline

    $maxWait = 15
    $waited = 0
    while (-not (Test-Backend) -and $waited -lt $maxWait) {
        Start-Sleep 1
        $waited++
    }
    return (Test-Backend)
}

function Stop-Backend {
    if (Test-Path $PidFile) {
        $bp = (Get-Content $PidFile -Raw).Trim()
        if ($bp -and (Get-Process -Id $bp -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $bp -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "uvicorn"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
}

function Open-CLI {
    $env:AUTH_TOKEN = "artenisa-secret-token-2026"
    $env:API_URL = "http://localhost:8765"
    Set-Location $CliDir
    python asistente.py
}

switch ($Command.ToLower()) {
    "start" {
        if (-not (Test-Backend)) {
            Stop-Backend
            $ok = Start-Backend
            if (-not $ok) {
                Write-Host "Backend failed to start" -ForegroundColor Red
                exit 1
            }
        }
        Write-Host "Backend ready on http://localhost:8765" -ForegroundColor Green
        Open-CLI
    }
    "stop" {
        Stop-Backend
        Write-Host "Artenisa stopped" -ForegroundColor Yellow
    }
    "restart" {
        Stop-Backend
        Start-Sleep 1
        $ok = Start-Backend
        if ($ok) {
            Write-Host "Backend restarted" -ForegroundColor Green
            Open-CLI
        } else {
            Write-Host "Backend failed to restart" -ForegroundColor Red
        }
    }
    "status" {
        if (Test-Backend) {
            Write-Host "Backend: RUNNING on http://localhost:8765" -ForegroundColor Green
        } else {
            Write-Host "Backend: STOPPED" -ForegroundColor Red
        }
    }
    "cli" {
        Open-CLI
    }
    default {
        Write-Host "Usage: artenisa [command]"
        Write-Host "  start   - Start backend + open CLI"
        Write-Host "  stop    - Stop backend"
        Write-Host "  restart - Restart + open CLI"
        Write-Host "  status  - Show backend status"
        Write-Host "  cli     - Open CLI only"
    }
}
