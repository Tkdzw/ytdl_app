# YT Downloader

**Version 2.1.1** · by Asher Naison · see [CHANGELOG.md](CHANGELOG.md)

A desktop app for batch-downloading YouTube videos and audio, built for
everyday users. Built with Python, CustomTkinter, yt-dlp, FFmpeg and Deno.

---

## Project Structure

```
ytdl_app/
├── main.py                   ← Entry point
├── app.py                    ← Root CTk window; tool detection + setup dialog
├── app_info.py               ← App name, version, developer (single source of truth)
├── ffmpeg_manager.py         ← FFmpeg version lookup (About dialog)
├── js_runtime_manager.py     ← Finds Node.js / Deno / Bun / QuickJS
├── requirements.txt
├── build.spec                ← PyInstaller spec (bundles vendor/ffmpeg + vendor/deno)
├── build_windows.bat         ← One-click Windows build
├── installer.iss             ← Inno Setup script for the .exe installer
├── scripts/
│   └── fetch_tools.ps1       ← Downloads + SHA-256-verifies FFmpeg and Deno into vendor/
│
├── engine/
│   ├── downloader.py         ← yt-dlp wrapper (format choice, cancel, progress)
│   ├── download_queue.py     ← Thread-safe queue + worker that drains it
│   └── playlist.py           ← Detect + list playlist/channel links (yt-dlp flat mode)
│
├── ui/
│   ├── main_window.py        ← Sidebar + content area assembly
│   ├── sidebar.py            ← Navigation rail
│   ├── tab_downloader.py     ← Home screen: links, options, download list, progress
│   ├── queue_list.py         ← Download list rows with per-item actions
│   ├── setup_dialog.py       ← "Finish setting up" — installs FFmpeg/Deno via WinGet
│   ├── dialogs.py            ← Per-video format picker, About
│   ├── theme.py              ← Light/dark colour tokens (contrast-checked) + CTk overrides
│   ├── tooltip.py            ← Hover/focus tooltips
│   ├── tab_history.py        ← Past downloads viewer
│   └── tab_settings.py       ← User preferences
│
└── utils/
    ├── tool_setup.py         ← Locate / install FFmpeg + JS runtime
    ├── error_messages.py     ← Plain-language error messages
    ├── logger.py             ← Rotating file + console logger
    ├── history_manager.py    ← Thread-safe JSON persistence
    ├── settings_manager.py   ← JSON-backed settings with defaults + migrations
    ├── url_validator.py      ← URL pre-validation
    ├── thumbnail_fetcher.py  ← Title (oEmbed) + thumbnail previews
    └── update_checker.py     ← Background yt-dlp version checker
```

---

## Running from source

```bash
pip install -r requirements.txt
python main.py
```

Python 3.11+. If FFmpeg or a JavaScript runtime is missing, the app opens a
**Finish setting up** window that installs them for you (see below). To use
bundled copies instead, run `scripts\fetch_tools.ps1` once — the app picks up
`vendor\ffmpeg` and `vendor\deno` automatically.

---

## Helper tools (FFmpeg + JavaScript runtime)

| Tool | Why | Required? |
|---|---|---|
| FFmpeg | Joins video + audio, converts to MP3 | Yes |
| Deno (or Node.js ≥ 20, Bun, QuickJS) | yt-dlp needs it to read most YouTube videos | Strongly recommended |

**Where the app looks** (first hit wins), in `utils/tool_setup.py`:

