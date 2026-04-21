"""
Utility: Centralised application logger.
All modules obtain a child logger via AppLogger.get_logger().
"""
import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(os.path.expanduser("~"), ".ytdl_app", "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")
_INITIALIZED = False


class AppLogger:
    """Factory for named loggers with file + console output."""

    @classmethod
    def _init_root(cls) -> None:
        global _INITIALIZED
        if _INITIALIZED:
            return
        os.makedirs(_LOG_DIR, exist_ok=True)

        root = logging.getLogger("ytdl")
        root.setLevel(logging.DEBUG)

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s – %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Rotating file handler (5 MB × 3 backups)
        fh = RotatingFileHandler(_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)

        # Console handler (INFO+)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)

        root.addHandler(fh)
        root.addHandler(ch)
        _INITIALIZED = True

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        cls._init_root()
        return logging.getLogger(f"ytdl.{name}")
