@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: build_windows.bat  —  One-click build for YT Batch Downloader on Windows
:: Run this from the ytdl_app\ folder (where main.py lives):
::   build_windows.bat
::
:: FFmpeg is bundled automatically via imageio-ffmpeg — no manual install needed.
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
echo [..] Installing dependencies (this includes the bundled FFmpeg binary)...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed. Check requirements.txt.
    pause & exit /b 1
)
echo [OK] All dependencies installed (FFmpeg bundled via imageio-ffmpeg).

:: ── Install PyInstaller ───────────────────────────────────────────────────────
pip install pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] Could not install PyInstaller.
    pause & exit /b 1
)
echo [OK] PyInstaller ready.

:: ── Verify imageio-ffmpeg can find its binary ─────────────────────────────────
echo [..] Verifying bundled FFmpeg...
python -c "import imageio_ffmpeg; p = imageio_ffmpeg.get_ffmpeg_exe(); print('[OK] Bundled FFmpeg:', p)"
if errorlevel 1 (
    echo [ERROR] imageio-ffmpeg could not locate its FFmpeg binary.
    echo         Try: pip install --upgrade imageio-ffmpeg
    pause & exit /b 1
)

:: ── Clean old build artifacts ─────────────────────────────────────────────────
echo [..] Cleaning previous build artifacts...
if exist "dist\YTBatchDownloader" rmdir /s /q "dist\YTBatchDownloader"
if exist "build\YTBatchDownloader" rmdir /s /q "build\YTBatchDownloader"

:: ── Run PyInstaller ───────────────────────────────────────────────────────────
echo [..] Running PyInstaller (imageio-ffmpeg binary will be bundled)...
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. Check the output above.
    pause & exit /b 1
)

:: ── Confirm FFmpeg is present in dist ────────────────────────────────────────
echo [..] Verifying FFmpeg in build output...
dir /s /b "dist\YTBatchDownloader\*.exe" 2>nul | findstr /i "ffmpeg" >nul
if errorlevel 1 (
    echo [WARN] ffmpeg.exe not found at top level — it may be inside imageio_ffmpeg\.
    echo        This is normal; imageio_ffmpeg handles path resolution at runtime.
) else (
    echo [OK] ffmpeg.exe detected in dist output.
)

:: ── Result ────────────────────────────────────────────────────────────────────
echo.
echo  ╔════════════════════════════════════════════════════════════════╗
echo  ║  Build complete!                                               ║
echo  ║  Executable: dist\YTBatchDownloader\YTBatchDownloader.exe     ║
echo  ║                                                                ║
echo  ║  FFmpeg is bundled — end users do NOT need to install it.      ║
echo  ╚════════════════════════════════════════════════════════════════╝
echo.
echo  Distribute the entire dist\YTBatchDownloader\ folder,
echo  or run installer.iss with Inno Setup to create a single .exe installer.
echo.
pause
