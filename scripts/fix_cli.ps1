# Fix Artenisa CLI
$projectRoot = "C:\Users\ASUS\Documents\Mis proyectos\asistente-ia"
$cliPath = Join-Path $projectRoot "cli\asistente.py"

Write-Host "Configurando Artenisa CLI..."
Write-Host ""
Write-Host "Proyecto: $projectRoot"
Write-Host "CLI: $cliPath"
Write-Host ""

$functionCode = @"

# ARTENISA CLI
function artenisa {
    python "$cliPath" `$args
}

"@

$profilePath = $PROFILE

if (-not (Test-Path (Split-Path $profilePath))) {
    New-Item -ItemType Directory -Path (Split-Path $profilePath) -Force | Out-Null
}

if (Test-Path $profilePath) {
    $content = Get-Content $profilePath -Raw
    if ($content -match "# ARTENISA CLI") {
        Write-Host "Actualizando funcion existente..."
        $content = $content -replace "(?s)# ARTENISA CLI.*?function artenisa \{[^}]+\}", $functionCode
        Set-Content -Path $profilePath -Value $content
    } else {
        Write-Host "Agregando nueva funcion..."
        Add-Content -Path $profilePath -Value $functionCode
    }
} else {
    Write-Host "Creando nuevo perfil..."
    Set-Content -Path $profilePath -Value $functionCode
}

Write-Host ""
Write-Host "Instalacion completada!"
Write-Host ""
Write-Host "Proximos pasos:"
Write-Host "  1. Cierra y reabre PowerShell"
Write-Host "  2. Ejecuta: artenisa"
Write-Host ""
