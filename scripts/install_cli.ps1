#!/usr/bin/env pwsh
<#
.SYNOPSIS
Instala el CLI de Artenisa en PowerShell

.DESCRIPTION
Este script configura el perfil de PowerShell para que el comando 'artenisa' 
funcione desde cualquier ubicación.
#>

$ErrorActionPreference = "Stop"

Write-Host "🔧 Instalando CLI de Artenisa..." -ForegroundColor Cyan
Write-Host ""

# Detectar ruta del proyecto
$projectRoot = Split-Path -Parent $PSScriptRoot
$cliScript = Join-Path $projectRoot "cli\asistente.py"

Write-Host "📁 Proyecto detectado en: $projectRoot" -ForegroundColor Green
Write-Host "📄 CLI script: $cliScript" -ForegroundColor Green
Write-Host ""

# Verificar que existe el CLI
if (-not (Test-Path $cliScript)) {
    Write-Host "❌ Error: No se encuentra cli/asistente.py" -ForegroundColor Red
    exit 1
}

# Ruta del perfil de PowerShell
$profilePath = $PROFILE
$profileDir = Split-Path -Parent $profilePath

Write-Host "📝 Perfil de PowerShell: $profilePath" -ForegroundColor Yellow
Write-Host ""

# Crear directorio del perfil si no existe
if (-not (Test-Path $profileDir)) {
    Write-Host "📁 Creando directorio de perfil..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}

# Crear o actualizar el perfil
$functionCode = @"

# ========================================
# ARTENISA CLI - Auto-generado
# ========================================
function artenisa {
    `$repoRoot = "$projectRoot"
    `$cliPath = Join-Path `$repoRoot 'cli\asistente.py'
    
    if (Test-Path `$cliPath) {
        python `$cliPath `$args
    } else {
        Write-Host "❌ Error: No se encuentra el CLI de Artenisa en `$cliPath" -ForegroundColor Red
        Write-Host "💡 Ejecuta: cd '$projectRoot' && python scripts/install_cli.ps1" -ForegroundColor Yellow
    }
}

Write-Host "✅ Artenisa CLI cargado. Usa 'artenisa' para iniciar." -ForegroundColor Green
# ========================================

"@

# Verificar si ya existe la función
$profileContent = ""
if (Test-Path $profilePath) {
    $profileContent = Get-Content $profilePath -Raw
}

if ($profileContent -match "# ARTENISA CLI") {
    Write-Host "⚠️  Función 'artenisa' ya existe en el perfil. Actualizando..." -ForegroundColor Yellow
    
    # Remover bloque anterior
    $profileContent = $profileContent -replace "(?s)# ========================================\s*# ARTENISA CLI.*?# ========================================\s*", ""
    
    # Agregar nuevo bloque
    $profileContent += $functionCode
    
    Set-Content -Path $profilePath -Value $profileContent -Encoding UTF8
} else {
    Write-Host "➕ Agregando función 'artenisa' al perfil..." -ForegroundColor Yellow
    Add-Content -Path $profilePath -Value $functionCode -Encoding UTF8
}

Write-Host ""
Write-Host "✅ Instalación completada!" -ForegroundColor Green
Write-Host ""
Write-Host "📌 Próximos pasos:" -ForegroundColor Cyan
Write-Host "   1. Cierra y reabre PowerShell (o ejecuta: . `$PROFILE)" -ForegroundColor White
Write-Host "   2. Ejecuta: artenisa" -ForegroundColor White
Write-Host ""
Write-Host "💡 Si tienes problemas, ejecuta: Get-Command artenisa" -ForegroundColor Yellow
Write-Host ""
