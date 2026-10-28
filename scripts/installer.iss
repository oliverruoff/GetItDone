#define MyAppVersion "0.1.0"
[Setup]
AppId={{FDC2216A-08C0-44D3-A977-381E34CB7D61}
AppName=GetItDone
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\GetItDone
DefaultGroupName=GetItDone
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=GetItDone-Setup-Windows
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\GetItDone.exe
[Files]
Source: "..\dist\GetItDone\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\GetItDone"; Filename: "{app}\GetItDone.exe"; AppUserModelID: "de.getitdone.notebook"
Name: "{autodesktop}\GetItDone"; Filename: "{app}\GetItDone.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Desktop-Verknüpfung erstellen"; Flags: unchecked
[Registry]
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\de.getitdone.notebook"; ValueType: string; ValueName: "DisplayName"; ValueData: "GetItDone"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\de.getitdone.notebook"; ValueType: string; ValueName: "IconUri"; ValueData: "{app}\_internal\app\ui\assets\getitdone.ico"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "GetItDone"; Flags: dontcreatekey uninsdeletevalue
[Run]
Filename: "{app}\GetItDone.exe"; Description: "GetItDone starten"; Flags: nowait postinstall skipifsilent
