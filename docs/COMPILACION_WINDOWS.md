# Instalación y compilación en Windows 11

## Opción A — Usuario final (recomendada)
1. Descargue `KipuFirma-<versión>-instalador.exe` desde **Releases**.
2. (Opcional) verifique la huella: `Get-FileHash .\KipuFirma-*-instalador.exe` y
   compárela con `SHA256SUMS.txt`.
3. Ejecute el instalador (no requiere administrador). Marque:
   * ☑ **Crear un acceso directo en el escritorio**
   * ☑ **Agregar «Firmar con KipuFirma» al clic derecho de los PDF**
4. Si SmartScreen avisa «Windows protegió su equipo» (ejecutable sin firma de
   código): *Más información → Ejecutar de todas formas*, solo si descargó de
   este repositorio y la huella coincide.

> En Windows 11 la opción del clic derecho aparece en **«Mostrar más opciones»**
> (menú clásico, Shift + F10).

## Opción B — Desde el código fuente (desarrollo)
Requisitos: [Python 3.11+](https://www.python.org/downloads/) (marque *Add to PATH*) y Git.

```powershell
git clone https://github.com/jorgeosmani/kipufirma.git
cd kipufirma
powershell -ExecutionPolicy Bypass -File scripts\instalar_desarrollo.ps1
```

El script crea `.venv`, instala dependencias fijadas, ejecuta las pruebas y
crea el **acceso directo en el Escritorio**. Para recrear solo el acceso:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\crear_acceso_directo.ps1
```

## Opción C — Compilar el ejecutable y el instalador
Requisitos adicionales: [Inno Setup 6](https://jrsoftware.org/isdl.php) (opcional, para el instalador).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\compilar_windows.ps1 -AccesoDirecto
```

Resultado en `dist\`:
* `KipuFirma\KipuFirma.exe` y `KipuFirma\kipufirma-cli.exe` (portable)
* `KipuFirma-<versión>-instalador.exe`
* `SHA256SUMS.txt`

### Firma de código (recomendado para distribución)
Con un certificado Authenticode:
```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a dist\KipuFirma\*.exe
```
(Firme antes de ejecutar Inno Setup, y luego firme también el instalador.)

## Línea de comandos
```powershell
kipufirma-cli certificado
kipufirma-cli firmar C:\Actas --palabra "Firma del docente" --palabra "Firma:" --informe informe.csv
kipufirma-cli firmar contrato.pdf --pagina ultima --ancla inf-der --dx 60 --dy 80
kipufirma-cli verificar C:\Actas\firmados
```
La contraseña se pide sin eco (o `--clave-stdin`); nunca se pasa como argumento.

## Desinstalar
*Configuración → Aplicaciones → KipuFirma → Desinstalar*. La configuración
(`%APPDATA%\KipuFirma`) se conserva; bórrela manualmente si lo desea. Su
archivo `.p12` nunca se toca.
