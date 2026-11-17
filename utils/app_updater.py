"""
Utility: update the app itself from the latest GitHub release.

1. ``check_latest()`` asks GitHub's public API for the latest release of
   ``app_info.GITHUB_REPO`` and compares its tag (``vX.Y.Z``) with
   ``app_info.VERSION``.
2. ``download_installer()`` fetches the release's ``YTDownloader_Setup.exe``
   to a temp folder and checks it against the SHA-256 that GitHub publishes
   for the file (and its exact size).
3. ``launch_installer()`` starts it silently through the Windows shell, which
   shows the usual admin (UAC) prompt; the caller then closes the app. The
   installer replaces the files and reopens the app (see installer.iss).

Only an installed copy (frozen exe next to an Inno Setup uninstaller) can
update itself; elsewhere ``can_self_update()`` is False and the UI offers the
release page instead.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

import app_info
from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

_API_LATEST = f"https://api.github.com/repos/{app_info.GITHUB_REPO}/releases/latest"
_RELEASES_PAGE = f"https://github.com/{app_info.GITHUB_REPO}/releases/latest"
_ASSET_NAME = f"{app_info.APP_ID}_Setup.exe"
_ALLOWED_DOWNLOAD_PREFIX = f"https://github.com/{app_info.GITHUB_REPO}/releases/download/"
_USER_AGENT = f"{app_info.APP_ID}/{app_info.VERSION} (update check)"
_UPDATE_DIR = os.path.join(tempfile.gettempdir(), f"{app_info.APP_ID}_update")
_CHUNK = 256 * 1024

RELEASES_PAGE = _RELEASES_PAGE


class UpdateError(Exception):
    """Something went wrong; the message is shown to the user as-is."""


class UpdateCancelled(Exception):
    pass


@dataclass
class ReleaseInfo:
    version: str              # "2.3.0"
    tag: str                  # "v2.3.0"
    name: str
    notes: str                # release body (Markdown)
    page_url: str
    published: str            # ISO date "2026-11-20"
    asset_url: str = ""
    asset_size: int = 0
    asset_sha256: str = ""    # lowercase hex, "" if GitHub didn't publish one

    @property
    def codename(self) -> str:
        """Codename from the release title ('v2.4.0 “Goshawk”'), else app_info's list."""
        m = re.search(r"[“\"']([A-Z][A-Za-z -]{1,30})[”\"']", self.name or "")
        return m.group(1) if m else app_info.codename_for(self.version)

    @property
    def display_version(self) -> str:
        return f"{self.version} “{self.codename}”" if self.codename else self.version

    @property
    def is_newer(self) -> bool:
        return parse_version(self.version) > parse_version(app_info.VERSION)


# ── Versions ──────────────────────────────────────────────────────────────────

def parse_version(text: str) -> tuple[int, ...]:
    """'v2.10.1' -> (2, 10, 1). Anything unparseable sorts lowest."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", text or "")
    if not m:
        return (0,)
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


# ── Where we run ──────────────────────────────────────────────────────────────

def can_self_update() -> bool:
    """True for the installed app: a frozen exe in a folder with Inno's uninstaller."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    app_dir = os.path.dirname(sys.executable)
    return bool(glob.glob(os.path.join(app_dir, "unins*.exe")))


# ── Check ─────────────────────────────────────────────────────────────────────

def _get(url: str, timeout: float):
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(req, timeout=timeout)


