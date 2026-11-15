"""Sequential media preparation and conversion with per-job output directories."""

import json
import logging
import shutil
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from youtube_midi import __version__
from youtube_midi.audio import extract_audio, probe_media, require_binary
from youtube_midi.download import download_video, validate_youtube_url
from youtube_midi.errors import AudioError, ProjectError
from youtube_midi.midi import export_tracks
from youtube_midi.models import ConversionOptions, MediaInfo
from youtube_midi.transcription import Transcriber

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedMedia:
    directory: Path
    video: Path | None
    audio: MediaInfo
    metadata: dict[str, Any]


def _write_report(directory: Path, data: dict[str, Any]) -> Path:
    report = directory / "result.json"
    temporary = directory / "result.partial.json"
    temporary.write_text(
        json.dumps(data, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(report)
    return report


def prepare_media(
    options: ConversionOptions, progress: Callable[[str], None] | None = None
) -> PreparedMedia:
    require_binary("ffmpeg")
    require_binary("ffprobe")
    source = validate_youtube_url(options.source) if options.source is not None else None
    if options.audio_file is not None:
        info = probe_media(options.audio_file)
        if info.duration > options.max_duration:
            raise AudioError("Local audio exceeds the configured duration limit.")
    directory = options.output_dir.resolve() / f"job-{uuid.uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=False)
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "project_version": __version__,
        "status": "preparing",
        "options": {**asdict(options), "source": source},
    }
    video: Path | None = None
    try:
        _write_report(directory, metadata)
        if source is not None:
            if progress:
                progress("Downloading video and audio.")
            video, video_metadata = download_video(
                source,
                directory / "video",
                max_duration=options.max_duration,
                max_download_size=options.max_download_size,
                progress=progress,
            )
            metadata["video"] = {**video_metadata, "path": str(video)}
            media_path = video
        elif options.audio_file is not None:
            media_path = options.audio_file
        else:
            raise ValueError("No input source.")
        if progress:
            progress("Extracting PCM audio.")
        audio = extract_audio(
            media_path, directory / "audio.wav", max_duration=options.max_duration
        )
        metadata.update(status="prepared", audio=asdict(audio))
        _write_report(directory, metadata)
    except (ProjectError, OSError, KeyboardInterrupt) as error:
        metadata.update(
            status="cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
            error=str(error),
        )
        try:
            _write_report(directory, metadata)
        except OSError:
            logger.exception("Cannot write failure report in %s", directory)
        raise
    return PreparedMedia(directory, video, audio, metadata)


def run_conversion(
    options: ConversionOptions,
    transcriber: Transcriber,
    progress: Callable[[str], None] | None = None,
) -> Path:
    transcriber.check_ready()
    prepared = prepare_media(options, progress)
    work = prepared.directory / "transcription"
    metadata = prepared.metadata
    try:
        metadata["status"] = "transcribing"
        _write_report(prepared.directory, metadata)
        if progress:
            progress("Transcribing instruments.")
        transcription = transcriber.transcribe(prepared.audio, work, options)
        if progress:
            progress("Exporting MIDI files.")
        exports = export_tracks(transcription.tracks, prepared.directory / "midi", bpm=options.bpm)
        metadata.update(
            status="completed",
            backend=transcription.backend,
            device=transcription.device,
            instruments=[
                {
                    "name": track.name,
                    "program": track.program,
                    "is_drum": track.is_drum,
                    "note_count": len(track.notes),
                }
                for track in transcription.tracks
            ],
            midi={"combined": exports.combined, "individual": exports.individual},
            warnings=transcription.warnings + exports.warnings,
        )
        return _write_report(prepared.directory, metadata)
    except (ProjectError, OSError, KeyboardInterrupt) as error:
        metadata.update(
            status="cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
            error=str(error),
        )
        _write_report(prepared.directory, metadata)
        raise
    finally:
        if not options.keep_intermediates:
            prepared.audio.path.unlink(missing_ok=True)
            if work.exists():
                shutil.rmtree(work)
