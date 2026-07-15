import os
import logging
import struct

logger = logging.getLogger(__name__)

VALID_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.3gp'}
MIN_VIDEO_SIZE_BYTES = 10_000

_H264_MARKERS = {b'avc1', b'avc3', b'avcC'}
_H265_MARKERS = {b'hev1', b'hvc1', b'hvcC'}
_MPEG4P2_MARKERS = {b'mp4v'}

_PLATFORM_CODEC_REQUIREMENTS = {
    "instagram": {"required": "H.264", "markers": _H264_MARKERS},
}


def detect_video_codec(video_path: str) -> str:
    """Detect video encoding by scanning the encoding mark in the MP4 box.

    Scan both the beginning and the end of the file (1MB each) to cover the case where moov is at the end of the file.
    Return 'h264'/'h265'/'mpeg4'/'unknown'.
    """
    try:
        file_size = os.path.getsize(video_path)
        scan_size = 1024 * 1024
        with open(video_path, "rb") as f:
            head = f.read(min(file_size, scan_size))
            if file_size > scan_size:
                f.seek(max(0, file_size - scan_size))
                tail = f.read()
            else:
                tail = b""
    except Exception:
        return "unknown"

    data = head + tail
    if any(m in data for m in _H264_MARKERS):
        return "h264"
    if any(m in data for m in _H265_MARKERS):
        return "h265"
    if b'mp4v' in data:
        return "mpeg4"
    return "unknown"


def check_codec_compatibility(video_path: str, platform: str) -> tuple[bool, str]:
    """Check whether the video encoding is compatible with the target platform. Return (compatible, warning_msg)."""
    req = _PLATFORM_CODEC_REQUIREMENTS.get(platform)
    if not req:
        return True, ""

    codec = detect_video_codec(video_path)
    if codec == "unknown":
        return True, ""

    if codec == "h264":
        return True, ""

    required = req["required"]
    codec_name = {"h265": "H.265/HEVC", "mpeg4": "MPEG-4 Part 2"}.get(codec, codec)
    return False, (
        f"The video is encoded as {codec_name}, {platform.title()} requires {required}."
        f"The video may be silently rejected by the platform. Please use H.264 encoded video."
    )


def validate_video_file(video_path, platform=None):
    """Pre-verify the video file before uploading and return (ok, error_msg).

    platform is optional, additionally checks encoding compatibility when passed in (incompatible only warns but does not block).
    """
    if not os.path.exists(video_path):
        return False, f"File does not exist: {video_path}"
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in VALID_VIDEO_EXTENSIONS:
        return False, f"Unsupported video format '{ext}', supported: {', '.join(sorted(VALID_VIDEO_EXTENSIONS))}"
    file_size = os.path.getsize(video_path)
    if file_size < MIN_VIDEO_SIZE_BYTES:
        return False, f"The file is too small ({file_size} bytes) and may not be a valid video"

    if platform:
        compat, warn = check_codec_compatibility(video_path, platform)
        if not compat:
            logger.warning(f"⚠️ Encoding warning: {warn}")

    return True, ""


def log_login_error(platform):
    """Unified not logged in error output"""
    logger.error(f"\n❌ {platform} not logged in detected! Please log in manually in the browser and then execute it again.")
    logger.warning("⚠️ Security Tip: This tool will not process your account password. Please visit the corresponding platform in your browser to complete the login.")


_LOGIN_SIGNALS = {
    "tiktok": ["accounts.tiktok.com", "/login", "login-modal"],
    "instagram": ["accounts.instagram.com", "/accounts/login"],
    "youtube": ["accounts.google.com", "/signin"],
}


def quick_login_check(page, platform):
    """Quickly check whether the current page is logged in.

    More forward than the login step of each platform - called before navigating to the target page,
    If the login page URL characteristics are detected, it will be terminated immediately to save time in subsequent processes.

    Return (logged_in: bool, detail: str).
    """
    try:
        url = (page.url or "").lower()
    except Exception:
        return True, "Unable to get URL, skipping preflight"

    signals = _LOGIN_SIGNALS.get(platform, [])
    for signal in signals:
        if signal.lower() in url:
            return False, f"URL contains login signal '{signal}'"
    return True, "ok"
