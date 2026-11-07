"""
Engine: thread-safe download queue + the worker that drains it.

The UI adds, removes and retries items at any time; the worker pulls the
next "Ready" item whenever it finishes one. That means:

* links added while a batch is running are picked up automatically,
* a single row can be cancelled or removed without stopping the rest,
* Cancel stops the current download immediately (within a progress tick).
"""
from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from engine.downloader import DownloadEngine, DownloadRequest, DownloadResult, ProgressData
from utils.error_messages import friendly_error
from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

READY = "Ready"
DOWNLOADING = "Downloading"
COMPLETED = "Completed"
FAILED = "Failed"
CANCELLED = "Cancelled"

FINISHED_STATES = (COMPLETED, FAILED, CANCELLED)


@dataclass
class QueueItem:
    id: int
    request: DownloadRequest
    status: str = READY
    title: str = ""                 # filled from oEmbed / yt-dlp as it becomes known
    duration: Optional[float] = None
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    eta_seconds: Optional[float] = None
    stage: str = ""                 # "" while downloading, "processing" during FFmpeg
    error: str = ""                 # plain-language message
    hint: str = ""                  # what the user can do about it
    error_detail: str = ""          # raw technical message
    filepaths: list[str] = field(default_factory=list)
    cancel_requested: bool = False
    remove_when_cancelled: bool = False
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def display_title(self) -> str:
        return self.title or self.request.url


class DownloadQueue:
    """All queue state lives here, guarded by one lock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: list[QueueItem] = []
        self._ids = itertools.count(1)

    # ── Reading ───────────────────────────────────────────────────────────────

    def items(self) -> list[QueueItem]:
        with self._lock:
            return list(self._items)

    def get(self, item_id: int) -> Optional[QueueItem]:
        with self._lock:
            return next((i for i in self._items if i.id == item_id), None)

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts = {s: 0 for s in (READY, DOWNLOADING, COMPLETED, FAILED, CANCELLED)}
            for i in self._items:
                counts[i.status] += 1
            counts["total"] = len(self._items)
            return counts

    def has_work(self) -> bool:
        with self._lock:
            return any(i.status == READY for i in self._items)

    # ── Editing ───────────────────────────────────────────────────────────────

    def add(self, request: DownloadRequest, title: str = "") -> QueueItem:
        with self._lock:
            item = QueueItem(id=next(self._ids), request=request, title=title)
            self._items.append(item)
            return item

    def remove(self, item_id: int) -> bool:
        """Remove a row. A row that is downloading is cancelled first and
        disappears once the worker has stopped it."""
        with self._lock:
            item = self.get(item_id)
            if not item:
                return False
            if item.status == DOWNLOADING:
                item.cancel_requested = True
                item.remove_when_cancelled = True
                return True
            self._items.remove(item)
            return True

    def cancel(self, item_id: int) -> None:
        with self._lock:
            item = self.get(item_id)
            if item and item.status == DOWNLOADING:
                item.cancel_requested = True
            elif item and item.status == READY:
                item.status = CANCELLED

    def retry(self, item_id: int) -> bool:
        with self._lock:
            item = self.get(item_id)
            if not item or item.status not in (FAILED, CANCELLED):
                return False
            self._reset(item)
            return True

    def retry_failed(self) -> int:
        with self._lock:
            failed = [i for i in self._items if i.status in (FAILED, CANCELLED)]
            for item in failed:
                self._reset(item)
            return len(failed)

    def clear_finished(self) -> int:
        with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if i.status not in FINISHED_STATES]
            return before - len(self._items)

    @staticmethod
    def _reset(item: QueueItem) -> None:
        item.status = READY
        item.percent = 0.0
        item.speed = item.eta = item.stage = ""
        item.eta_seconds = None
        item.error = item.hint = item.error_detail = ""
        item.cancel_requested = item.remove_when_cancelled = False

    # ── Worker side ───────────────────────────────────────────────────────────

    def take_next(self) -> Optional[QueueItem]:
        with self._lock:
            for item in self._items:
                if item.status == READY:
                    item.status = DOWNLOADING
                    item.cancel_requested = False
                    item.started_at = time.monotonic()
                    return item
            return None

    def finish(self, item: QueueItem, result: DownloadResult) -> None:
        with self._lock:
            item.finished_at = time.monotonic()
            item.speed = item.eta = item.stage = ""
            item.eta_seconds = None
            if result.title and result.title != item.request.url:
                item.title = result.title
            if result.success:
                item.status = COMPLETED
                item.percent = 100.0
                item.filepaths = result.filepaths or ([result.filepath] if result.filepath else [])
            elif result.cancelled:
                item.status = CANCELLED
                item.percent = 0.0
                if item.remove_when_cancelled and item in self._items:
                    self._items.remove(item)
            else:
                item.status = FAILED
                friendly = friendly_error(result.error_message)
                item.error, item.hint = friendly.message, friendly.hint
                item.error_detail = result.error_message

    def cancel_all_running(self) -> None:
        with self._lock:
            for item in self._items:
                if item.status == DOWNLOADING:
                    item.cancel_requested = True


class QueueWorker(threading.Thread):
    """
    Drains a DownloadQueue one item at a time. All callbacks run on this
    thread — the UI must marshal them onto the Tk thread with ``after``.
    """

    def __init__(
        self,
        queue: DownloadQueue,
        on_item_start: Optional[Callable[[QueueItem], None]] = None,
        on_progress: Optional[Callable[[QueueItem, ProgressData], None]] = None,
        on_item_done: Optional[Callable[[QueueItem, DownloadResult], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_all_done: Optional[Callable[[bool], None]] = None,
    ) -> None:
        super().__init__(daemon=True, name="QueueWorker")
        self._queue = queue
        self._on_item_start = on_item_start
        self._on_progress = on_progress
        self._on_item_done = on_item_done
        self._on_log = on_log
        self._on_all_done = on_all_done
        self._engine = DownloadEngine()
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Stop now: cancels the running download; Ready items stay queued."""
        self._stop_event.set()
        self._queue.cancel_all_running()

    @property
    def is_cancelled(self) -> bool:
        return self._stop_event.is_set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            item = self._queue.take_next()
            if item is None:
                break
            if self._on_item_start:
                self._on_item_start(item)
            _log.info("Starting #%d: %s [%s]", item.id, item.request.url, item.request.mode)

            def progress(data: ProgressData, item: QueueItem = item) -> None:
                item.percent = data.percent
                item.speed, item.eta = data.speed, data.eta
                item.eta_seconds = data.eta_seconds
                item.stage = "processing" if data.status == "finished" else ""
                if data.title and not item.title:
                    item.title = data.title
                if data.duration and not item.duration:
                    item.duration = data.duration
                if self._on_progress:
                    self._on_progress(item, data)

            result = self._engine.download(
                item.request,
                on_progress=progress,
                on_log=self._on_log,
                cancel_check=lambda item=item: item.cancel_requested or self._stop_event.is_set(),
            )
            self._queue.finish(item, result)
            if self._on_item_done:
                self._on_item_done(item, result)

        if self._on_all_done:
            self._on_all_done(self._stop_event.is_set())
