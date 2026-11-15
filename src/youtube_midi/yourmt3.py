"""YourMT3+ note adaptation without importing its model runtime."""

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from youtube_midi.errors import DependencyError
from youtube_midi.models import InstrumentTrack, NoteEvent

SPACE_ID = "mimbres/YourMT3"
SOURCE_REVISION = "5e66c1ea173a8186e0d20432b841d3180cc015b5"
CHECKPOINT_FILE = (
    "amt/logs/2024/notask_all_cross_v6_xk2_amp0811_gm_ext_plus_nops_b72/checkpoints/model.ckpt"
)
CHECKPOINT_SHA256 = "76673d4289aae1a66984b3fee59157d484cda8fdf9b56279251b137321d448e6"


def model_directory() -> Path:
    configured = os.environ.get("YT_MIDI_MODEL_DIR")
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return (
        Path(configured).expanduser().absolute() if configured else cache / "youtube-midi/yourmt3"
    )


def runtime_python(directory: Path) -> Path:
    return directory / "runtime/bin/python"


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_assets(directory: Path, *, verify_hashes: bool = True) -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Model manifest must be a JSON object.")
        if (
            data.get("revision") != SOURCE_REVISION
            or data.get("checkpoint_sha256") != CHECKPOINT_SHA256
            or not runtime_python(directory).is_file()
            or not (directory / "source/amt/src/model/ymt3.py").is_file()
        ):
            raise ValueError("Model manifest or runtime does not match the pinned backend.")
        checkpoint = directory / "source" / CHECKPOINT_FILE
        if not checkpoint.is_file():
            raise ValueError("Missing model checkpoint.")
        if verify_hashes:
            if file_sha256(checkpoint) != CHECKPOINT_SHA256:
                raise ValueError("Checkpoint SHA-256 mismatch; refusing to load it.")
            files = data["source_sha256"]
            if not isinstance(files, dict) or "amt/src/model/ymt3.py" not in files:
                raise ValueError("Missing source integrity manifest.")
            for relative, digest in files.items():
                path = directory / "source" / relative
                if not path.resolve().is_relative_to((directory / "source").resolve()):
                    raise ValueError("Invalid source manifest path.")
                if file_sha256(path) != digest:
                    raise ValueError(f"Source integrity mismatch: {relative}")
        return data
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DependencyError(
            f"YourMT3+ not configured or invalid: {error}. Run: uv run yt-midi setup-model"
        ) from error


def model_status() -> dict[str, Any]:
    directory = model_directory()
    try:
        manifest = validate_assets(directory, verify_hashes=False)
    except DependencyError as error:
        return {"ready": False, "directory": str(directory), "detail": str(error)}
    return {
        "ready": True,
        "directory": str(directory),
        **{
            key: manifest.get(key)
            for key in (
                "name",
                "revision",
                "checkpoint_sha256",
                "validated_device",
                "torch_version",
                "cuda_version",
            )
        },
        "detail": "Installed; source/checkpoint hashes are verified before inference.",
    }


def setup_model(device: str = "auto") -> Path:
    if sys.platform != "linux":
        raise DependencyError("The pinned YourMT3+ runtime currently supports Linux/WSL only.")
    uv = shutil.which("uv")
    if uv is None:
        raise DependencyError("Install uv before running setup-model.")
    directory = model_directory()
    directory.mkdir(parents=True, exist_ok=True)
    python = runtime_python(directory)
    requirements = Path(__file__).parent / "assets/yourmt3-requirements.txt"
    worker = Path(__file__).with_name("yourmt3_worker.py")
    environment = {**os.environ, "YT_MIDI_MODEL_DIR": str(directory), "WANDB_MODE": "disabled"}
    environment.pop("HF_HUB_OFFLINE", None)
    commands = [
        [uv, "venv", "--python", "3.11", str(directory / "runtime")],
        [
            uv,
            "pip",
            "sync",
            "--python",
            str(python),
            "--torch-backend",
            "cu124",
            "--require-hashes",
            str(requirements),
        ],
        [str(python), str(worker), "--setup", "--device", device],
    ]
    if python.is_file():
        commands.pop(0)
    try:
        for command in commands:
            subprocess.run(command, check=True, env=environment)
    except (OSError, subprocess.CalledProcessError) as error:
        raise DependencyError(f"Model setup failed: {error}") from error
    validate_assets(directory)
    return directory


class ModelNote(Protocol):
    is_drum: bool
    program: int
    onset: float
    offset: float
    pitch: int


def normalize_notes(
    notes: Iterable[ModelNote], duration: float, names: dict[int, str]
) -> tuple[tuple[InstrumentTrack, ...], tuple[str, ...]]:
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Audio duration must be finite and positive.")
    groups: dict[tuple[int, bool], list[NoteEvent]] = defaultdict(list)
    discarded = 0
    for note in notes:
        start, end = float(note.onset), float(note.offset)
        program, pitch = int(note.program), int(note.pitch)
        drum = bool(note.is_drum)
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0
            or start >= duration
            or not 0 <= pitch <= 127
            or (not drum and not 0 <= program <= 127)
        ):
            discarded += 1
            continue
        if drum and end <= start:
            end = start + 0.1
        end = min(end, duration)
        if end <= start:
            discarded += 1
            continue
        groups[(0 if drum else program, drum)].append(NoteEvent(start, end, pitch, 100))
    tracks = []
    for (program, drum), events in sorted(groups.items()):
        if drum:
            name, midi_program = "Drums", 0
        elif program in {100, 101}:
            name = "Singing Voice" if program == 100 else "Singing Voice (chorus)"
            midi_program = 53 if program == 100 else 52
        else:
            name, midi_program = names.get(program, f"Instrument {program}"), program
        tracks.append(
            InstrumentTrack(
                name,
                midi_program,
                tuple(sorted(events, key=lambda event: (event.start, event.pitch))),
                drum,
            )
        )
    warnings = ["Instrument identification is estimated; note velocity is fixed at 100."]
    if discarded:
        warnings.append(f"Discarded {discarded} invalid or unannotated model notes.")
    return tuple(tracks), tuple(warnings)
