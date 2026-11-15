from pathlib import Path

import pretty_midi
import pytest

from youtube_midi.errors import MidiError
from youtube_midi.midi import export_tracks
from youtube_midi.models import ConversionOptions, InstrumentTrack, NoteEvent


def test_export_instruments_drums_and_overlapping_notes(tmp_path: Path) -> None:
    tracks = (
        InstrumentTrack("Piano", 0, (NoteEvent(0, 2, 60), NoteEvent(0.5, 1, 64))),
        InstrumentTrack("Bass", 33, (NoteEvent(0.5, 2.5, 40),)),
        InstrumentTrack("Drums", 0, (NoteEvent(1, 1.1, 36),), is_drum=True),
    )
    exports = export_tracks(tracks, tmp_path / "midi")
    assert len(exports.individual) == 3
    assert exports.combined is not None
    result = pretty_midi.PrettyMIDI(str(exports.combined))
    assert [instrument.name for instrument in result.instruments] == ["Piano", "Bass", "Drums"]
    assert [instrument.program for instrument in result.instruments] == [0, 33, 0]
    assert [instrument.is_drum for instrument in result.instruments] == [False, False, True]
    assert len(result.instruments[0].notes) == 2
    piano_notes = {note.pitch: note for note in result.instruments[0].notes}
    assert piano_notes[60].start == pytest.approx(0, abs=0.001)
    assert piano_notes[60].end == pytest.approx(2, abs=0.001)
    assert piano_notes[64].start == pytest.approx(0.5, abs=0.001)
    assert piano_notes[64].end == pytest.approx(1, abs=0.001)
    assert result.instruments[1].notes[0].end == pytest.approx(2.5, abs=0.001)


def test_no_silent_channel_reuse(tmp_path: Path) -> None:
    tracks = tuple(
        InstrumentTrack(f"Instrument {index}", index, (NoteEvent(0, 1, 60),)) for index in range(16)
    )
    result = export_tracks(tracks, tmp_path / "midi")
    assert result.combined is None
    assert len(result.individual) == 16
    assert "15" in result.warnings[0]


def test_track_names_cannot_escape_directory(tmp_path: Path) -> None:
    track = InstrumentTrack("../../evil", 0, (NoteEvent(0, 1, 60),))
    result = export_tracks((track,), tmp_path / "midi")
    assert result.individual[0].parent == tmp_path / "midi"


def test_no_notes_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(MidiError, match="no notes"):
        export_tracks((InstrumentTrack("Piano", 0, ()),), tmp_path / "midi")


def test_existing_midi_directory_is_preserved(tmp_path: Path) -> None:
    protected = tmp_path / "keep.mid"
    protected.write_bytes(b"keep")
    with pytest.raises(MidiError, match="overwrite"):
        export_tracks((InstrumentTrack("Piano", 0, (NoteEvent(0, 1, 60),)),), tmp_path)
    assert protected.read_bytes() == b"keep"


@pytest.mark.parametrize(
    "values",
    [
        (-1, 1, 60, 100),
        (1, 1, 60, 100),
        (0, float("nan"), 60, 100),
        (0, 1, 128, 100),
        (0, 1, 60, 0),
        (0, 1, 60.5, 100),
        (0, 1, True, 100),
    ],
)
def test_invalid_notes(values: tuple[float, float, int, int]) -> None:
    with pytest.raises(ValueError):
        NoteEvent(*values)


def test_internal_drum_token_is_not_a_midi_program() -> None:
    with pytest.raises(ValueError, match="General MIDI"):
        InstrumentTrack("Drums", 128, (NoteEvent(0, 1, 36),), is_drum=True)


def test_options_require_one_source() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ConversionOptions()
    with pytest.raises(ValueError, match="exactly one"):
        ConversionOptions(source="url", audio_file=Path("audio.wav"))
