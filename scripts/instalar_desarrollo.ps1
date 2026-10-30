<#
.SYNOPSIS
  Prepara KipuFirma para ejecutarse desde el código fuente en Windows 11.

.DESCRIPTION
  1. Verifica Python 3.11+ (lanzador "py").
  2. Crea el entorno virtual .venv e instala dependencias fijadas.
  3. Ejecuta las pruebas automáticas.
  4. Crea el acceso directo en el Escritorio.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\instalar_desarrollo.ps1
#>
[CmdletBinding()]
param([switch]$SinPruebas, [switch]$SinAccesoDirecto)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host '==> Verificando Python' -ForegroundColor Cyan
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { throw 'No se encontró Python. Instálelo desde https://www.python.org/downloads/ (marque "Add python.exe to PATH").' }
$ver = & py -3 -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]'3.11') { throw "Se requiere Python 3.11 o superior (encontrado $ver)." }
Write-Host "Python $ver"

Write-Host '==> Creando entorno virtual .venv' -ForegroundColor Cyan
if (-not (Test-Path .venv)) { & py -3 -m venv .venv }
$venvVer = & (Join-Path $repo '.venv\Scripts\python.exe') -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$venvVer -lt [version]'3.11') {
    throw "El entorno .venv usa Python $venvVer. Borre la carpeta .venv y vuelva a ejecutar este script."
}
$python = Join-Path $repo '.venv\Scripts\python.exe'
function Invoke-Pip([string[]]$pipArgs) {
    & $python -m pip @pipArgs
    if ($LASTEXITCODE -ne 0) {
        throw "pip falló al ejecutar: pip $($pipArgs -join ' '). Revise el mensaje anterior (suele indicar el paquete en conflicto)."
    }
}
Invoke-Pip @('install', '--upgrade', 'pip')
Invoke-Pip @('install', '-r', 'requirements-dev.txt')
Invoke-Pip @('install', '-e', '.', '--no-deps')

if (-not $SinPruebas) {
    Write-Host '==> Ejecutando pruebas' -ForegroundColor Cyan
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $python -m pytest -q
    Remove-Item Env:\QT_QPA_PLATFORM
    if ($LASTEXITCODE -ne 0) { throw 'Las pruebas fallaron. Revise la salida anterior.' }
}

if (-not $SinAccesoDirecto) {
    & (Join-Path $PSScriptRoot 'crear_acceso_directo.ps1')
}
Write-Host ''
Write-Host 'Listo. Abra KipuFirma desde el acceso directo del Escritorio o con:' -ForegroundColor Green
Write-Host '   .venv\Scripts\pythonw.exe -m kipufirma'
