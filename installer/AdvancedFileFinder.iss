; Optional: turns the folder build into a normal Windows installer (Inno Setup 6, free).
; 1) run build_exe.bat   2) open this file in Inno Setup   3) press Compile  ->  installer\Output\
#define AppName "Advanced File Finder"
#define AppVersion "1.0.0"
#define AppExe "AdvancedFileFinder.exe"

[Setup]
AppId={{B2D6C7C4-5F55-4E54-9B8E-7B1F6C0E2A11}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=AdvancedFileFinder-Setup-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Files]
Source: "..\dist\AdvancedFileFinder\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
