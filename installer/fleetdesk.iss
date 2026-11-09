; Windows installer for FleetDesk (Inno Setup 6). Built by scripts/build_installer.py, which
; passes AppVersion and SourceDir (the portable bundle staged by scripts/build_portable.py).
;
; Per-user install: no administrator rights, nothing outside the user's profile. Every
; executable that runs after installation is the PSF-signed Python from the bundle.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\FleetDesk"
#endif
#define AppName "FleetDesk"
#define AppPort "5000"

[Setup]
; Never change AppId: it is how Windows recognises an upgrade of the same app.
AppId={{6C1F9D4B-2E8A-4F37-9B5D-0A7E3C2D1F84}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ZIUGOD
AppPublisherURL=https://ziugod.github.io/fleetdesk/
AppSupportURL=https://github.com/ZIUGOD/fleetdesk/blob/main/docs/guia-do-usuario.md
AppUpdatesURL=https://ziugod.github.io/fleetdesk/
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=FleetDesk-Setup
SetupIconFile=..\src\fleetdesk\static\img\fleetdesk.ico
UninstallDisplayIcon={app}\fleetdesk.ico
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; The app runs in the background with no window; Restart Manager may stop it if the
; polite /quit request in [Code] did not.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Replace the bundled runtime wholesale on upgrade, so no stale module from an older
; version can shadow a newer one.
Type: filesandordirs; Name: "{app}\runtime"

[Files]
Source: "{#SourceDir}\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\src\fleetdesk\static\img\fleetdesk.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m fleetdesk"; WorkingDir: "{app}"; IconFilename: "{app}\fleetdesk.ico"; Comment: "Painel da transportadora a partir das planilhas"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m fleetdesk"; WorkingDir: "{app}"; IconFilename: "{app}\fleetdesk.ico"; Tasks: desktopicon

[Run]
; No skipifsilent: after a silent in-app update the app reopens by itself.
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m fleetdesk"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall

[UninstallDelete]
; Python writes bytecode caches next to the sources at run time.
Type: filesandordirs; Name: "{app}\runtime"

[Code]
// Ask a running FleetDesk to shut down through its own /quit endpoint, so files are not in
// use. Settings in %APPDATA%\FleetDesk are left untouched.
procedure StopRunningFleetDesk();
var
  Request: Variant;
begin
  try
    Request := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Request.Open('POST', 'http://127.0.0.1:{#AppPort}/quit', False);
    Request.SetTimeouts(1000, 1000, 1000, 1000);
    Request.Send('');
    Sleep(1500);
  except
    // Not running: nothing to stop.
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningFleetDesk();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningFleetDesk();
  Result := True;
end;
