# PowerShell wrapper for cli/artenisa.py
# Loads backend/.env values and starts the backend automatically if needed.

$repoRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")
$ensureScript = Join-Path $repoRoot "scripts\ensure_backend.ps1"
if (Test-Path $ensureScript) {
    & $ensureScript
} else {
    Write-Warning "Could not find $ensureScript. Proceeding without auto-starting the backend."
    $loadScript = Join-Path $repoRoot "scripts\load_env.ps1"
    if (Test-Path $loadScript) {
        . $loadScript
    }
    python (Join-Path $repoRoot "cli\asistente.py")
}
