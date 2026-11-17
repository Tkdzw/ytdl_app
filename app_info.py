"""
Single source of truth for the app's name, version and credits.

Everything that shows a name or version (window title, sidebar, About
window, the .exe's file properties via build.spec) reads it from here.
installer.iss can't import Python, so keep its AppVersion in step —
see CHANGELOG.md.
"""

APP_NAME = "YT Downloader"
APP_ID = "YTDownloader"                  # file/exe-safe name
VERSION = "2.3.0"                        # semantic versioning: MAJOR.MINOR.PATCH
RELEASE_DATE = "2026-11-17"

# ── Release codenames ─────────────────────────────────────────────────────────
# Each MINOR release gets a bird's name, in alphabetical order (like Android's
# desserts); patch releases keep their minor release's name (2.1.1 = Dunlin).
# For a new minor release, add the next name from _NEXT_CODENAMES here.
CODENAMES = {
    "1.0": "Albatross",
    "1.1": "Bluejay",
    "2.0": "Crane",
    "2.1": "Dunlin",
    "2.2": "Eagle",
    "2.3": "Falcon",
}
_NEXT_CODENAMES = ["Goshawk", "Heron", "Ibis", "Jacana", "Kestrel", "Lark", "Magpie",
                   "Nightjar", "Osprey", "Puffin", "Quail", "Raven", "Swift", "Tern"]


def codename_for(version: str) -> str:
    """'2.1.1' -> 'Dunlin'; '' when the release has no name."""
    return CODENAMES.get(".".join(version.split(".")[:2]), "")


CODENAME = codename_for(VERSION)
# "2.3.0 “Falcon”": how the version is shown in the app
DISPLAY_VERSION = f"{VERSION} “{CODENAME}”" if CODENAME else VERSION
DEVELOPER = "Asher Naison"
GITHUB_REPO = "Tkdzw/ytdl_app"           # in-app updates come from its releases
COPYRIGHT = f"© 2026 {DEVELOPER}"
DESCRIPTION = "Download videos and music from YouTube and other sites."
CREDITS = "Built with yt-dlp, FFmpeg, Deno and CustomTkinter."

# Short highlights for the About window's "What's new" (full list: CHANGELOG.md)
WHATS_NEW = [
    "Update the app from inside the app: Settings → Updates (new in 2.3)",
    "Faster downloads: each video downloads over several connections at once (new in 2.2)",
    "Download several videos at the same time, with automatic slow-down if YouTube says there are too many requests (new in 2.2)",
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
