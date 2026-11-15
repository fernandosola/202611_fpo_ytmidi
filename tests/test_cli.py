import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from youtube_midi.cli import app
from youtube_midi.errors import DependencyError

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_model_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("YT_MIDI_MODEL_DIR", str(tmp_path / "model-cache"))


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "prepare" in result.stdout
    assert "convert" in result.stdout
    assert "setup-model" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "not configured" in result.stdout


def test_cli_does_not_import_model_runtimes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import youtube_midi.cli; "
            "assert not {'torch', 'tensorflow', 'jax'} & sys.modules.keys()",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_json_doctor() -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    assert "python" in json.loads(result.stdout)


def test_setup_model_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    setup = Mock(return_value=tmp_path)
    monkeypatch.setattr("youtube_midi.yourmt3.setup_model", setup)
    result = runner.invoke(app, ["setup-model", "--device", "cuda"])
    assert result.exit_code == 0, result.output
    setup.assert_called_once_with("cuda")
    assert str(tmp_path) in result.stdout


def test_setup_model_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = Mock(side_effect=DependencyError("runtime unavailable"))
    monkeypatch.setattr("youtube_midi.yourmt3.setup_model", setup)
    result = runner.invoke(app, ["setup-model"])
    assert result.exit_code == 3
    assert "runtime unavailable" in result.output


def test_source_is_required() -> None:
    result = runner.invoke(app, ["prepare"])
    assert result.exit_code == 2


def test_two_sources_are_rejected(audio_file: Path) -> None:
    result = runner.invoke(
        app, ["prepare", "https://youtu.be/abcdefghijk", "--audio-file", str(audio_file)]
    )
    assert result.exit_code == 2


def test_missing_worker_fails_before_download(tmp_path: Path) -> None:
    output = tmp_path / "output"
    result = runner.invoke(
        app, ["convert", "https://youtu.be/abcdefghijk", "--output-dir", str(output)]
    )
    assert result.exit_code == 3
    assert not output.exists()


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is required")
def test_prepare_command(audio_file: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["prepare", "--audio-file", str(audio_file), "--output-dir", str(tmp_path / "output")]
    )
    assert result.exit_code == 0, result.output
    report = Path(result.stdout.strip())
    assert json.loads(report.read_text())["status"] == "prepared"
