import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pretty_midi
import pytest

from youtube_midi import yourmt3
from youtube_midi.errors import DependencyError
from youtube_midi.models import ConversionOptions
from youtube_midi.pipeline import run_conversion
from youtube_midi.transcription import YourMT3Transcriber
from youtube_midi.yourmt3 import normalize_notes


@dataclass
class PredictedNote:
    is_drum: bool
    program: int
    onset: float
    offset: float
    pitch: int


def test_real_model_note_contract() -> None:
    notes = [
        PredictedNote(False, 0, 0, 2, 60),
        PredictedNote(False, 0, 0.5, 1, 64),
        PredictedNote(False, 33, 0, 1, 40),
        PredictedNote(True, 128, 0.5, 0.5, 36),
        PredictedNote(False, 100, 0, 1, 72),
    ]
    tracks, warnings = normalize_notes(notes, 1.5, {0: "Acoustic Piano", 33: "Bass"})
    assert {track.name for track in tracks} == {"Acoustic Piano", "Bass", "Drums", "Singing Voice"}
    drums = next(track for track in tracks if track.is_drum)
    assert drums.program == 0
    assert drums.notes[0].end == pytest.approx(0.6)
    voice = next(track for track in tracks if track.name == "Singing Voice")
    assert voice.program == 53
    piano = next(track for track in tracks if track.program == 0 and not track.is_drum)
    assert len(piano.notes) == 2
    assert piano.notes[0].end == 1.5
    assert "fixed at 100" in warnings[0]


def test_padding_and_unannotated_notes_are_not_exported() -> None:
    tracks, warnings = normalize_notes(
        [PredictedNote(False, 129, 0, 1, 60), PredictedNote(False, 0, 2, 3, 60)], 1, {}
    )
    assert not tracks
    assert "Discarded 2" in warnings[1]


@pytest.mark.parametrize("body", ["null", "[]", "{}", "not json"])
def test_invalid_manifests_fail_with_setup_guidance(tmp_path: Path, body: str) -> None:
    (tmp_path / "manifest.json").write_text(body, encoding="utf-8")
    with pytest.raises(DependencyError, match="setup-model"):
        yourmt3.validate_assets(tmp_path)


@pytest.fixture
def model_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "assets"
    source = directory / "source/amt/src/model/ymt3.py"
    source.parent.mkdir(parents=True)
    source.write_text("fixture source\n", encoding="utf-8")
    checkpoint = directory / "source" / yourmt3.CHECKPOINT_FILE
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"fixture checkpoint")
    python = yourmt3.runtime_python(directory)
    python.parent.mkdir(parents=True)
    python.touch()
    digest = yourmt3.file_sha256(checkpoint)
    monkeypatch.setattr(yourmt3, "CHECKPOINT_SHA256", digest)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "revision": yourmt3.SOURCE_REVISION,
                "checkpoint_sha256": digest,
                "source_sha256": {"amt/src/model/ymt3.py": yourmt3.file_sha256(source)},
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_valid_assets_and_modified_checkpoint(model_assets: Path) -> None:
    yourmt3.validate_assets(model_assets)
    (model_assets / "source" / yourmt3.CHECKPOINT_FILE).write_bytes(b"changed checkpoint")
    with pytest.raises(DependencyError, match="SHA-256 mismatch"):
        yourmt3.validate_assets(model_assets)


def test_modified_source_is_rejected(model_assets: Path) -> None:
    (model_assets / "source/amt/src/model/ymt3.py").write_text("changed\n", encoding="utf-8")
    with pytest.raises(DependencyError, match="Source integrity"):
        yourmt3.validate_assets(model_assets)


