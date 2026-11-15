import wave
from pathlib import Path

import pytest


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "source with spaces.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(bytes(1600 * 2 * 2))
    return path
