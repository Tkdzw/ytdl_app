"""
Utility: URL validation helpers.
Quickly checks whether a string looks like a supported video URL
before handing it to yt-dlp, giving the user fast feedback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Patterns for the most common platforms
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("YouTube",    re.compile(r"https?://(www\.)?(youtube\.com/watch|youtu\.be/|youtube\.com/shorts/|youtube\.com/playlist)")),
    ("YouTube",    re.compile(r"https?://(www\.)?youtube\.com/(channel|c|user|@)")),
    ("Vimeo",      re.compile(r"https?://(www\.)?vimeo\.com/")),
    ("Twitch",     re.compile(r"https?://(www\.)?twitch\.tv/")),
    ("Twitter/X",  re.compile(r"https?://(www\.)?(twitter|x)\.com/")),
    ("TikTok",     re.compile(r"https?://(www\.)?tiktok\.com/")),
    ("Instagram",  re.compile(r"https?://(www\.)?instagram\.com/")),
    ("Facebook",   re.compile(r"https?://(www\.)?facebook\.com/")),
    ("Dailymotion",re.compile(r"https?://(www\.)?dailymotion\.com/")),
    ("SoundCloud", re.compile(r"https?://(www\.)?soundcloud\.com/")),
]

_URL_RE = re.compile(r"^https?://\S+$")


@dataclass
class ValidationResult:
    url: str
    valid: bool
    platform: str = ""
    reason: str = ""


def validate_url(url: str) -> ValidationResult:
    """
    Validate a single URL string.
    Returns a ValidationResult with .valid and optional .platform / .reason.
    """
    url = url.strip()
    if not url:
        return ValidationResult(url=url, valid=False, reason="Empty string")

    if not _URL_RE.match(url):
        return ValidationResult(url=url, valid=False, reason="Not a valid HTTP/HTTPS URL")

    for platform, pattern in _PATTERNS:
        if pattern.match(url):
            return ValidationResult(url=url, valid=True, platform=platform)

    # Unknown platform — still a valid URL, yt-dlp may support it
    return ValidationResult(url=url, valid=True, platform="Unknown")


def validate_urls(raw_text: str) -> tuple[list[ValidationResult], list[ValidationResult]]:
    """
    Split a multiline string into individual URLs and validate each.
    Returns (valid_results, invalid_results).
    """
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    valid: list[ValidationResult] = []
    invalid: list[ValidationResult] = []

    for line in lines:
        result = validate_url(line)
        if result.valid:
            valid.append(result)
        else:
            invalid.append(result)

    return valid, invalid
