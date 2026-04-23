# YouTube Batch Downloader

A production-ready desktop app for batch-downloading YouTube videos and audio.
Built with Python, CustomTkinter, yt-dlp, and FFmpeg (bundled — no install needed).

---

## Project Structure

```
ytdl_app/
├── main.py                   ← Entry point
├── app.py                    ← Root CTk window, bootstraps all layers
├── ffmpeg_manager.py         ← FFmpeg resolver + conversion API (imageio-ffmpeg)
├── conversion_worker.py      ← Threaded post-download conversion engine
├── requirements.txt
├── build.spec                ← PyInstaller build spec (bundles FFmpeg)
├── build_windows.bat         ← One-click Windows build script
├── installer.iss             ← Inno Setup script for .exe installer
│
├── engine/
│   ├── __init__.py
│   └── downloader.py         ← yt-dlp wrapper, DownloadWorker thread
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py        ← Sidebar + content area assembly
│   ├── sidebar.py            ← Navigation rail
│   ├── dialogs.py            ← FFmpeg warning, per-video format picker
│   ├── tab_downloader.py     ← URL input, progress, log, conversion panel
│   ├── tab_batch_queue.py    ← Live queue status table
│   ├── tab_history.py        ← Past downloads viewer
│   └── tab_settings.py       ← User preferences
│
└── utils/
    ├── __init__.py
    ├── logger.py             ← Rotating file + console logger
    ├── ffmpeg_checker.py     ← Legacy FFmpeg PATH detection (fallback only)
    ├── history_manager.py    ← Thread-safe JSON persistence
    ├── settings_manager.py   ← JSON-backed settings with defaults
    ├── url_validator.py      ← URL pre-validation before yt-dlp
    ├── thumbnail_fetcher.py  ← Async YouTube thumbnail loader
    └── update_checker.py     ← Background yt-dlp version checker
```

---

## Installation

### 1. Python 3.11+

```bash
python --version
```

### 2. Install Python dependencies (FFmpeg is included)

```bash
pip install -r requirements.txt
```

`imageio-ffmpeg` ships a **pre-built static FFmpeg binary** for Windows,
macOS, and Linux. No separate FFmpeg installation is required.

### 3. Run the app

```bash
python main.py
```

That's it. FFmpeg is resolved automatically at startup via `ffmpeg_manager.py`.

---

## FFmpeg Integration

FFmpeg is provided by the `imageio-ffmpeg` Python package, which bundles a
static build of FFmpeg for each platform. The resolution order at runtime is:

| Priority | Strategy | Notes |
|----------|----------|-------|
| 1 | `imageio_ffmpeg.get_ffmpeg_exe()` | Bundled binary — always preferred |
| 2 | PyInstaller `_MEIPASS` bundle | For frozen/distributed builds |
| 3 | `shutil.which("ffmpeg")` | System PATH — last resort fallback |

The resolved FFmpeg path is injected into `os.environ["PATH"]` so that
`yt-dlp`'s subprocess calls also find it automatically.

---

## Features

| Feature | Detail |
|---|---|
| Batch URL input | Paste multiple URLs, one per line |
| Video mode | Best quality (4K/8K), MP4 / MKV / WEBM selectable per-video |
| Audio mode | Best audio → MP3 @ 192 kbps via FFmpeg |
| Post-download conversion | Convert to MP3, WAV, MP4, or M4A after download |
| Per-video format dialog | Prompts before each video download |
| Sequential processing | One at a time for maximum stability |
| Live progress | Progress bar, %, speed, ETA |
| Activity log | Scrollable in-app console |
| Batch queue tab | Live status: Pending / Downloading / Completed / Failed |
| History tab | Persistent JSON history with open-folder shortcut |
| Zero FFmpeg setup | Bundled via imageio-ffmpeg — nothing for users to install |
| Error resilience | Failed URLs are logged and skipped; batch continues |
| Cancel support | Graceful cancellation between downloads |

---

## Building a Distributable (.exe)

```bat
build_windows.bat
```

This script:
1. Creates a virtual environment
2. Installs all dependencies including `imageio-ffmpeg`
3. Verifies the bundled FFmpeg binary is accessible
4. Runs PyInstaller with `build.spec` to produce `dist\YTBatchDownloader\`

To wrap into a single installer `.exe`, open `installer.iss` in
[Inno Setup](https://jrsoftware.org/isinfo.php) and press F9.

**The output installer does not require FFmpeg to be pre-installed on
the target machine.**

---

## Data Storage

All app data is stored in `~/.ytdl_app/`:
- `download_history.json` — persistent download records
- `settings.json` — user preferences
- `logs/app.log` — rotating log file (5 MB × 3 backups)

Default download output: `~/Downloads/YTBatchDL/`

---

## Architecture Notes

- **No global mutable state** — all state flows through class instances
- **Threading** — `DownloadWorker` and `ConversionWorker` are daemon threads; UI updates use `widget.after()`
- **yt-dlp callbacks** — `progress_hooks` feeds real-time data to the UI without polling
- **FFmpeg** — resolved once at startup, path cached and injected into `os.environ["PATH"]`
- **History** — `HistoryManager` uses a `threading.Lock` for safe concurrent writes
- **Logging** — Child loggers under `ytdl.*` namespace; file + console handlers on root
