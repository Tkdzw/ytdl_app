; ─────────────────────────────────────────────────────────────────────────────
; installer.iss  —  Inno Setup script for YT Batch Downloader
;
; Requirements:
;   1. Run build_windows.bat first so dist\YTBatchDownloader\ exists
;   2. Download Inno Setup from https://jrsoftware.org/isinfo.php
;   3. Open this file in Inno Setup IDE and press F9 (or Build → Compile)
;
; Output: installer\YTBatchDownloader_Setup.exe
; ─────────────────────────────────────────────────────────────────────────────

#define AppName      "YT Batch Downloader"
#define AppVersion   "1.0.0"
#define AppPublisher "YTDLApp"
#define AppExeName   "YTBatchDownloader.exe"
#define AppURL       "https://github.com/yt-dlp/yt-dlp"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Output location (relative to where this .iss file sits)
OutputDir=installer
OutputBaseFilename=YTBatchDownloader_Setup
; Use the generated icon if present
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Require admin for Program Files install
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Create a &desktop shortcut";     GroupDescription: "Additional icons:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Create a &Quick Launch shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Bundle the entire PyInstaller output folder
Source: "dist\YTBatchDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";                  Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}";        Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}";          Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up the app-data folder created at runtime
Type: filesandordirs; Name: "{userappdata}\.ytdl_app"

[Code]
// Show a note about FFmpeg on the finish page
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
    WizardForm.FinishedLabel.Caption :=
      'Setup has finished installing {#AppName}.' + #13#10 + #13#10 +
      'IMPORTANT: FFmpeg is required for video merging and MP3 conversion.' + #13#10 +
      'If you have not installed it yet, download it from:' + #13#10 +
      '  https://ffmpeg.org/download.html' + #13#10 +
      'and add it to your system PATH.';
end;
