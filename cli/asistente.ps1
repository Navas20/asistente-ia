# PowerShell wrapper for cli/asistente.py
# Loads backend/.env values into the current session and starts the CLI.

$repoRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")
$loadScript = Join-Path $repoRoot "scripts\load_env.ps1"
if (Test-Path $loadScript) {
    . $loadScript
} else {
    Write-Warning "Could not find $loadScript. Proceeding without auto-loading env."
}

python (Join-Path $repoRoot "cli\asistente.py")
