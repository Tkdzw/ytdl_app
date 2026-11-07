"""
Utility: turn yt-dlp / FFmpeg error text into plain language.

``friendly_error(raw)`` returns a short message saying what went wrong and a
hint saying what to do about it. The raw text stays available to the UI
under "Show details" for anyone who wants it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FriendlyError:
    message: str
    hint: str


# (pattern, message, hint) — first match wins, so specific patterns go first.
_RULES: list[tuple[str, str, str]] = [
    (r"confirm you.?re not a bot|sign in to confirm you",
     "YouTube wants to check you're not a robot.",
     "Wait a few minutes and retry. Downloading fewer videos at once helps."),
    (r"confirm your age|age.restricted|inappropriate for some users",
     "This video is age-restricted.",
     "It can only be downloaded with a signed-in YouTube account."),
    (r"private video",
     "This video is private.",
     "Only people the owner shared it with can watch it."),
    (r"members.only|join this channel",
     "This video is for channel members only.",
     "It needs a paid channel membership."),
    (r"premieres? in|live event will begin|this live event|is_upcoming",
     "This video hasn't started yet (scheduled premiere or live stream).",
     "Try again after it has been broadcast."),
    (r"copyright",
     "This video was removed because of a copyright claim.",
     "It can't be downloaded."),
    (r"not available in your country|blocked it in your country|geo.?restrict",
     "This video isn't available in your country.",
     "It can't be downloaded from here."),
    (r"video unavailable|this video is not available|has been removed|"
     r"account associated with this video has been terminated",
     "This video is unavailable.",
     "It may have been deleted or made private. Check the link in your browser."),
    (r"requested format is not available|no video formats found",
     "That quality isn't available for this video.",
     "Choose “Best” quality and retry."),
    (r"http error 429|too many requests",
     "YouTube is limiting downloads right now.",
     "Wait 10–15 minutes, then retry."),
    (r"http error 403|forbidden",
     "YouTube blocked this download.",
     "Retry in a little while. Keeping yt-dlp up to date usually fixes this."),
    (r"http error 404|not found",
     "The video couldn't be found.",
     "Check that the link is complete and still works in your browser."),
    (r"unsupported url",
     "This link isn't a video page the app can download.",
     "Paste the link of the video itself (it usually has “watch?v=” in it)."),
    (r"ffmpeg.*not (found|installed)|ffprobe.*not found|ffmpeg is not installed",
     "FFmpeg is missing, so the video and audio couldn't be combined.",
     "Click “Fix” at the top of the window to install it."),
    (r"no space left|errno 28|disk full",
     "Your disk is full.",
     "Free up some space or choose another “Save to” folder."),
    (r"permission denied|errno 13|access is denied",
     "The app isn't allowed to save in that folder.",
     "Choose a different “Save to” folder, such as your Downloads folder."),
    (r"getaddrinfo|name or service not known|nodename nor servname|"
     r"unable to download webpage|connection (reset|refused|aborted)|"
     r"timed out|network is unreachable|temporary failure in name resolution",
     "Couldn't connect to the internet.",
     "Check your connection and retry."),
    (r"javascript runtime|js runtime|n challenge|signature (extraction|solving)",
     "YouTube's player couldn't be read.",
     "Click “Fix” at the top to install Deno, then retry."),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), m, h) for p, m, h in _RULES]

_GENERIC = FriendlyError(
    "The download failed.",
    "Retry once. If it keeps failing, open “Show details” to see the technical message.",
)


def friendly_error(raw: str) -> FriendlyError:
    """Map a raw error string to a plain-language message + next step."""
    text = raw or ""
    for pattern, message, hint in _COMPILED:
        if pattern.search(text):
            return FriendlyError(message, hint)
    return _GENERIC
