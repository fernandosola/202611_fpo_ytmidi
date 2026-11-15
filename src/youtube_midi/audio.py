"""Validate media and extract PCM audio with system FFmpeg binaries."""

import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from youtube_midi.errors import AudioError, DependencyError
from youtube_midi.models import MediaInfo


def require_binary(name: str) -> str:
    binary = shutil.which(name)
    if binary is None:
        raise DependencyError(f"{name} is missing. Install the system FFmpeg/ffprobe binaries.")
    return binary


def _run_media_command(command: list[str], timeout: float) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise DependencyError(f"Media executable not found: {command[0]}") from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AudioError(f"Media command failed: {error}") from error
    if result.returncode:
        raise AudioError(f"Media command failed: {result.stderr.strip()[-1000:]}")
    return result.stdout


def probe_media(path: Path, *, require_video: bool = False) -> MediaInfo:
    path = path.resolve()
    if not path.is_file():
        raise AudioError(f"Media file not found: {path}")
    output = _run_media_command(
        [
            require_binary("ffprobe"),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        timeout=30,
    )
    try:
        metadata = json.loads(output)
        streams = metadata["streams"]
        audio_stream = next(stream for stream in streams if stream.get("codec_type") == "audio")
        if require_video and not any(stream.get("codec_type") == "video" for stream in streams):
            raise AudioError("The downloaded media does not contain a video stream.")
        duration = float(audio_stream.get("duration") or metadata["format"]["duration"])
        sample_rate = int(audio_stream["sample_rate"])
        channels = int(audio_stream["channels"])
        if not math.isfinite(duration) or duration <= 0 or sample_rate <= 0 or channels <= 0:
            raise ValueError("Invalid audio duration, sample rate or channel count.")
    except (ValueError, KeyError, TypeError, AttributeError, StopIteration) as error:
        raise AudioError("Invalid media metadata or missing audio stream.") from error
    return MediaInfo(path, duration, sample_rate, channels)


def extract_audio(source: Path, destination: Path, *, max_duration: float = 900) -> MediaInfo:
    info = probe_media(source)
    if info.duration > max_duration:
        raise AudioError(f"Audio exceeds the duration limit of {max_duration:g} seconds.")
    binary = require_binary("ffmpeg")
    destination = destination.resolve()
    if destination.exists():
        raise AudioError(f"Refusing to overwrite audio: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".extract-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "audio.wav"
        _run_media_command(
            [
                binary,
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-i",
                str(info.path),
                "-map",
                "0:a:0",
                "-vn",
                "-c:a",
                "pcm_s16le",
                str(staged),
            ],
            timeout=max(60, info.duration * 2),
        )
        extracted = probe_media(staged)
        if abs(extracted.duration - info.duration) > 1:
            raise AudioError("Extracted audio duration differs from the source.")
        try:
            destination.hardlink_to(staged)
        except FileExistsError as error:
            raise AudioError(f"Refusing to overwrite audio: {destination}") from error
    return MediaInfo(destination, extracted.duration, extracted.sample_rate, extracted.channels)
