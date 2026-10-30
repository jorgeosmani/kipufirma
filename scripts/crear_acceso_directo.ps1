<#
.SYNOPSIS
  Crea (o actualiza) el acceso directo de KipuFirma en el Escritorio de Windows.

.DESCRIPTION
  Detecta automáticamente la instalación:
    1. Instalador:        %LOCALAPPDATA%\Programs\KipuFirma\KipuFirma.exe
    2. Compilación local: <repo>\dist\KipuFirma\KipuFirma.exe
    3. Modo desarrollo:   <repo>\.venv\Scripts\pythonw.exe -m kipufirma
  Usa la carpeta Escritorio real (también si está redirigida a OneDrive).

.PARAMETER Ejecutable
  Ruta explícita a KipuFirma.exe (opcional).

.PARAMETER MenuInicio
  Crea también el acceso en el menú Inicio.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\crear_acceso_directo.ps1
#>
[CmdletBinding()]
param(
    [string]$Ejecutable,
    [switch]$MenuInicio
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

$target = $null; $arguments = ''; $workdir = $null
$icon = Join-Path $repo 'packaging\kipufirma.ico'

if ($Ejecutable) {
    if (-not (Test-Path $Ejecutable)) { throw "No existe: $Ejecutable" }
    $target = (Resolve-Path $Ejecutable).Path
} else {
    $candidatos = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\KipuFirma\KipuFirma.exe'),
        (Join-Path $repo 'dist\KipuFirma\KipuFirma.exe')
    )
    $target = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $target) {
        $pyw = Join-Path $repo '.venv\Scripts\pythonw.exe'
        if (-not (Test-Path $pyw)) {
            throw 'No se encontró KipuFirma. Ejecute primero scripts\instalar_desarrollo.ps1 o scripts\compilar_windows.ps1.'
        }
        $target = $pyw; $arguments = '-m kipufirma'; $workdir = $repo
    }
}
if (-not $workdir) { $workdir = Split-Path -Parent $target }
if ($target -like '*.exe' -and $target -notlike '*pythonw.exe') { $icon = $target }

function New-Shortcut([string]$lnkPath) {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnkPath)
    $sc.TargetPath = $target
    $sc.Arguments = $arguments
    $sc.WorkingDirectory = $workdir
    $sc.IconLocation = "$icon,0"
    $sc.Description = 'KipuFirma - Firma electrónica de documentos PDF'
    $sc.Save()
    Write-Host "Acceso directo creado: $lnkPath" -ForegroundColor Green
}

$desktop = [Environment]::GetFolderPath('Desktop')
New-Shortcut (Join-Path $desktop 'KipuFirma.lnk')
if ($MenuInicio) {
    $programs = [Environment]::GetFolderPath('Programs')
    New-Shortcut (Join-Path $programs 'KipuFirma.lnk')
}
