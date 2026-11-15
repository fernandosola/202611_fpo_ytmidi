from pathlib import Path
from typing import Any

import pytest

from youtube_midi import download
from youtube_midi.errors import DownloadError
from youtube_midi.models import MediaInfo

VIDEO_ID = "abcdefghijk"


@pytest.mark.parametrize(
    "source",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?t=10",
        f"https://youtube.com/shorts/{VIDEO_ID}",
        f"https://youtube.com/embed/{VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}&list=ignored",
    ],
)
def test_canonical_video_url(source: str) -> None:
    assert download.validate_youtube_url(source) == f"https://www.youtube.com/watch?v={VIDEO_ID}"


@pytest.mark.parametrize(
    "source",
    [
        "http://youtube.com/watch?v=abcdefghijk",
        "https://youtube.com.evil.example/watch?v=abcdefghijk",
        "https://youtube.com@evil.example/watch?v=abcdefghijk",
        "https://user:pass@youtube.com/watch?v=abcdefghijk",
        "https://youtube.com:8080/watch?v=abcdefghijk",
        "https://youtube.com:invalid/watch?v=abcdefghijk",
        "https://youtube.com/playlist?list=123",
        "https://youtube.com/@channel",
        "https://youtube.com/watch?v=abcdefghijk&v=zyxwvutsrqp",
        "https://youtu.be/short",
        "file:///etc/passwd",
    ],
)
def test_rejects_unsupported_urls(source: str) -> None:
    with pytest.raises(DownloadError):
        download.validate_youtube_url(source)


@pytest.fixture
def fake_downloader(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "info": {"id": VIDEO_ID, "title": "Test", "duration": 1, "availability": "public"},
        "downloaded_bytes": 10,
        "settings": {},
    }

    class FakeYoutubeDL:
        def __init__(self, settings: dict[str, Any]) -> None:
            state["settings"] = settings

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def extract_info(self, source: str, *, download: bool) -> dict[str, Any]:
            if download:
                path = Path(state["settings"]["outtmpl"].replace("%(id)s", VIDEO_ID))
                path = Path(str(path).replace("%(ext)s", "mkv"))
                state["settings"]["progress_hooks"][0](
                    {"filename": str(path), "downloaded_bytes": state["downloaded_bytes"]}
                )
                path.write_bytes(b"fake video")
            return state["info"]

    monkeypatch.setattr(download, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(download, "require_binary", lambda name: name)
    monkeypatch.setattr(
        download, "probe_media", lambda path, **kwargs: MediaInfo(path, 1, 16000, 2)
    )
    return state


def test_downloads_video_and_keeps_metadata(
    fake_downloader: dict[str, Any], tmp_path: Path
) -> None:
    path, metadata = download.download_video(f"https://youtu.be/{VIDEO_ID}", tmp_path / "video")
    assert path.suffix == ".mkv"
    assert metadata["id"] == VIDEO_ID
    assert fake_downloader["settings"]["format"] == "bv*+ba/b"
    assert fake_downloader["settings"]["noplaylist"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"duration": 1000},
        {"duration": None},
        {"duration": float("nan")},
        {"is_live": True},
        {"_type": "playlist"},
        {"availability": "private"},
        {"id": "differentid"},
    ],
)
def test_rejects_metadata(
    fake_downloader: dict[str, Any], tmp_path: Path, change: dict[str, Any]
) -> None:
    fake_downloader["info"].update(change)
    with pytest.raises(DownloadError):
        download.download_video(f"https://youtu.be/{VIDEO_ID}", tmp_path / "video")


def test_enforces_actual_download_size(fake_downloader: dict[str, Any], tmp_path: Path) -> None:
    fake_downloader["downloaded_bytes"] = 20
    with pytest.raises(DownloadError, match="byte limit"):
        download.download_video(
            f"https://youtu.be/{VIDEO_ID}", tmp_path / "video", max_download_size=10
        )


def test_refuses_existing_download_directory(
    fake_downloader: dict[str, Any], tmp_path: Path
) -> None:
    existing = tmp_path / "keep.txt"
    existing.write_text("keep", encoding="utf-8")
    with pytest.raises(DownloadError, match="empty"):
        download.download_video(f"https://youtu.be/{VIDEO_ID}", tmp_path)
    assert existing.read_text(encoding="utf-8") == "keep"
