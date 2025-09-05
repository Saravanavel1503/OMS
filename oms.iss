; ---------- Inno Setup Script for OMS ----------
#define MyAppName        "OMS"
#define MyAppVersion     "1.0.0"
#define MyAppPublisher   "Saravanavel"
#define MyAppEXE         "OMS.exe"
#define MySourceDir      "C:\D_drive\Saravanavel\tools\OMS_Webapp\dist\OMS"
#define InstallDir       "{localappdata}\OMSApp"   ; per-user, no admin

[Setup]
; Generate your own GUID once (Tools -> Generate GUID in Inno) and keep it stable
AppId={{8E8EBE6F-1B7D-4A7B-9F0A-5C0F5F0B8F01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={#InstallDir}
DefaultGroupName={#MyAppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
OutputBaseFilename=OMS-Setup-{#MyAppVersion}
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppEXE}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Pull in everything from the PyInstaller one-dir output
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppEXE}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppEXE}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional options:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppEXE}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent