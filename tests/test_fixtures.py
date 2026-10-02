import json
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT

FIXTURES = REPO_ROOT / "tests" / "fixtures"
VIDEO = FIXTURES / "talk.mp4"
TEXT = FIXTURES / "talk.txt"
MAX_BYTES = 2_000_000


def test_every_fixture_under_2_mb() -> None:
    sizes = {p.name: p.stat().st_size for p in FIXTURES.iterdir() if p.is_file()}
    assert "talk.mp4" in sizes
    assert all(size < MAX_BYTES for size in sizes.values()), sizes


def test_spoken_text_has_several_topics() -> None:
    text = TEXT.read_text(encoding="utf-8")
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    assert len(paragraphs) >= 5
    assert 350 <= len(text.split()) <= 500  # about 150 s of speech
    assert "?" in text and "!" in text


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not on PATH")
def test_video_format() -> None:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,channels",
            "-of",
            "json",
            str(VIDEO),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    info = json.loads(out)
    assert abs(float(info["format"]["duration"]) - 150.0) <= 0.1
    video = [s for s in info["streams"] if s["codec_type"] == "video"]
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    assert len(video) == 1 and len(audio) == 1
    v, a = video[0], audio[0]
    assert (v["codec_name"], v["width"], v["height"]) == ("h264", 480, 270)
    assert (v["r_frame_rate"], v["pix_fmt"]) == ("30/1", "yuv420p")
    assert (a["codec_name"], a["channels"]) == ("aac", 1)
