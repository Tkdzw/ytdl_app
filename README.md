# YouTube Batch Downloader

A production-ready desktop app for batch-downloading YouTube videos and audio.
Built with Python, CustomTkinter, yt-dlp, and FFmpeg.

---

## Project Structure

```
ytdl_app/
├── main.py                   ← Entry point
├── app.py                    ← Root CTk window, bootstraps all layers
├── requirements.txt
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
│   ├── tab_downloader.py     ← URL input, progress, log
│   ├── tab_batch_queue.py    ← Live queue status table
│   └── tab_history.py        ← Past downloads viewer
│
└── utils/
    ├── __init__.py
    ├── logger.py             ← Rotating file + console logger
    ├── ffmpeg_checker.py     ← FFmpeg PATH detection
    └── history_manager.py    ← Thread-safe JSON persistence
```

---

## Installation

### 1. Python 3.11+ (also works on 3.14)

```bash
python --version
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install FFmpeg

**Windows:**
```
winget install ffmpeg
# or download from https://ffmpeg.org/download.html and add to PATH
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt install ffmpeg
```

Verify installation:
```bash
ffmpeg -version
```

### 4. Run the app

```bash
python main.py
```

---

## Features

| Feature | Detail |
|---|---|
| Batch URL input | Paste multiple URLs, one per line |
| Video mode | Best quality (4K/8K), MP4 / MKV / WEBM selectable per-video |
| Audio mode | Best audio → MP3 @ 192 kbps via FFmpeg |
| Per-video format dialog | Prompts before each video download |
| Sequential processing | One at a time for maximum stability |
| Live progress | Progress bar, %, speed, ETA |
| Activity log | Scrollable in-app console |
| Batch queue tab | Live status: Pending / Downloading / Completed / Failed |
| History tab | Persistent JSON history with open-folder shortcut |
| FFmpeg guard | Startup check — disables downloads if FFmpeg missing |
| Error resilience | Failed URLs are logged and skipped; batch continues |
| Cancel support | Graceful cancellation between downloads |

---

## Data Storage

All app data is stored in `~/.ytdl_app/`:
- `download_history.json` — persistent download records
- `logs/app.log` — rotating log file (5 MB × 3 backups)

Default download output: `~/Downloads/YTBatchDL/`

---

## Architecture Notes

- **No global mutable state** — all state flows through class instances
- **Threading** — `DownloadWorker` is a daemon thread; UI updates use `widget.after()`
- **yt-dlp callbacks** — `progress_hooks` feeds real-time data to the UI without polling
- **History** — `HistoryManager` uses a threading.Lock for safe concurrent writes
- **Logging** — Child loggers under `ytdl.*` namespace; file + console handlers on root
