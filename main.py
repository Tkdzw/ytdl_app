"""
YT Downloader - Main Entry Point
"""
import sys
import os

# Ensure the app directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import YTDownloaderApp


def main() -> None:
    """Application entry point."""
    app = YTDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
