"""Download one public YouTube video, retaining both video and audio."""

import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpError

from youtube_midi.audio import probe_media, require_binary
from youtube_midi.errors import DownloadError


def validate_youtube_url(source: str) -> str:
    try:
        parsed = urlsplit(source)
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
        ):
            raise ValueError("An HTTPS YouTube URL without credentials is required.")
        host = parsed.hostname
        if host == "youtu.be":
            video_id = parsed.path.removeprefix("/")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                identifiers = parse_qs(parsed.query).get("v", [])
                if len(identifiers) != 1:
                    raise ValueError("A single video identifier is required.")
                video_id = identifiers[0]
            elif parsed.path.startswith(("/shorts/", "/embed/")):
                video_id = parsed.path.split("/")[-1]
            else:
                raise ValueError("Only individual videos are supported, not channels or playlists.")
        else:
            raise ValueError("Only youtube.com and youtu.be URLs are supported.")
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) is None:
            raise ValueError("Invalid YouTube video identifier.")
    except ValueError as error:
        raise DownloadError(str(error)) from error
    return f"https://www.youtube.com/watch?v={video_id}"


def _validate_metadata(info: dict[str, Any], max_duration: float) -> None:
    if info.get("_type", "video") != "video":
        raise DownloadError("Playlists are not supported.")
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
        raise DownloadError("Live or upcoming streams are not supported.")
    if info.get("availability") not in {None, "public", "unlisted"}:
        raise DownloadError("Only publicly accessible videos without authentication are supported.")
    try:
        duration = float(info["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise DownloadError("Cannot verify the video's duration before downloading.") from error
    if not math.isfinite(duration) or duration <= 0 or duration > max_duration:
        raise DownloadError(f"Video exceeds the duration limit of {max_duration:g} seconds.")


def download_video(
    source: str,
    directory: Path,
    *,
    max_duration: float = 900,
    max_download_size: int = 1024**3,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    normalized = validate_youtube_url(source)
    require_binary("ffmpeg")
    require_binary("ffprobe")
    video_id = parse_qs(urlsplit(normalized).query)["v"][0]
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise DownloadError("Download directory must be empty to prevent output collisions.")
    transferred: dict[str, int] = {}

    def progress_hook(data: dict[str, Any]) -> None:
        filename = str(data.get("filename", "stream"))
        transferred[filename] = int(data.get("downloaded_bytes") or 0)
        if sum(transferred.values()) > max_download_size:
            raise DownloadError("Download exceeded the configured byte limit.")
        if progress and data.get("status") == "finished":
            progress("Downloaded stream; preparing video container.")

    def match_filter(info: dict[str, Any], *, incomplete: bool = False) -> str | None:
        if incomplete:
            return None
        try:
            _validate_metadata(info, max_duration)
        except DownloadError as error:
            return str(error)
        return None

    settings = {
        "format": "bv*+ba/b",
        "merge_output_format": "mkv",
        "outtmpl": str(directory.resolve() / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": False,
        "cachedir": False,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "skip_unavailable_fragments": False,
        "progress_hooks": [progress_hook],
        "match_filter": match_filter,
    }
    try:
        with YoutubeDL(settings) as downloader:
            info = downloader.extract_info(normalized, download=False)
            if not isinstance(info, dict):
                raise DownloadError("YouTube returned no video metadata.")
            _validate_metadata(info, max_duration)
            if info.get("id") != video_id:
                raise DownloadError("The video identifier does not match the requested URL.")
            downloaded = downloader.extract_info(normalized, download=True)
            if not isinstance(downloaded, dict):
                raise DownloadError("The download did not return a completed video.")
    except YtDlpError as error:
        raise DownloadError(
            "YouTube download failed; verify availability and yt-dlp version."
        ) from error
    candidates = [
        path
        for path in directory.glob(f"{video_id}.*")
        if path.suffix in {".mkv", ".mp4", ".webm", ".mov", ".avi", ".flv"}
    ]
    if len(candidates) != 1:
        raise DownloadError("Cannot identify a single completed video file.")
    video = candidates[0]
    if video.stat().st_size > max_download_size:
        raise DownloadError("Completed video exceeds the configured byte limit.")
    media = probe_media(video, require_video=True)
    if media.duration > max_duration:
        raise DownloadError("Downloaded media exceeds the configured duration limit.")
    return video, {
        "id": video_id,
        "url": normalized,
        "title": str(info.get("title", video_id)),
        "duration": media.duration,
    }
