@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: build_windows.bat  —  One-click build for YT Batch Downloader on Windows
:: Run this from the ytdl_app\ folder (where main.py lives):
::   build_windows.bat
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

:: ── Check / activate venv ────────────────────────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    echo [OK] Activating existing venv...
    call venv\Scripts\activate.bat
) else (
    echo [..] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
)

:: ── Install / upgrade dependencies ───────────────────────────────────────────
echo [..] Installing dependencies...
pip install --upgrade pip --quiet
pip install pyinstaller customtkinter yt-dlp Pillow --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause & exit /b 1
)
echo [OK] Dependencies installed.

:: ── Clean old build artifacts ─────────────────────────────────────────────────
echo [..] Cleaning previous build...
if exist "dist\YTBatchDownloader" rmdir /s /q "dist\YTBatchDownloader"
if exist "build\build"           rmdir /s /q "build\build"

:: ── Run PyInstaller ───────────────────────────────────────────────────────────
echo [..] Running PyInstaller...
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. See output above.
    pause & exit /b 1
)

:: ── Result ────────────────────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║  Build complete!                                         ║
echo  ║  Executable:  dist\YTBatchDownloader\YTBatchDownloader.exe  ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.
echo  Tip: Share the entire dist\YTBatchDownloader\ folder,
echo       or use Inno Setup to wrap it into a single .exe installer.
echo.
pause
