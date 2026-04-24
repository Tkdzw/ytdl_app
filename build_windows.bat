@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: build_windows.bat  —  One-click build for YT Batch Downloader on Windows
:: Run from the ytdl_app\ folder:  build_windows.bat
::
:: FFmpeg is NOT bundled. Users install it separately and set the path in
:: Settings > Tools, or add it to their system PATH.
:: ─────────────────────────────────────────────────────────────────────────────
setlocal EnableDelayedExpansion

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   YT Batch Downloader  —  Windows Build  ║
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

:: ── Check Node.js ────────────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] Node.js not found — YouTube downloads may fail without it.
    echo        Install: winget install OpenJS.NodeJS
) else (
    for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo [OK] Node.js %%v
)

:: ── Clean previous build ─────────────────────────────────────────────────────
echo [..] Cleaning previous build...
if exist "dist\YTBatchDownloader" rmdir /s /q "dist\YTBatchDownloader"
if exist "build\YTBatchDownloader" rmdir /s /q "build\YTBatchDownloader"

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
echo  ║  Executable: dist\YTBatchDownloader\YTBatchDownloader.exe     ║
echo  ║                                                                ║
echo  ║  NOTE: Users must install FFmpeg separately.                   ║
echo  ║  Set the bin folder in the app: Settings ^> Tools              ║
echo  ╚════════════════════════════════════════════════════════════════╝
echo.
pause
