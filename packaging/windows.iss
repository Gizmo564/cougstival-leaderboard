; Inno Setup script. Build with:  iscc /DAppVersion=1.0.0 packaging\windows.iss   (after the PyInstaller build in dist\CougstivalLeaderboard)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
[Setup]
AppName=Leaderboard Kit
AppVersion={#AppVersion}
DefaultDirName={autopf}\Leaderboard Kit
DefaultGroupName=Leaderboard Kit
OutputBaseFilename=LeaderboardKit-Setup-{#AppVersion}
OutputDir=..\installer
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\CougstivalLeaderboard.exe

[Files]
Source: "..\dist\CougstivalLeaderboard\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Leaderboard Setup"; Filename: "{app}\CougstivalLeaderboard.exe"; Parameters: "setup"
Name: "{autodesktop}\Leaderboard Setup"; Filename: "{app}\CougstivalLeaderboard.exe"; Parameters: "setup"

[Run]
Filename: "{app}\CougstivalLeaderboard.exe"; Parameters: "setup"; Description: "Open the setup app"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Unregister-ScheduledTask -TaskName 'CougstivalLeaderboard' -Confirm:$false -ErrorAction SilentlyContinue"""; Flags: runhidden; RunOnceId: "RemoveTask"
