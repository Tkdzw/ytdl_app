; ─────────────────────────────────────────────────────────────────────────────
; installer.iss  —  Inno Setup script for YT Downloader
;
; Requirements:
;   1. Run build_windows.bat first so dist\YTDownloader\ exists
;   2. Download Inno Setup from https://jrsoftware.org/isinfo.php
;   3. Open this file in Inno Setup IDE and press F9 (or Build → Compile)
;
; Output: installer\YTDownloader_Setup.exe
;
; Keep AppVersion in step with app_info.py (see CHANGELOG.md).
;
; NOTE: FFmpeg (yt-dlp build, GPL) and Deno (MIT) are bundled under
;       {app}\_internal\tools\ with their license files — users need no
;       extra setup. build_windows.bat downloads and verifies them.
; ─────────────────────────────────────────────────────────────────────────────

#define AppName      "YT Downloader"
#define AppVersion   "2.0.0"
#define AppPublisher "Asher Naison"
#define AppExeName   "YTDownloader.exe"
#define AppURL       "https://github.com/yt-dlp/yt-dlp"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
AppCopyright=Copyright (C) 2026 {#AppPublisher}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Output location (relative to where this .iss file sits)
OutputDir=installer
OutputBaseFilename=YTDownloader_Setup
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
Name: "desktopicon";     Description: "Create a &desktop shortcut";      GroupDescription: "Additional icons:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Create a &Quick Launch shortcut";  GroupDescription: "Additional icons:"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Bundle the entire PyInstaller output folder (includes tools\ffmpeg + tools\deno)
Source: "dist\YTDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Upgrading from 1.x ("YT Batch Downloader"): remove the old exe and shortcuts,
; which had different names and would otherwise be left behind.
Type: files;          Name: "{app}\YTBatchDownloader.exe"
Type: filesandordirs; Name: "{commonprograms}\YT Batch Downloader"
Type: files;          Name: "{commondesktop}\YT Batch Downloader.lnk"

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
// Confirm successful install on the finish page
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
    WizardForm.FinishedLabel.Caption :=
      'Setup has finished installing {#AppName}.' + #13#10 + #13#10 +
      'FFmpeg and Deno are included - everything is ready to use.' + #13#10 + #13#10 +
      'Click Finish to launch the app.';
end;
