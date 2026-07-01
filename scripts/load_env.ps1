# Load environment variables from backend/.env into the current PowerShell session.
# Usage:
#   .\scripts\load_env.ps1
#   .\scripts\load_env.ps1 -Verbose
#   .\scripts\load_env.ps1 -Command "python backend/main.py"

param(
    [string]$Command = ""
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$envPath = Join-Path $repoRoot "backend\.env"

if (-not (Test-Path $envPath)) {
    Write-Warning "backend/.env not found. Nothing to load."
    if ($Command) { Invoke-Expression $Command }
    return
}

Get-Content $envPath | ForEach-Object {
    if ($_ -match '^[ \t]*([^#][^=\s]+)[ \t]*=[ \t]*(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        if ($value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Trim('"')
        } elseif ($value.StartsWith("'") -and $value.EndsWith("'")) {
            $value = $value.Trim("'")
        }
        [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
        Write-Verbose "Loaded env $name"
    }
}

Write-Host "Loaded environment variables from backend/.env." -ForegroundColor Green

if ($Command) {
    Write-Host "Running: $Command" -ForegroundColor Cyan
    Invoke-Expression $Command
}
