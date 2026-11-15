"""Export already-transcribed events, without guessing missing instruments."""

import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pretty_midi

from youtube_midi.errors import MidiError
from youtube_midi.models import InstrumentTrack


@dataclass(frozen=True)
class MidiExports:
    combined: Path | None
    individual: tuple[Path, ...]
    warnings: tuple[str, ...]


def _write_midi(tracks: tuple[InstrumentTrack, ...], path: Path, bpm: float) -> None:
    midi = pretty_midi.PrettyMIDI(initial_tempo=bpm, resolution=960)
    for track in tracks:
        instrument = pretty_midi.Instrument(
            program=track.program, name=track.name, is_drum=track.is_drum
        )
        for note in sorted(track.notes, key=lambda event: (event.start, event.pitch, event.end)):
            instrument.notes.append(
                pretty_midi.Note(
                    velocity=note.velocity, pitch=note.pitch, start=note.start, end=note.end
                )
            )
        midi.instruments.append(instrument)
    midi.write(str(path))


def export_tracks(
    tracks: tuple[InstrumentTrack, ...], directory: Path, *, bpm: float = 120
) -> MidiExports:
    if not math.isfinite(bpm) or not 1 <= bpm <= 1000:
        raise MidiError("Nominal MIDI tempo must be between 1 and 1000 BPM.")
    active = tuple(track for track in tracks if track.notes)
    if not active:
        raise MidiError(
            "The transcription contains no notes; no successful MIDI conversion exists."
        )
    if directory.exists():
        raise MidiError(f"Refusing to overwrite an existing MIDI directory: {directory}")
    warnings = [f"No notes for instrument: {track.name}" for track in tracks if not track.notes]
    combined: Path | None = None
    individual: list[Path] = []
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise MidiError(f"Cannot create the MIDI directory: {directory}") from error
    try:
        for index, track in enumerate(active, start=1):
            name = re.sub(r"[^A-Za-z0-9._-]+", "_", track.name).strip("._-")[:64] or "instrument"
            path = directory / f"{index:03d}_{name}.mid"
            _write_midi((track,), path, bpm)
            individual.append(path)
        if sum(not track.is_drum for track in active) <= 15:
            combined = directory / "combined.mid"
            _write_midi(active, combined, bpm)
        else:
            warnings.append("More than 15 tonal instruments: only individual MIDI files exported.")
    except (OSError, ValueError) as error:
        shutil.rmtree(directory)
        raise MidiError(f"MIDI export failed: {error}") from error
    return MidiExports(combined, tuple(individual), tuple(warnings))
