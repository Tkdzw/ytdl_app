"""
Engine: multi-connection HTTP downloader (IDM-style).

yt-dlp already downloads HLS/DASH *fragments* in parallel
(``concurrent_fragment_downloads``), but a plain HTTP(S) file - which is how
YouTube serves most of its video and audio streams - comes down over a single
connection. Many servers (YouTube's included) cap the speed of each connection,
so one connection rarely fills a fast line.

``ParallelHttpFD`` splits such a file into byte ranges, fetches them over
several connections at once, and writes each piece straight into its place in
one file, so there is nothing to join afterwards. The number of connections is
the same "Parallel connections" setting used for fragments.

Whenever parallel download isn't possible or safe (no Range support, unknown
size, small file, speed limit set, ...) it quietly falls back to yt-dlp's
normal single-connection ``HttpFD``. If a parallel download fails part-way it
also falls back, so the worst case is the old behaviour.

``install()`` registers the class for the http/https protocols.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from typing import Optional

import yt_dlp.downloader as _ytdl_downloader
from yt_dlp.downloader.http import HttpFD
from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import HTTPError, TransportError
from yt_dlp.utils import DownloadCancelled, parse_http_range
from yt_dlp.utils.networking import HTTPHeaderDict

from engine.rate_guard import GUARD, retry_after_seconds
from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

_MIB = 1024 * 1024
# Below this size the set-up cost outweighs any gain.
_MIN_PARALLEL_SIZE = 4 * _MIB
# Pieces are handed out from a queue, so a fast connection simply takes more
# of them. YouTube throttles single requests above ~10 MB, hence the cap.
_MIN_CHUNK = 1 * _MIB
_MAX_CHUNK = 10 * _MIB
_READ_BLOCK = 256 * 1024
_PROGRESS_INTERVAL = 0.5          # seconds between progress reports
_SPEED_WINDOW = 3.0               # seconds of history used for the speed figure
_MAX_429_RETRIES = 4              # per piece, each after a growing cool-down
_TEMP_SUFFIX = ".mc.part"         # distinct from HttpFD's ".part" (see _temp_path)


class _Unsuitable(Exception):
    """This URL can't be fetched in parallel; use the normal downloader."""


class _Failed(Exception):
    """A piece could not be fetched even after retrying."""


