# Changelog

All notable changes to YT Downloader. Versions follow
[Semantic Versioning](https://semver.org/): MAJOR for changes that remove or
rework features, MINOR for new features, PATCH for fixes.

When releasing, update the version in **`app_info.py`** (used by the app and
the .exe properties) and **`installer.iss`** (`AppVersion`).

---

## 2.0.0 — 2026-11-07

A redesign for everyday users. **Renamed from "YT Batch Downloader" to "YT Downloader".**

### Added
- **Download list on the home screen** — every link becomes a row with title, thumbnail,
  length and status, plus Play, Open folder, Retry, Details, Stop and Remove buttons.
- **Guided setup** — a "Finish setting up" window finds FFmpeg and a JavaScript runtime,
  and installs any missing one with one click through WinGet (`yt-dlp.FFmpeg`,
  `DenoLand.Deno`). The app picks them up immediately, without a restart.
- **Tools bundled in the installer** — `scripts/fetch_tools.ps1` downloads FFmpeg and Deno
  from their official releases, verifies their SHA-256 checksums, and the build includes them.
- **Instant Stop** — stops the current download within about a second and removes partial
  files; waiting items stay in the list. Single rows can be stopped or removed.
- **Add links while downloading** — they join the running batch automatically.
- **Plain-language errors** — e.g. "This video is private." with what to do next; the
  technical message is under Details (with Copy).
- **Overall progress** — "3 of 10 done · about 5 min left", plus a finish banner with
  Open folder / Play, a sound and a flashing taskbar button.
- **Keyboard shortcuts** — Ctrl+V adds clipboard links, Ctrl+Enter starts, Ctrl+L jumps to
  the link box, Ctrl+1/2/3 switch tabs, Esc closes dialogs.
- **Tooltips** on every setting.
- **About window** — developer, version and release date, build type, Windows and tool
  versions, links to your downloads/settings/log folders, what's new, shortcuts, and
  "Copy details" for bug reports.
- Version, product name and developer shown in the .exe's file properties.

### Changed
- **Settings simplified** — everyday options first; retries, parallel connections, speed
  limit, proxy and tool locations moved under a collapsed "Advanced" section.
- **Readable in light and dark mode** — all text at least 12 px with WCAG AA contrast
  (≥ 4.5:1); status shown in words and symbols, not colour alone. The theme now follows
  Windows by default ("System").
- Deno is preferred after Node.js; QuickJS is tried last (it is much slower).
- Clearing the History now asks for confirmation first.

### Removed
- The separate **Batch Queue** tab (its job is done by the home-screen list).

### Fixed
- yt-dlp's built-in Deno support is no longer switched off when no runtime was detected.
- CustomTkinter redraw errors when list rows or dialogs closed.

---

## 1.1.0

### Added
- **"Download" and "Quality" choices** on the home screen: Video (MP4) / Audio (MP3), and
  Best / 1080p / 720p / 480p or 128–320 kbps, with a short hint for each.
- Capped qualities prefer H.264 MP4, which plays on almost any device; WEBM now correctly
  gets VP9/AV1 + Opus.
- Status says what FFmpeg is doing ("Merging video and audio…", "Converting to MP3…").
- Clickable "Fix" chips when setup is incomplete.

### Changed
- The per-video format pop-up is off by default (one-time settings migration).
- The output folder chosen on the home screen is remembered.

### Removed
- The post-download conversion card (FFmpeg already produces the final MP4/MP3 during download).
- All leftover references to `imageio-ffmpeg`; the outdated `INTEGRATION_GUIDE.md`.

---

## 1.0.1

### Fixed
- The YouTube player-client list was passed in a form yt-dlp ignored.
- History and conversion recorded the pre-processing file name (e.g. `.webm` instead of `.mp3`).
- Conversion ignored the FFmpeg folder set in Settings.
- Duplicate URLs got stuck as "Pending" in the queue.
- The "Retry Failed" button was never connected.

---

## 1.0.0

First release: batch downloads with yt-dlp, video/audio modes, queue and history tabs,
settings, and a Windows installer.
