@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: build_windows.bat  —  One-click build for YT Downloader on Windows
:: Run from the ytdl_app\ folder:  build_windows.bat
::
:: FFmpeg and Deno are downloaded (checksum-verified) and bundled into the
:: app, so installed copies work without any extra setup.
:: ─────────────────────────────────────────────────────────────────────────────
setlocal EnableDelayedExpansion

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   YT Downloader 2.1.1  —  Windows Build  ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

:: ── Create / activate venv ───────────────────────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    echo [OK] Activating existing venv...
    call venv\Scripts\activate.bat
) else (
    echo [..] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
)

:: ── Install dependencies ─────────────────────────────────────────────────────
echo [..] Installing dependencies...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause & exit /b 1
)
pip install pyinstaller --quiet
echo [OK] Dependencies installed.

:: ── Bundle FFmpeg + Deno (downloaded from official releases, SHA-256 checked) ──
echo [..] Fetching FFmpeg and Deno into vendor\ ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\fetch_tools.ps1"
if errorlevel 1 (
    echo [ERROR] Could not download or verify FFmpeg/Deno. See messages above.
    pause & exit /b 1
)

:: ── Clean previous build ─────────────────────────────────────────────────────
echo [..] Cleaning previous build...
if exist "dist\YTDownloader" rmdir /s /q "dist\YTDownloader"
if exist "build\YTDownloader" rmdir /s /q "build\YTDownloader"

:: ── Run PyInstaller ──────────────────────────────────────────────────────────
echo [..] Running PyInstaller...
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller failed. See output above.
    pause & exit /b 1
)

echo.
echo  ╔════════════════════════════════════════════════════════════════╗
echo  ║  Build complete!                                               ║
echo  ║  Executable: dist\YTDownloader\YTDownloader.exe               ║
echo  ║                                                                ║
echo  ║  FFmpeg and Deno are bundled in tools\ — no extra setup.        ║
echo  ╚════════════════════════════════════════════════════════════════╝
echo.
pause
