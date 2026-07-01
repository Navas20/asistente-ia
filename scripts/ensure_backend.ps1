param(
    [switch]$SkipCli
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$loadScript = Join-Path $repoRoot "scripts\load_env.ps1"
if (Test-Path $loadScript) {
    . $loadScript
}

$apiUrl = if ($env:API_URL) { $env:API_URL } else { "http://localhost:8000" }
$backendUrl = $apiUrl.TrimEnd('/')

function Test-Backend {
    try {
        $resp = Invoke-WebRequest -Uri "$backendUrl/" -TimeoutSec 3 -UseBasicParsing
        return $resp.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

if (Test-Backend) {
    Write-Host "Backend already running at $backendUrl" -ForegroundColor Green
}
else {
    $existing = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'main:app' -and $_.CommandLine -match 'backend'
    } | Select-Object -First 1

    if (-not $existing) {
        Write-Host "Starting backend automatically..." -ForegroundColor Cyan
        Start-Process -FilePath "python" -ArgumentList @('-m','uvicorn','main:app','--app-dir','backend','--host','0.0.0.0','--port','8000') -WorkingDirectory $repoRoot -WindowStyle Hidden
        Start-Sleep -Seconds 2
    }
    else {
        Write-Host "Backend process already detected." -ForegroundColor Yellow
    }
}

for ($i = 0; $i -lt 20; $i++) {
    if (Test-Backend) {
        Write-Host "Backend ready at $backendUrl" -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 1
}

if (-not (Test-Backend)) {
    Write-Warning "Backend did not become ready in time. You can start it manually with: python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000"
    if ($SkipCli) { return }
}

if (-not $SkipCli) {
    Write-Host "Launching Artenisa CLI..." -ForegroundColor Cyan
    python (Join-Path $repoRoot "cli\asistente.py")
}