def check_latest(timeout: float = 8) -> ReleaseInfo:
    """Fetch the latest published release. Raises UpdateError on failure."""
    try:
        with _get(_API_LATEST, timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("No releases have been published yet.") from exc
        if exc.code in (403, 429):
            raise UpdateError("GitHub is limiting update checks right now. "
                              "Please try again in an hour.") from exc
        raise UpdateError(f"GitHub answered with an error (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpdateError("Couldn't reach GitHub. Check your internet connection.") from exc
    except ValueError as exc:
        raise UpdateError("GitHub sent an unexpected reply.") from exc

    tag = str(data.get("tag_name") or "")
    info = ReleaseInfo(
        version=".".join(str(p) for p in parse_version(tag)),
        tag=tag,
        name=str(data.get("name") or tag),
        notes=str(data.get("body") or "").strip(),
        page_url=str(data.get("html_url") or _RELEASES_PAGE),
        published=str(data.get("published_at") or "")[:10],
    )
    for asset in data.get("assets") or []:
        if asset.get("name") == _ASSET_NAME:
            info.asset_url = str(asset.get("browser_download_url") or "")
            info.asset_size = int(asset.get("size") or 0)
            digest = str(asset.get("digest") or "")
            if digest.lower().startswith("sha256:"):
                info.asset_sha256 = digest.split(":", 1)[1].lower()
            break
    _log.info("Latest release %s (installed %s), installer %s",
              info.tag, app_info.VERSION, "found" if info.asset_url else "missing")
    return info


# ── Download ──────────────────────────────────────────────────────────────────

def download_installer(
    info: ReleaseInfo,
    on_progress: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Download and verify the installer. Returns its path.
    Raises UpdateError (shown to the user) or UpdateCancelled.
    """
    if not info.asset_url:
        raise UpdateError(f"This release has no {_ASSET_NAME} to install.")
    if not info.asset_url.startswith(_ALLOWED_DOWNLOAD_PREFIX):
        raise UpdateError("The installer link doesn't point at this app's GitHub releases.")

    cleanup_downloads()
    os.makedirs(_UPDATE_DIR, exist_ok=True)
    final = os.path.join(_UPDATE_DIR, f"{app_info.APP_ID}_Setup_{info.version}.exe")
    part = final + ".part"
    sha = hashlib.sha256()
    done = 0
    try:
        with _get(info.asset_url, timeout=30) as resp, open(part, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or info.asset_size or 0)
            while True:
                if is_cancelled and is_cancelled():
                    raise UpdateCancelled()
                block = resp.read(_CHUNK)
                if not block:
                    break
                fh.write(block)
                sha.update(block)
                done += len(block)
                if on_progress:
                    on_progress(done, total)
    except UpdateCancelled:
        _remove(part)
        raise
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        _remove(part)
        raise UpdateError("The download was interrupted. Check your connection and try again.") from exc

    # ── Verify ────────────────────────────────────────────────────────────────
    problem = ""
    if info.asset_size and done != info.asset_size:
        problem = f"size {done} bytes, expected {info.asset_size}"
    elif info.asset_sha256 and sha.hexdigest() != info.asset_sha256:
        problem = "SHA-256 checksum doesn't match the one GitHub published"
    else:
        with open(part, "rb") as fh:
            if fh.read(2) != b"MZ":
                problem = "not a Windows program"
    if problem:
        _remove(part)
        _log.error("Update download rejected: %s", problem)
        raise UpdateError("The downloaded installer failed its safety check "
                          f"({problem}), so it was deleted. Please try again.")
    if not info.asset_sha256:
        _log.warning("Release %s has no published SHA-256; checked size only", info.tag)

    os.replace(part, final)
    _log.info("Update %s downloaded and verified: %s", info.version, final)
    return final


# ── Install ───────────────────────────────────────────────────────────────────

def launch_installer(path: str) -> None:
    """
    Start the installer silently. Windows shows the admin prompt; if the user
    declines it, UpdateError is raised and the app should stay open.
    """
    log_path = os.path.join(_UPDATE_DIR, "install.log")
    args = (f'/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS '
            f'/LOG="{log_path}"')
    try:
        # ShellExecute (not subprocess) so Windows can raise the UAC prompt
        # the installer needs (PrivilegesRequired=admin).
        os.startfile(path, "open", args)       # type: ignore[attr-defined]
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1223:     # ERROR_CANCELLED
            raise UpdateError("The update was cancelled at the Windows permission prompt.") from exc
        raise UpdateError(f"Couldn't start the installer: {exc}") from exc
    _log.info("Installer launched: %s %s", path, args)


def cleanup_downloads() -> None:
    """Remove installers left over from earlier updates."""
    if os.path.isdir(_UPDATE_DIR):
        shutil.rmtree(_UPDATE_DIR, ignore_errors=True)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