class ParallelHttpFD(HttpFD):
    """HttpFD that uses several connections when the server allows it."""

    FD_NAME = "http (multi-connection)"

    def real_download(self, filename, info_dict):
        connections = int(self.params.get("concurrent_fragment_downloads") or 1)
        if not self._can_try_parallel(filename, info_dict, connections):
            return super().real_download(filename, info_dict)

        try:
            total, last_modified = self._probe(info_dict)
        except _Unsuitable as exc:
            _log.debug("Single connection for %s: %s", filename, exc)
            self._wait_out_cooldown(filename, info_dict)
            return super().real_download(filename, info_dict)

        tmp = _temp_path(filename)
        try:
            self._download_parallel(filename, tmp, info_dict, total, connections)
        except DownloadCancelled:
            raise
        except (_Failed, OSError) as exc:
            _remove(tmp)
            self.report_warning(
                f"Multi-connection download failed ({exc}); "
                "retrying over a single connection")
            self._wait_out_cooldown(filename, info_dict)
            return super().real_download(filename, info_dict)

        self.try_rename(tmp, filename)
        if self.params.get("updatetime"):
            info_dict["filetime"] = self.try_utime(filename, last_modified)
        return True

    def _wait_out_cooldown(self, filename, info_dict) -> None:
        """Sit out an HTTP 429 cool-down, still ticking the progress hook so
        the app's Cancel (which raises from the hook) keeps working."""
        while GUARD.cooldown_left() > 0:
            self._hook_progress({"status": "downloading", "downloaded_bytes": 0,
                                 "filename": filename, "speed": None, "eta": None},
                                info_dict)
            time.sleep(min(GUARD.cooldown_left(), 0.5) or 0.05)

    # ── Eligibility ───────────────────────────────────────────────────────────

    def _can_try_parallel(self, filename, info_dict, connections: int) -> bool:
        if connections <= 1 or filename == "-" or hasattr(filename, "write"):
            return False
        if self.params.get("test") or self.params.get("nopart"):
            return False
        # The speed limit is enforced per connection by HttpFD; keep it exact.
        if self.params.get("ratelimit"):
            return False
        if info_dict.get("request_data") is not None:
            return False
        headers = info_dict.get("http_headers") or {}
        if any(k.lower() == "range" for k in headers):
            return False
        # A half-finished single-connection download: let HttpFD resume it.
        if self.params.get("continuedl", True) and os.path.isfile(self.temp_name(filename)):
            return False
        return True

    def _headers(self, info_dict) -> HTTPHeaderDict:
        return HTTPHeaderDict({"Accept-Encoding": "identity"}, info_dict.get("http_headers"))

    def _extensions(self, info_dict) -> dict:
        target = self._get_impersonate_target(info_dict)
        return {"impersonate": target} if target is not None else {}

    def _open_range(self, info_dict, start: int, end: int):
        headers = self._headers(info_dict)
        headers["Range"] = f"bytes={start}-{end}"
        return self.ydl.urlopen(Request(info_dict["url"], None, headers,
                                        extensions=self._extensions(info_dict)))

    def _probe(self, info_dict) -> tuple[int, Optional[str]]:
        """Return (total size, Last-Modified) if the server serves byte ranges."""
        try:
            resp = self._open_range(info_dict, 0, 0)
        except HTTPError as exc:
            if exc.status == 429:
                GUARD.note_429(retry_after_seconds(exc.response.headers))
            raise _Unsuitable(f"probe failed: {exc}") from exc
        except TransportError as exc:
            raise _Unsuitable(f"probe failed: {exc}") from exc
        try:
            if resp.status != 206:
                raise _Unsuitable(f"no range support (HTTP {resp.status})")
            start, end, total = parse_http_range(resp.headers.get("Content-Range"))
            if start != 0 or not total:
                raise _Unsuitable("size unknown")
            if total < _MIN_PARALLEL_SIZE:
                raise _Unsuitable(f"small file ({total} bytes)")
            return total, resp.headers.get("Last-Modified")
        finally:
            resp.close()

    # ── Download ──────────────────────────────────────────────────────────────

    def _download_parallel(self, filename, tmp, info_dict, total, connections) -> None:
        chunk = max(_MIN_CHUNK, min(_MAX_CHUNK, total // (connections * 4)))
        pieces: queue.SimpleQueue = queue.SimpleQueue()
        n_pieces = 0
        for start in range(0, total, chunk):
            pieces.put((start, min(start + chunk, total) - 1))
            n_pieces += 1
        connections = min(connections, n_pieces)

        _remove(tmp)                     # stale leftovers from an earlier attempt
        with open(tmp, "wb") as fh:
            fh.truncate(total)           # reserve the space; pieces fill it in

        self.report_destination(filename)
        self.to_screen(f"[download] Using {connections} connections "
                       f"({n_pieces} pieces of {chunk / _MIB:.1f} MiB)")

        state = _SharedState(connections)
        workers = [
            threading.Thread(target=self._worker, name=f"ytdl-conn-{i}",
                             args=(info_dict, tmp, pieces, state), daemon=True)
            for i in range(connections)
        ]
        start_time = time.time()
        for w in workers:
            w.start()

        history: list[tuple[float, int]] = [(start_time, 0)]
        try:
            while not state.all_done.wait(_PROGRESS_INTERVAL):
                if state.error:
                    break
                now = time.time()
                done = state.downloaded
                history.append((now, done))
                while len(history) > 2 and now - history[0][0] > _SPEED_WINDOW:
                    history.pop(0)
                t0, b0 = history[0]
                speed = (done - b0) / (now - t0) if now > t0 else None
                eta = int((total - done) / speed) if speed else None
                # The app's hook raises DownloadCancelled here to cancel.
                self._hook_progress({
                    "status": "downloading",
                    "downloaded_bytes": done,
                    "total_bytes": total,
                    "tmpfilename": tmp,
                    "filename": filename,
                    "eta": eta,
                    "speed": speed,
                    "elapsed": now - start_time,
                }, info_dict)
        finally:
            state.stop.set()
            for w in workers:
                w.join()

        if state.error:
            raise _Failed(state.error)
        size = os.path.getsize(tmp)
        if state.downloaded != total or size != total:
            raise _Failed(f"got {state.downloaded} of {total} bytes")

        self._hook_progress({
            "status": "finished",
            "downloaded_bytes": total,
            "total_bytes": total,
            "tmpfilename": tmp,
            "filename": filename,
            "elapsed": time.time() - start_time,
        }, info_dict)

    def _worker(self, info_dict, tmp, pieces: queue.SimpleQueue, state: "_SharedState") -> None:
        retries = int(self.params.get("retries") or 0) + 2
        try:
            with open(tmp, "r+b") as fh:
                while not state.stop.is_set():
                    try:
                        start, end = pieces.get_nowait()
                    except queue.Empty:
                        return
                    self._fetch_piece(info_dict, fh, start, end, retries, state)
        except Exception as exc:          # report the first failure, stop the rest
            with state.lock:
                if state.error is None:
                    state.error = str(exc) or type(exc).__name__
            state.stop.set()
        finally:
            state.worker_exited()

    def _fetch_piece(self, info_dict, fh, start, end, retries, state) -> None:
        pos = start
        attempt = 0
        throttled = 0
        while pos <= end:
            # One slot per connection, shared by every download in the app;
            # this also waits out any HTTP 429 cool-down.
            if not GUARD.acquire_connection(state.stop):
                return
            try:
                resp = self._open_range(info_dict, pos, end)
                try:
                    got_start, _, _ = parse_http_range(resp.headers.get("Content-Range"))
                    if resp.status != 206 or got_start != pos:
                        raise _Failed(f"server ignored the byte range (HTTP {resp.status})")
                    while pos <= end:
                        if state.stop.is_set():
                            return
                        block = resp.read(min(_READ_BLOCK, end - pos + 1))
                        if not block:
                            break
                        fh.seek(pos)
                        fh.write(block)
                        pos += len(block)
                        state.add(len(block))
                finally:
                    resp.close()
                if pos <= end:
                    raise TransportError(f"connection closed early at byte {pos}")
            except HTTPError as exc:
                if exc.status == 429:
                    throttled += 1
                    if throttled > _MAX_429_RETRIES:
                        raise _Failed("HTTP 429 Too Many Requests") from exc
                    wait = GUARD.note_429(retry_after_seconds(exc.response.headers))
                    self.report_warning(f"Server says too many requests (HTTP 429); "
                                        f"pausing {wait:.0f}s and using fewer connections")
                    continue          # acquire_connection waits out the cool-down
                # Other 4xx (e.g. an expired link) won't get better by retrying.
                if exc.status < 500:
                    raise _Failed(f"HTTP {exc.status}") from exc
                attempt += 1
                if attempt > retries:
                    raise _Failed(f"bytes {pos}-{end}: {exc}") from exc
                state.stop.wait(min(2 ** attempt, 10))
            except (TransportError, OSError) as exc:
                attempt += 1
                if attempt > retries:
                    raise _Failed(f"bytes {pos}-{end}: {exc}") from exc
                _log.debug("Retrying bytes %d-%d (%d/%d): %s", pos, end, attempt, retries, exc)
                state.stop.wait(min(2 ** attempt, 10))
            finally:
                GUARD.release_connection()


class _SharedState:
    def __init__(self, workers: int) -> None:
        self.lock = threading.Lock()
        self.stop = threading.Event()        # tells workers to give up
        self.all_done = threading.Event()    # set when the last worker exits
        self.downloaded = 0
        self.error: Optional[str] = None
        self._running = workers

    def worker_exited(self) -> None:
        with self.lock:
            self._running -= 1
            if self._running <= 0:
                self.all_done.set()

    def add(self, n: int) -> None:
        with self.lock:
            self.downloaded += n


def _temp_path(filename: str) -> str:
    # Not HttpFD's "<name>.part": a sparse, partly filled file of full length
    # would look finished to HttpFD's resume logic.
    return filename + _TEMP_SUFFIX


def _remove(path: str) -> None:
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError as exc:
        _log.debug("Could not remove %s: %s", path, exc)


def install() -> None:
    """Use ParallelHttpFD for every plain http/https download yt-dlp makes."""
    _ytdl_downloader.PROTOCOL_MAP.setdefault("http", ParallelHttpFD)
    _ytdl_downloader.PROTOCOL_MAP.setdefault("https", ParallelHttpFD)
