# ─────────────────────────────────────────────────────────────────────────────
# fetch_tools.ps1 — download FFmpeg and Deno into vendor\ for bundling.
#
# Called by build_windows.bat before PyInstaller. build.spec copies vendor\
# into the app as tools\, so installed copies of the app work out of the box.
#
# Safety:
#   * Downloads only over HTTPS from the projects' official GitHub releases.
#   * Every archive is checked against the SHA-256 checksum the publisher
#     posts alongside it. A missing or mismatched checksum stops the build;
#     nothing unverified is ever bundled.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch_tools.ps1 [-Force]
# ─────────────────────────────────────────────────────────────────────────────
param([switch]$Force)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is much faster without it
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root   = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor"
$tmp    = Join-Path ([IO.Path]::GetTempPath()) ("ytdl_tools_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $vendor, $tmp | Out-Null

# FFmpeg build maintained by the yt-dlp project (same as winget yt-dlp.FFmpeg)
$FfmpegZipName  = "ffmpeg-master-latest-win64-gpl.zip"
$FfmpegBase     = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest"
$FfmpegZipUrl   = "$FfmpegBase/$FfmpegZipName"
$FfmpegSumUrl   = "$FfmpegBase/checksums.sha256"

# Deno — yt-dlp's default JavaScript runtime
$DenoZipName    = "deno-x86_64-pc-windows-msvc.zip"
$DenoZipUrl     = "https://github.com/denoland/deno/releases/latest/download/$DenoZipName"
$DenoSumUrl     = "$DenoZipUrl.sha256sum"
$DenoLicenseUrl = "https://raw.githubusercontent.com/denoland/deno/main/LICENSE.md"

function Get-ExpectedHash([string]$checksumText, [string]$fileName) {
    # Accepts "<hash>  <name>" lists, a bare hash, or PowerShell Get-FileHash output.
    $hashRe = "\b[0-9a-fA-F]{64}\b"
    $lines = $checksumText -split "`r?`n" | Where-Object { $_.Trim() }
    # 1) a "<hash>  <fileName>" line
    foreach ($line in $lines) {
        if ($line -match [regex]::Escape($fileName)) {
            $m = [regex]::Match($line, $hashRe)
            if ($m.Success) { return $m.Value.ToLower() }
        }
    }
    # 2) a file holding exactly one hash (bare hash, or "Hash : ..." format)
    $all = [regex]::Matches($checksumText, $hashRe)
    if ($all.Count -eq 1) { return $all[0].Value.ToLower() }
    throw "No SHA-256 checksum for $fileName found in the checksum file."
}

function Get-Verified([string]$url, [string]$sumUrl, [string]$fileName) {
    $dest = Join-Path $tmp $fileName
    Write-Host "[..] Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    Write-Host "[..] Downloading checksum $sumUrl"
    $sumText = (Invoke-WebRequest -Uri $sumUrl -UseBasicParsing).Content
    if ($sumText -is [byte[]]) { $sumText = [Text.Encoding]::UTF8.GetString($sumText) }
    $expected = Get-ExpectedHash $sumText $fileName
    $actual = (Get-FileHash -Algorithm SHA256 -Path $dest).Hash.ToLower()
    if ($actual -ne $expected) {
        throw "Checksum mismatch for $fileName`n  expected $expected`n  got      $actual"
    }
    Write-Host "[OK] SHA-256 verified: $fileName"
    return $dest
}

try {
    # ── FFmpeg ───────────────────────────────────────────────────────────────
    $ffDir = Join-Path $vendor "ffmpeg"
    if ($Force -or -not (Test-Path (Join-Path $ffDir "ffmpeg.exe"))) {
        $zip = Get-Verified $FfmpegZipUrl $FfmpegSumUrl $FfmpegZipName
        $out = Join-Path $tmp "ffmpeg"
        Expand-Archive -Path $zip -DestinationPath $out -Force
        $bin = Get-ChildItem -Path $out -Recurse -Filter ffmpeg.exe | Select-Object -First 1
        if (-not $bin) { throw "ffmpeg.exe not found inside $FfmpegZipName" }
        Remove-Item -Recurse -Force $ffDir -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $ffDir | Out-Null
        Copy-Item (Join-Path $bin.DirectoryName "ffmpeg.exe")  $ffDir
        Copy-Item (Join-Path $bin.DirectoryName "ffprobe.exe") $ffDir
        $lic = Get-ChildItem -Path $out -Recurse -Filter "LICENSE*" | Select-Object -First 1
        if ($lic) { Copy-Item $lic.FullName (Join-Path $ffDir "LICENSE.txt") }
        Write-Host "[OK] FFmpeg -> $ffDir"
    } else {
        Write-Host "[OK] FFmpeg already in $ffDir (use -Force to refresh)"
    }

    # ── Deno ─────────────────────────────────────────────────────────────────
    $denoDir = Join-Path $vendor "deno"
    if ($Force -or -not (Test-Path (Join-Path $denoDir "deno.exe"))) {
        $zip = Get-Verified $DenoZipUrl $DenoSumUrl $DenoZipName
        Remove-Item -Recurse -Force $denoDir -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $denoDir | Out-Null
        Expand-Archive -Path $zip -DestinationPath $denoDir -Force
        if (-not (Test-Path (Join-Path $denoDir "deno.exe"))) { throw "deno.exe not found inside $DenoZipName" }
        Invoke-WebRequest -Uri $DenoLicenseUrl -OutFile (Join-Path $denoDir "LICENSE.md") -UseBasicParsing
        Write-Host "[OK] Deno -> $denoDir"
    } else {
        Write-Host "[OK] Deno already in $denoDir (use -Force to refresh)"
    }

    & (Join-Path $ffDir "ffmpeg.exe") -hide_banner -version | Select-Object -First 1
    & (Join-Path $denoDir "deno.exe") --version | Select-Object -First 1
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