def test_setup_uses_locked_cuda_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("YT_MIDI_MODEL_DIR", str(tmp_path / "runtime-test"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(yourmt3.shutil, "which", lambda _: "/fake/uv")
    monkeypatch.setattr(yourmt3, "validate_assets", lambda _: {})
    commands: list[list[str]] = []

    def execute(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert "HF_HUB_OFFLINE" not in kwargs["env"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(yourmt3.subprocess, "run", execute)
    yourmt3.setup_model("cuda")
    assert commands[1][commands[1].index("--torch-backend") + 1] == "cu124"
    assert "--require-hashes" in commands[1]
    assert commands[2][-2:] == ["--device", "cuda"]


def test_installed_worker_prefers_runtime_dependencies(tmp_path: Path) -> None:
    cli_site = tmp_path / "cli-site"
    runtime_site = tmp_path / "runtime-site"
    runtime_site.mkdir()
    package = cli_site / "youtube_midi"
    shutil.copytree(
        Path(yourmt3.__file__).parent,
        package,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (cli_site / "numpy.py").write_text("__version__ = 'cli'\n", encoding="utf-8")
    (runtime_site / "numpy.py").write_text("__version__ = 'runtime'\n", encoding="utf-8")
    (runtime_site / "torch.py").write_text(
        "import numpy\nprint(numpy.__version__)\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, str(package / "yourmt3_worker.py"), "--check", "--device", "cpu"],
        env={**os.environ, "PYTHONPATH": str(runtime_site)},
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert result.stdout.splitlines() == ["runtime", "cpu"]


@pytest.fixture
def musical_audio(tmp_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("FFmpeg is required for the model fixture")
    path = tmp_path / "original chord.wav"
    expression = (
        "aevalsrc='0.1*(sin(2*PI*261.625565*t)+sin(2*PI*329.627557*t)"
        "+sin(2*PI*391.995436*t))*exp(-3*mod(t,1))"
        "+0.08*sin(2*PI*130.812783*t)':s=44100:d=12"
    )
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            expression,
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return path


@pytest.mark.model
@pytest.mark.skipif(os.environ.get("YT_MIDI_RUN_MODEL_TESTS") != "1", reason="Opt-in model tests")
@pytest.mark.parametrize(
    "device,batch_size", [pytest.param("cuda", 4, marks=pytest.mark.gpu), ("cpu", 1)]
)
def test_real_inference_exports_chord(
    musical_audio: Path,
    tmp_path: Path,
    device: Literal["cpu", "cuda"],
    batch_size: int,
) -> None:
    options = ConversionOptions(
        audio_file=musical_audio,
        output_dir=tmp_path / "output",
        device=device,
        batch_size=batch_size,
    )
    report = run_conversion(options, YourMT3Transcriber(device=device))
    data = json.loads(report.read_text(encoding="utf-8"))
    midi = pretty_midi.PrettyMIDI(data["midi"]["combined"])
    assert data["status"] == "completed"
    assert data["device"] == device
    assert data["backend"]["checkpoint_sha256"] == yourmt3.CHECKPOINT_SHA256
    assert {60, 64, 67} <= {note.pitch for track in midi.instruments for note in track.notes}
    assert all(
        0 <= note.start < note.end <= 12.01 for track in midi.instruments for note in track.notes
    )
    assert not (report.parent / "audio.wav").exists()


@pytest.mark.model
@pytest.mark.gpu
@pytest.mark.skipif(os.environ.get("YT_MIDI_RUN_MODEL_TESTS") != "1", reason="Opt-in model tests")
def test_three_minute_inference_keeps_absolute_times(musical_audio: Path, tmp_path: Path) -> None:
    path = tmp_path / "three minutes.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-stream_loop",
            "14",
            "-i",
            str(musical_audio),
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    options = ConversionOptions(audio_file=path, output_dir=tmp_path / "output", device="cuda")
    report = run_conversion(options, YourMT3Transcriber(device="cuda"))
    data = json.loads(report.read_text(encoding="utf-8"))
    midi = pretty_midi.PrettyMIDI(data["midi"]["combined"])
    assert data["audio"]["duration"] == 180
    assert 170 < midi.get_end_time() <= 180.01
    assert (report.parent / "worker.log").is_file()
