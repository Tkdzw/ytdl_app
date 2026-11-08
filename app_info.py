"""
Single source of truth for the app's name, version and credits.

Everything that shows a name or version (window title, sidebar, About
window, the .exe's file properties via build.spec) reads it from here.
installer.iss can't import Python, so keep its AppVersion in step —
see CHANGELOG.md.
"""

APP_NAME = "YT Downloader"
APP_ID = "YTDownloader"                  # file/exe-safe name
VERSION = "2.1.1"                        # semantic versioning: MAJOR.MINOR.PATCH
RELEASE_DATE = "2026-11-08"
DEVELOPER = "Asher Naison"
COPYRIGHT = f"© 2026 {DEVELOPER}"
DESCRIPTION = "Download videos and music from YouTube and other sites."
CREDITS = "Built with yt-dlp, FFmpeg, Deno and CustomTkinter."

# Short highlights for the About window's "What's new" (full list: CHANGELOG.md)
WHATS_NEW = [
    "4K and 1440p YouTube downloads work again (2.1.1)",
    "Playlists: each video gets its own row and progress bar (new in 2.1)",
    "New name: YT Downloader",
    "Your downloads now appear as a list on the home screen, with Play, Open folder and Retry",
    "One-click setup installs FFmpeg and Deno for you (already included in the installer)",
    "Simple Video/Audio and quality choices; 1080p MP4 by default",
    "Stop works instantly; add links while a batch is running",
    "Clear error messages that say what to do next",
    "Overall progress with time left, and a summary when everything finishes",
    "Simpler Settings with explanations, light/dark theme that follows Windows",
    "Keyboard shortcuts: Ctrl+V adds links, Ctrl+Enter starts",
]
