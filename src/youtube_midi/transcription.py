"""Typed JSON boundary for an explicitly configured, trusted model worker."""

import json
import os
import re
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from youtube_midi.errors import DependencyError, TranscriptionError
from youtube_midi.models import ConversionOptions, InstrumentTrack, MediaInfo, NoteEvent


@dataclass(frozen=True)
class TranscriptionResult:
    tracks: tuple[InstrumentTrack, ...]
    backend: dict[str, str]
    device: str
    warnings: tuple[str, ...] = ()


class Transcriber(Protocol):
    def check_ready(self) -> None: ...

    def transcribe(
        self, audio: MediaInfo, directory: Path, options: ConversionOptions
    ) -> TranscriptionResult: ...


def _decode_response(data: Any) -> TranscriptionResult:
    try:
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
            raise ValueError("Missing response schema version.")
        if data["schema_version"] != 1:
            raise ValueError("Unsupported response schema version.")
        backend = data["backend"]
        if not isinstance(backend, dict) or not all(
            isinstance(backend.get(key), str) and backend[key].strip()
            for key in ("name", "revision", "checkpoint_sha256")
        ):
            raise ValueError("Backend name, revision and checkpoint hash are required.")
        if re.fullmatch(r"[a-fA-F0-9]{64}", backend["checkpoint_sha256"]) is None:
            raise ValueError("Invalid checkpoint SHA-256.")
        device = data["device"]
        if device not in {"cpu", "cuda"}:
            raise ValueError("Worker must report its actual device.")
        if not isinstance(data["tracks"], list):
            raise ValueError("Tracks must be a list.")
        tracks: list[InstrumentTrack] = []
        for record in data["tracks"]:
            if not isinstance(record["name"], str) or not isinstance(record["notes"], list):
                raise ValueError("Invalid instrument name or note list.")
            notes: list[NoteEvent] = []
            for note in record["notes"]:
                if any(type(note[key]) not in {int, float} for key in ("start", "end")):
                    raise ValueError("Note times must be numbers, not strings or booleans.")
                notes.append(
                    NoteEvent(
                        float(note["start"]),
                        float(note["end"]),
                        note["pitch"],
                        note.get("velocity", 100),
                    )
                )
            tracks.append(
                InstrumentTrack(record["name"], record["program"], tuple(notes), record["is_drum"])
            )
        warnings = data.get("warnings", [])
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            raise ValueError("Warnings must be a list of strings.")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise TranscriptionError(f"Invalid worker response: {error}") from error
    return TranscriptionResult(
        tuple(tracks),
        {key: backend[key] for key in ("name", "revision", "checkpoint_sha256")},
        device,
        tuple(warnings),
    )


def _stop_process(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()
    except ProcessLookupError:
        process.wait()


class WorkerTranscriber:
    def __init__(
        self,
        worker: Path | None,
        *,
        python: Path = Path(sys.executable),
        timeout: float = 3600,
        environment: dict[str, str] | None = None,
    ) -> None:
        self.worker = worker.resolve() if worker is not None else None
        self.python = python.absolute()
        self.timeout = timeout
        self.environment = environment or {}

    def check_ready(self) -> None:
        if self.worker is None or not self.worker.is_file():
            raise DependencyError(
                "No transcription backend configured. Use prepare for video/audio only, "
                "or provide a trusted --worker after model validation."
            )
        if not self.python.is_file() or not os.access(self.python, os.X_OK):
            raise DependencyError("Worker Python executable is missing or not executable.")

    def transcribe(
        self, audio: MediaInfo, directory: Path, options: ConversionOptions
    ) -> TranscriptionResult:
        self.check_ready()
        directory.mkdir(parents=True, exist_ok=False)
        request = directory / "request.json"
        response = directory / "response.json"
        log = directory.parent / "worker.log"
        request.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "audio": {**asdict(audio), "path": str(audio.path.resolve())},
                    "device": options.device,
                    "batch_size": options.batch_size,
                },
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
        environment = {
            **os.environ,
            **self.environment,
            "WANDB_MODE": "disabled",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
        command = [
            str(self.python),
            str(self.worker),
            "--request",
            str(request),
            "--response",
            str(response),
        ]
        try:
            with (
                log.open("w", encoding="utf-8") as output,
                subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=environment,
                    start_new_session=os.name == "posix",
                ) as process,
            ):
                try:
                    returncode = process.wait(timeout=self.timeout)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    _stop_process(process)
                    raise
        except subprocess.TimeoutExpired as error:
            raise TranscriptionError(f"Worker timed out. Log: {log}") from error
        except OSError as error:
            raise TranscriptionError(f"Cannot start the model worker: {error}") from error
        if returncode:
            raise TranscriptionError(f"Worker exited with code {returncode}. Log: {log}")
        try:
            if response.stat().st_size > 16 * 1024**2:
                raise TranscriptionError("Worker response exceeds the 16 MiB contract limit.")
            result = _decode_response(json.loads(response.read_text(encoding="utf-8")))
        except (OSError, ValueError) as error:
            raise TranscriptionError("Worker did not write a readable JSON response.") from error
        if options.device != "auto" and result.device != options.device:
            raise TranscriptionError("Worker silently changed the explicitly requested device.")
        if any(note.end > audio.duration + 0.1 for track in result.tracks for note in track.notes):
            raise TranscriptionError("Worker returned notes beyond the input audio duration.")
        return result


class YourMT3Transcriber(WorkerTranscriber):
    def __init__(self, *, device: str = "auto") -> None:
        from youtube_midi.yourmt3 import model_directory, runtime_python

        self.model_directory = model_directory()
        self.device = device
        self._ready = False
        super().__init__(
            Path(__file__).with_name("yourmt3_worker.py"),
            python=runtime_python(self.model_directory),
            environment={"YT_MIDI_MODEL_DIR": str(self.model_directory)},
        )

    def check_ready(self) -> None:
        from youtube_midi.yourmt3 import validate_assets

        if self._ready:
            return
        validate_assets(self.model_directory)
        super().check_ready()
        try:
            result = subprocess.run(
                [str(self.python), str(self.worker), "--check", "--device", self.device],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env={**os.environ, **self.environment, "HF_HUB_OFFLINE": "1"},
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DependencyError(f"YourMT3+ runtime check failed: {error}") from error
        if result.returncode:
            raise DependencyError(f"YourMT3+ runtime check failed: {result.stderr[-2000:]}")
        self._ready = True
