"""Data contracts shared by pipeline stages."""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class ConversionOptions:
    source: str | None = None
    audio_file: Path | None = None
    output_dir: Path = Path("output")
    device: Literal["auto", "cuda", "cpu"] = "auto"
    batch_size: int = 4
    max_duration: float = 900.0
    max_download_size: int = 1024**3
    keep_intermediates: bool = False
    bpm: float = 120.0

    def __post_init__(self) -> None:
        if (self.source is None) == (self.audio_file is None):
            raise ValueError("Provide exactly one YouTube URL or local audio file.")
        if self.device not in {"auto", "cuda", "cpu"}:
            raise ValueError("Device must be auto, cuda or cpu.")
        if self.batch_size < 1 or self.max_download_size < 1:
            raise ValueError("Batch size and download size limit must be positive.")
        if not math.isfinite(self.max_duration) or self.max_duration <= 0:
            raise ValueError("Duration limit must be finite and positive.")
        if not math.isfinite(self.bpm) or not 1 <= self.bpm <= 1000:
            raise ValueError("Nominal MIDI tempo must be between 1 and 1000 BPM.")


@dataclass(frozen=True)
class NoteEvent:
    start: float
    end: float
    pitch: int
    velocity: int = 100

    def __post_init__(self) -> None:
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValueError("Note times must be finite.")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Note end must be after its nonnegative start.")
        if type(self.pitch) is not int or not 0 <= self.pitch <= 127:
            raise ValueError("MIDI pitch must be an integer between 0 and 127.")
        if type(self.velocity) is not int or not 1 <= self.velocity <= 127:
            raise ValueError("MIDI velocity must be an integer between 1 and 127.")


@dataclass(frozen=True)
class InstrumentTrack:
    name: str
    program: int
    notes: tuple[NoteEvent, ...]
    is_drum: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Instrument name must not be empty.")
        if type(self.program) is not int or not 0 <= self.program <= 127:
            raise ValueError("General MIDI program must be an integer between 0 and 127.")
        if type(self.is_drum) is not bool:
            raise ValueError("is_drum must be a boolean.")
