; Inno Setup script for T4A-BORIS.
; Wraps the portable build folder produced by t4a_boris_windows_deployment.ps1 into a normal
; Windows installer: Start Menu entry, optional Desktop icon, Add/Remove Programs entry,
; uninstaller. No Python/git/terminal ever visible to the end user.
;
; Usage (from a Developer/PowerShell prompt with ISCC on PATH, or full path to ISCC.exe):
;   ISCC.exe /DMyAppVersion="9.14" /DBuildDir="C:\Users\you\T4A-BORIS-9.14-build-output" t4a_boris_installer.iss
;
; MyAppVersion and BuildDir are required defines - there is no sensible default for either,
; since they change on every rebuild.

#ifndef MyAppVersion
  #error "Pass /DMyAppVersion=<version>, e.g. /DMyAppVersion=9.14"
#endif
#ifndef BuildDir
  #error "Pass /DBuildDir=<path to the folder produced by t4a_boris_windows_deployment.ps1>"
#endif

#define MyAppName "T4A-BORIS"
#define MyAppPublisher "T4A"

[Setup]
AppId={{B4A6C4B0-9C7A-4B8D-8B0E-T4ABORISAPPID}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m boris"; WorkingDir: "{app}\python"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m boris"; WorkingDir: "{app}\python"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m boris"; WorkingDir: "{app}\python"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
