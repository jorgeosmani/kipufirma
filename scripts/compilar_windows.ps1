<#
.SYNOPSIS
  Compila KipuFirma para Windows: ejecutable (PyInstaller) e instalador (Inno Setup).

.DESCRIPTION
  Genera:
    dist\KipuFirma\KipuFirma.exe           (aplicación de ventana)
    dist\KipuFirma\kipufirma-cli.exe       (línea de comandos)
    dist\KipuFirma-<versión>-instalador.exe (si Inno Setup 6 está instalado)
    dist\SHA256SUMS.txt                    (huellas para verificar la descarga)

  Recomendado para distribución pública: firmar los .exe con un certificado de
  firma de código (Authenticode) para evitar avisos de SmartScreen.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\compilar_windows.ps1 -AccesoDirecto
#>
[CmdletBinding()]
param([switch]$AccesoDirecto, [switch]$SinInstalador, [switch]$SinPruebas)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path .venv)) { & (Join-Path $PSScriptRoot 'instalar_desarrollo.ps1') -SinAccesoDirecto -SinPruebas:$SinPruebas }
$python = Join-Path $repo '.venv\Scripts\python.exe'

$version = & $python -c "import sys; sys.path.insert(0,'src'); import kipufirma; print(kipufirma.__version__)"
Write-Host "==> Versión $version" -ForegroundColor Cyan
$parts = ($version.Split('.') + @('0','0','0'))[0..3] -join ', '
(Get-Content packaging\version_info.txt -Raw) `
  -replace 'filevers=\([^)]*\)', "filevers=($parts)" `
  -replace 'prodvers=\([^)]*\)', "prodvers=($parts)" `
  -replace "'FileVersion', '[^']*'", "'FileVersion', '$version'" `
  -replace "'ProductVersion', '[^']*'", "'ProductVersion', '$version'" |
  Set-Content packaging\version_info.txt -Encoding UTF8

if (-not $SinPruebas) {
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $python -m pytest -q
    Remove-Item Env:\QT_QPA_PLATFORM
    if ($LASTEXITCODE -ne 0) { throw 'Pruebas fallidas: no se compila.' }
}

Write-Host '==> PyInstaller' -ForegroundColor Cyan
& $python -m PyInstaller packaging\kipufirma.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falló.' }

Write-Host '==> Prueba rápida del ejecutable de consola' -ForegroundColor Cyan
& dist\KipuFirma\kipufirma-cli.exe --help | Select-Object -First 3

if (-not $SinInstalador) {
    $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($iscc) {
        Write-Host '==> Inno Setup' -ForegroundColor Cyan
        & $iscc "/DAppVersion=$version" packaging\kipufirma.iss
    } else {
        Write-Warning 'Inno Setup 6 no está instalado: se omite el instalador (https://jrsoftware.org/isdl.php).'
    }
}

Write-Host '==> SHA256SUMS' -ForegroundColor Cyan
Get-ChildItem dist -Recurse -Include *.exe | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    "$h  $($_.FullName.Substring((Resolve-Path dist).Path.Length + 1))"
} | Set-Content dist\SHA256SUMS.txt -Encoding UTF8

if ($AccesoDirecto) { & (Join-Path $PSScriptRoot 'crear_acceso_directo.ps1') -Ejecutable dist\KipuFirma\KipuFirma.exe }
Write-Host "Compilación terminada en $repo\dist" -ForegroundColor Green
