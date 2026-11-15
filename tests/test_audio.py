import shutil
import subprocess
from pathlib import Path

import pytest

from youtube_midi.audio import extract_audio, probe_media, require_binary
from youtube_midi.errors import AudioError, DependencyError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg is required"
    ),
]


def test_extract_preserves_audio_format(audio_file: Path, tmp_path: Path) -> None:
    destination = tmp_path / "extracted.wav"
    info = extract_audio(audio_file, destination)
    assert info.path == destination
    assert info.duration == pytest.approx(0.1)
    assert info.sample_rate == 16000
    assert info.channels == 2
    assert audio_file.exists()


def test_does_not_overwrite_audio(audio_file: Path) -> None:
    original = audio_file.read_bytes()
    with pytest.raises(AudioError, match="overwrite"):
        extract_audio(audio_file, audio_file)
    assert audio_file.read_bytes() == original


def test_duration_limit(audio_file: Path, tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="duration limit"):
        extract_audio(audio_file, tmp_path / "audio.wav", max_duration=0.01)


def test_requires_video_when_requested(audio_file: Path) -> None:
    with pytest.raises(AudioError, match="video stream"):
        probe_media(audio_file, require_video=True)


def test_missing_media(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="not found"):
        probe_media(tmp_path / "missing.wav")


def test_corrupted_media(tmp_path: Path) -> None:
    corrupted = tmp_path / "corrupted.wav"
    corrupted.write_bytes(b"not audio")
    with pytest.raises(AudioError, match="Media command failed"):
        probe_media(corrupted)


def test_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(DependencyError):
        require_binary("ffmpeg")


def test_extract_from_video_with_audio(audio_file: Path, tmp_path: Path) -> None:
    video = tmp_path / "generated video.mkv"
    subprocess.run(
        [
            require_binary("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=64x64:r=10",
            "-i",
            str(audio_file),
            "-t",
            "0.1",
            "-c:v",
            "mpeg4",
            "-c:a",
            "pcm_s16le",
            str(video),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    assert probe_media(video, require_video=True).channels == 2
    result = extract_audio(video, tmp_path / "from-video.wav")
    assert result.duration == pytest.approx(0.1, abs=0.02)
    assert video.exists()


def test_video_without_audio_is_rejected(tmp_path: Path) -> None:
    video = tmp_path / "silent-video.mp4"
    subprocess.run(
        [
            require_binary("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=64x64:r=10",
            "-t",
            "0.1",
            "-an",
            "-c:v",
            "mpeg4",
            str(video),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    with pytest.raises(AudioError, match="missing audio"):
        probe_media(video)
