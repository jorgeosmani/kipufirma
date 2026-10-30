; Instalador de KipuFirma para Windows 10/11 (Inno Setup 6).
; Compilar:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\kipufirma.iss
; Requiere haber generado antes dist\KipuFirma con PyInstaller.
; Instala POR jorgeosmani (sin permisos de administrador) en %LOCALAPPDATA%\Programs\KipuFirma.

#define AppName "KipuFirma"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "KipuFirma.exe"

[Setup]
AppId={{6B1E2C4A-9F3D-4E57-A8C1-2D7B5E0F9A31}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=KipuFirma
AppPublisherURL=https://github.com/jorgeosmani/kipufirma
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=KipuFirma-{#AppVersion}-instalador
SetupIconFile=kipufirma.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
MinVersion=10.0.17763

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el &escritorio"; GroupDescription: "Accesos directos:"
Name: "contextmenu"; Description: "Agregar «Firmar con KipuFirma» al clic derecho de los PDF"; GroupDescription: "Integración con el Explorador:"

[Files]
Source: "..\dist\KipuFirma\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Firma electrónica de documentos PDF"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon; Comment: "Firma electrónica de documentos PDF"

[Registry]
; Menú contextual para .pdf (por usuario, sin tocar la asociación predeterminada de PDF).
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\KipuFirma"; ValueType: string; ValueName: ""; ValueData: "Firmar con KipuFirma"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\KipuFirma"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\KipuFirma"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\KipuFirma\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