1. The folder / file chosen in **Settings › Tools**
2. Copies bundled with the app (`_internal\tools\` in the installed app, `vendor\` in a source checkout)
3. The system PATH — re-read from the registry, so tools installed while the app runs are found
4. Well-known locations (WinGet, Scoop, Chocolatey, Homebrew…)

**Existing installs / source runs:** if something is missing, the setup window
offers **Install**, which runs WinGet (built into Windows 10/11) from the
official `winget` source:

| Tool | WinGet package | Notes |
|---|---|---|
| FFmpeg | `yt-dlp.FFmpeg` | FFmpeg build maintained by the yt-dlp project; per-user, no admin |
| Deno | `DenoLand.Deno` | yt-dlp's default JS runtime; per-user, no admin |

Nothing is installed unless the user clicks Install. After installing, the
app re-detects the tools and enables downloads immediately — no restart.
Without WinGet, the window links to the download pages and lets the user pick
the FFmpeg folder.

**New installs:** the installer already contains both tools (next section).

---

## Features

| Feature | Detail |
|---|---|
| Download list on the home screen | Paste links → each becomes a row with title, thumbnail, length and status |
| Simple choices | Download: Video (MP4) / Audio (MP3); Quality: Best / 1080p / 720p / 480p or 128–320 kbps |
| Device-friendly video | Capped qualities prefer H.264 MP4, which plays almost everywhere |
| Per-row actions | Remove, Stop, Retry, Play, Open folder, Details |
| Playlists & channels | Expanded into one row per video (asks before adding more than 150); a video link inside a playlist asks “just this video or the whole playlist?” |
| Add while downloading | New links join the running batch automatically |
| Instant Stop | Stops the current download within about a second and removes partial files; waiting items stay queued |
| Overall progress | "3 of 10 done · about 5 min left" plus a batch progress bar |
| Finish banner | Summary with Open folder / Play, a sound, and a flashing taskbar button |
| Plain-language errors | e.g. "This video is private." with what to do next; technical text under Details |
| Guided setup | Detects / installs FFmpeg and Deno; "Fix" chip on the home screen |
| History tab | Persistent JSON history with search, filter, CSV export |
| Keyboard | Ctrl+V (outside text boxes) adds clipboard links · Ctrl+Enter starts · Ctrl+L link box · Ctrl+1/2/3 tabs · Esc closes dialogs |
| Simple Settings | Everyday options first; retries, speed limit, proxy and tool paths under a collapsed “Advanced”; hover/focus tooltips on every option |
| Readable in light & dark | Theme follows Windows by default; all text ≥ 12 px and ≥ 4.5:1 contrast (WCAG AA) — colours live in `ui/theme.py`; status always shown in words + symbol, not colour alone |

---

## Building a Distributable (.exe)

```bat
build_windows.bat
```

This script:
1. Creates a virtual environment and installs dependencies (plus PyInstaller)
2. Runs `scripts\fetch_tools.ps1`, which downloads FFmpeg (`yt-dlp/FFmpeg-Builds`)
   and Deno (`denoland/deno`) from their official GitHub releases and checks each
   archive against the publisher's SHA-256 checksum — the build stops on any mismatch
3. Runs PyInstaller with `build.spec` → `dist\YTDownloader\` (tools under `_internal\tools\`)

To wrap into a single installer `.exe`, open `installer.iss` in
[Inno Setup](https://jrsoftware.org/isinfo.php) and press F9.

**Licensing:** the bundled FFmpeg build is GPL-licensed and Deno is MIT. Their
license files are copied next to the binaries; if you distribute the installer,
keep them and link to the FFmpeg source (as the GPL requires).

---

## Data Storage

All app data is stored in `~/.ytdl_app/`:
- `download_history.json` — persistent download records
- `settings.json` — user preferences
- `logs/app.log` — rotating log file (5 MB × 3 backups)

Default download output: `~/Downloads/YTBatchDL/` (folder name kept from 1.x so existing downloads stay in one place)

---

## Architecture Notes

- **Queue** — `DownloadQueue` holds all items behind one lock; `QueueWorker` (daemon thread) pulls the next Ready item, so the UI can add/remove/retry at any time
- **Cancel** — the progress hook raises `yt_dlp.utils.DownloadCancelled`, yt-dlp's supported abort
- **Threading** — all worker callbacks are marshalled to Tk with `widget.after()`; Tk images are created on the main thread
- **Tools** — `utils/tool_setup.detect_tools()` writes `_ffmpeg_location` / `_js_runtime_*` settings that each download reads
- **History** — `HistoryManager` uses a `threading.Lock` for safe concurrent writes
- **Logging** — Child loggers under `ytdl.*` namespace; file + console handlers on root
