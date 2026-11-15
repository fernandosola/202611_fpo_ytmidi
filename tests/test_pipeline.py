import json
import shutil
from pathlib import Path

import pytest

from youtube_midi.errors import DependencyError, TranscriptionError
from youtube_midi.models import ConversionOptions, InstrumentTrack, MediaInfo, NoteEvent
from youtube_midi.pipeline import prepare_media, run_conversion
from youtube_midi.transcription import TranscriptionResult, WorkerTranscriber

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg is required"
    ),
]


class FixtureTranscriber:
    def check_ready(self) -> None:
        pass

    def transcribe(
        self, audio: MediaInfo, directory: Path, options: ConversionOptions
    ) -> TranscriptionResult:
        return TranscriptionResult(
            (InstrumentTrack("Piano", 0, (NoteEvent(0, 0.08, 60),)),),
            {"name": "synthetic fixture"},
            "cpu",
        )


def test_prepare_local_audio(audio_file: Path, tmp_path: Path) -> None:
    prepared = prepare_media(ConversionOptions(audio_file=audio_file, output_dir=tmp_path / "out"))
    assert prepared.audio.path.exists()
    assert prepared.video is None
    assert json.loads((prepared.directory / "result.json").read_text())["status"] == "prepared"


def test_conversion_with_fixture_events(audio_file: Path, tmp_path: Path) -> None:
    original = audio_file.read_bytes()
    report = run_conversion(
        ConversionOptions(audio_file=audio_file, output_dir=tmp_path / "out"), FixtureTranscriber()
    )
    data = json.loads(report.read_text())
    assert data["status"] == "completed"
    assert Path(data["midi"]["combined"]).exists()
    assert not (report.parent / "audio.wav").exists()
    assert audio_file.read_bytes() == original


def test_missing_worker_fails_before_creating_outputs(audio_file: Path, tmp_path: Path) -> None:
    output = tmp_path / "out"
    with pytest.raises(DependencyError):
        run_conversion(
            ConversionOptions(audio_file=audio_file, output_dir=output), WorkerTranscriber(None)
        )
    assert not output.exists()


def test_keep_intermediates(audio_file: Path, tmp_path: Path) -> None:
    report = run_conversion(
        ConversionOptions(
            audio_file=audio_file, output_dir=tmp_path / "out", keep_intermediates=True
        ),
        FixtureTranscriber(),
    )
    assert (report.parent / "audio.wav").exists()


@pytest.mark.parametrize("failure", [TranscriptionError, KeyboardInterrupt])
def test_failed_transcription_has_no_success_report(
    audio_file: Path, tmp_path: Path, failure: type[BaseException]
) -> None:
    class FailingTranscriber(FixtureTranscriber):
        def transcribe(
            self, audio: MediaInfo, directory: Path, options: ConversionOptions
        ) -> TranscriptionResult:
            raise failure("test failure")

    with pytest.raises(failure):
        run_conversion(
            ConversionOptions(audio_file=audio_file, output_dir=tmp_path / "out"),
            FailingTranscriber(),
        )
    report = next((tmp_path / "out").glob("*/result.json"))
    expected = "cancelled" if failure is KeyboardInterrupt else "failed"
    assert json.loads(report.read_text())["status"] == expected
    assert not (report.parent / "audio.wav").exists()
    assert audio_file.exists()
