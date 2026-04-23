# FFmpeg Integration Guide
## Self-Contained FFmpeg via `imageio-ffmpeg`

---

## Overview

This enhancement replaces the manual `FFmpegChecker` approach with a fully
self-contained FFmpeg solution using `imageio-ffmpeg`. End users **no longer
need to install FFmpeg manually** — the correct binary is automatically
provided by the Python package.

---

## New Files

| File | Purpose |
|------|---------|
| `ffmpeg_manager.py` | Core FFmpeg resolver + conversion API |
| `conversion_worker.py` | Threaded conversion engine with callback signals |

## Modified Files

| File | What Changed |
|------|-------------|
| `app.py` | Calls `ffmpeg_manager.get_ffmpeg_path()` instead of `FFmpegChecker` |
| `engine/downloader.py` | `_build_opts()` auto-injects managed FFmpeg path |
| `ui/tab_downloader.py` | New "Post-download Conversion" panel |
| `build.spec` | Includes `imageio_ffmpeg` data directory |
| `requirements.txt` | Added `imageio-ffmpeg>=0.4.9` |

---

## Architecture

```
app.py
  └─ ffmpeg_manager.get_ffmpeg_path()
       └─ imageio_ffmpeg.get_ffmpeg_exe()   ← bundled binary
            ↓ (path injected into os.environ["PATH"])
  └─ settings.set("_ffmpeg_location", dir)
       ↓
engine/downloader.py
  └─ DownloadEngine._build_opts()
       └─ ffmpeg_location → yt-dlp option   ← yt-dlp finds ffmpeg

ui/tab_downloader.py
  └─ [Post-download Conversion panel]
       └─ ConversionWorker (conversion_worker.py)
            └─ ffmpeg_manager.convert_file()
                 └─ subprocess: ffmpeg -y -i <in> ... <out>
                      ↑ path from get_ffmpeg_path()
```

---

## Drop-in Installation

### 1. Install the new dependency

```bash
pip install imageio-ffmpeg
# or update all deps:
pip install -r requirements.txt
```

### 2. Copy new modules to your project root

```
ytdl_app/
  ffmpeg_manager.py        ← NEW
  conversion_worker.py     ← NEW
  app.py                   ← REPLACE
  engine/downloader.py     ← REPLACE
  ui/tab_downloader.py     ← REPLACE
  build.spec               ← REPLACE
  requirements.txt         ← REPLACE
```

The `utils/ffmpeg_checker.py` file is **kept intact** as a fallback — if
`imageio-ffmpeg` is not installed, `app.py` automatically falls back to the
legacy checker with no code changes required.

---

## `ffmpeg_manager.py` Public API

### `get_ffmpeg_path() -> str`

Returns the absolute path to the FFmpeg executable. Resolution order:

1. **`imageio_ffmpeg.get_ffmpeg_exe()`** — bundled static binary (preferred)
2. **`shutil.which("ffmpeg")`** — system PATH fallback
3. **PyInstaller `_MEIPASS`** — frozen bundle fallback

Raises `FFmpegNotFoundError` if no binary is found.

```python
from ffmpeg_manager import get_ffmpeg_path

ffmpeg = get_ffmpeg_path()
print(ffmpeg)
# → /path/to/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux64-v7.0
```

---

### `convert_to_mp3(input_file, output_file, *, bitrate, on_progress, on_log)`

```python
from ffmpeg_manager import convert_to_mp3

convert_to_mp3(
    "/tmp/video.webm",
    "/tmp/audio.mp3",
    bitrate="192k",
    on_progress=lambda pct, t: print(f"{pct:.0f}% at {t}"),
    on_log=print,
)
```

---

### `convert_file(input_file, output_file, *, output_format, bitrate, ...)`

Dispatcher supporting `"mp3"`, `"wav"`, `"mp4"`, `"m4a"`:

```python
from ffmpeg_manager import convert_file

convert_file("/tmp/video.mp4", "/tmp/audio.wav", output_format="wav")
```

---

### `detect_format(filepath) -> str`

```python
from ffmpeg_manager import detect_format

fmt = detect_format("/tmp/video.webm")   # → "webm"
```

---

### `cleanup_temp_file(filepath)`

```python
from ffmpeg_manager import cleanup_temp_file

cleanup_temp_file("/tmp/intermediate.webm")   # deletes if exists, silent on error
```

---

## `conversion_worker.py` — Threaded Conversion

```python
from conversion_worker import ConversionRequest, ConversionWorker

req = ConversionRequest(
    input_file="/tmp/music.webm",
    output_file="/tmp/music.mp3",
    output_format="mp3",
    bitrate="320k",
    delete_source=True,   # delete the .webm after successful conversion
)

worker = ConversionWorker(
    requests=[req],
    on_progress=lambda pct, t: widget.after(0, update_bar, pct),
    on_item_done=lambda r: widget.after(0, on_done, r),
    on_log=lambda msg: widget.after(0, log_ui, msg),
    on_all_done=lambda: widget.after(0, on_all_finished),
)
worker.start()
```

> **Thread safety:** All callbacks are invoked from the worker thread.
> Wrap any Tkinter widget updates in `widget.after(0, fn, *args)`.

---

## PyInstaller Packaging

### Method 1: One-file build (simplest)

```bash
pyinstaller --onefile --collect-all imageio_ffmpeg main.py
```

### Method 2: Folder build using the updated `build.spec`

```bash
pyinstaller build.spec --clean
```

The updated `build.spec` automatically:
- Detects the `imageio_ffmpeg` package directory
- Adds it to `datas` so the FFmpeg binary is bundled
- Adds `imageio_ffmpeg` to `hiddenimports`

### Runtime resolution in frozen builds

`imageio_ffmpeg.get_ffmpeg_exe()` handles `_MEIPASS` natively — it will find
the binary inside the extracted bundle without any extra configuration.

---

## GUI Changes: Post-Download Conversion Panel

The updated `tab_downloader.py` adds a collapsible panel at the bottom of
the download controls:

```
┌──────────────────────────────────────────────────────────────────┐
│ 🔄  Post-download Conversion  (powered by imageio-ffmpeg)  [OFF] │
└──────────────────────────────────────────────────────────────────┘
```

When toggled ON:

```
┌──────────────────────────────────────────────────────────────────┐
│ 🔄  Post-download Conversion  (powered by imageio-ffmpeg)  [ON]  │
│                                                                  │
│  Format:  [mp3] [wav] [mp4] [m4a]                               │
│  Bitrate: [128k] [192k] [256k] [320k]                           │
│  ☐ Delete source after conversion                               │
└──────────────────────────────────────────────────────────────────┘
```

After all downloads complete, `ConversionWorker` is automatically launched
for each successfully downloaded file. Progress is shown in the same bar and
log widget as downloads.

---

## Error Handling Summary

| Exception | When raised |
|-----------|------------|
| `FFmpegNotFoundError` | `imageio-ffmpeg` not installed AND no system FFmpeg |
| `FFmpegConversionError` | FFmpeg process exits non-zero; includes `returncode` + `stderr` |
| `FileNotFoundError` | Input file does not exist |
| `ValueError` | Unsupported output format string |

---

## Backward Compatibility

- `utils/ffmpeg_checker.py` is **untouched** — used as automatic fallback
- `DownloadRequest.ffmpeg_location` field still works as before
- All existing download logic is preserved; only `_build_opts()` has a small
  addition to source the path from `ffmpeg_manager` when no explicit path
  is set
