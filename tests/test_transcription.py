import json
import sys
from pathlib import Path
from typing import Any

import pytest

from youtube_midi.errors import DependencyError, TranscriptionError
from youtube_midi.models import ConversionOptions, MediaInfo
from youtube_midi.transcription import WorkerTranscriber, _decode_response


@pytest.fixture
def worker_response() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "backend": {"name": "test fixture", "revision": "fixture", "checkpoint_sha256": "0" * 64},
        "device": "cpu",
        "tracks": [
            {
                "name": "Piano",
                "program": 0,
                "is_drum": False,
                "notes": [{"start": 0, "end": 0.08, "pitch": 60}],
            }
        ],
        "warnings": [],
    }


def test_trusted_worker_contract(
    worker_response: dict[str, Any], audio_file: Path, tmp_path: Path
) -> None:
    script = tmp_path / "test worker.py"
    script.write_text(
        "import argparse, json\n"
        "import typer\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--request')\n"
        "parser.add_argument('--response')\n"
        "args = parser.parse_args()\n"
        "assert json.loads(Path(args.request).read_text())['schema_version'] == 1\n"
        f"Path(args.response).write_text({json.dumps(worker_response)!r})\n",
        encoding="utf-8",
    )
    worker = WorkerTranscriber(script, python=Path(sys.executable))
    result = worker.transcribe(
        MediaInfo(audio_file, 0.1, 16000, 2),
        tmp_path / "work",
        ConversionOptions(audio_file=audio_file),
    )
    assert result.tracks[0].notes[0].pitch == 60
    assert result.device == "cpu"
    assert worker.python == Path(sys.executable).absolute()


def test_missing_worker() -> None:
    with pytest.raises(DependencyError, match="No transcription backend"):
        WorkerTranscriber(None).check_ready()


@pytest.mark.parametrize("invalid", [None, [], {}, {"schema_version": 2}])
def test_invalid_response(invalid: Any) -> None:
    with pytest.raises(TranscriptionError):
        _decode_response(invalid)


@pytest.mark.parametrize("field,value", [("program", 128), ("is_drum", "false"), ("name", "")])
def test_invalid_instrument(worker_response: dict[str, Any], field: str, value: Any) -> None:
    worker_response["tracks"][0][field] = value
    with pytest.raises(TranscriptionError):
        _decode_response(worker_response)


@pytest.mark.parametrize("field,value", [("pitch", 60.5), ("start", True), ("end", "1")])
def test_invalid_note(worker_response: dict[str, Any], field: str, value: Any) -> None:
    worker_response["tracks"][0]["notes"][0][field] = value
    with pytest.raises(TranscriptionError):
        _decode_response(worker_response)


@pytest.mark.parametrize(
    "body,message",
    [
        ("raise SystemExit(8)\n", "code 8"),
        ("print('missing response')\n", "readable JSON"),
        ("while True:\n    pass\n", "timed out"),
    ],
)
def test_worker_process_failures(body: str, message: str, audio_file: Path, tmp_path: Path) -> None:
    script = tmp_path / "failing-worker.py"
    script.write_text(body, encoding="utf-8")
    worker = WorkerTranscriber(script, timeout=0.5)
    with pytest.raises(TranscriptionError, match=message):
        worker.transcribe(
            MediaInfo(audio_file, 0.1, 16000, 2),
            tmp_path / "work",
            ConversionOptions(audio_file=audio_file),
        )
    assert (tmp_path / "worker.log").exists()
