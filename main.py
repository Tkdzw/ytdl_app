"""
YouTube Batch Downloader - Main Entry Point
"""
import sys
import os

# Ensure the app directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import YouTubeBatchDownloader


def main() -> None:
    """Application entry point."""
    app = YouTubeBatchDownloader()
    app.mainloop()


if __name__ == "__main__":
    main()
