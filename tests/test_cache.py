import hashlib
from pathlib import Path

import pytest

from clipper.cache import (
    STAGES,
    done_path,
    invalidate_from,
    is_done,
    mark_done,
    sha256_file,
    stage_key,
    work_dir,
)
from clipper.config import load_config
from tests.conftest import REPO_ROOT


@pytest.fixture
def inputs(tmp_path: Path) -> list[Path]:
    a = tmp_path / "a.json"
    b = tmp_path / "b.wav"
    a.write_text('{"x": 1}')
    b.write_bytes(b"\x00\x01" * 10)
    return [a, b]


def test_stages_match_plan_order() -> None:
    assert STAGES == (
        "ingest",
        "transcribe",
        "candidates",
        "signals",
        "score",
        "select",
        "reframe",
        "captions",
        "render",
        "report",
    )


def test_sha256_file_matches_hashlib_across_chunks(tmp_path: Path) -> None:
    data = bytes(range(256)) * 9000  # > 2 MiB, several read chunks
    p = tmp_path / "big.bin"
    p.write_bytes(data)
    assert sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_work_dir(tmp_path: Path) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"video")
    expected = hashlib.sha256(b"video").hexdigest()[:16]
    assert work_dir(video) == Path("work") / expected
    assert work_dir(video, root=tmp_path / "w") == tmp_path / "w" / expected
    assert not (tmp_path / "w").exists()


def test_key_is_stable(inputs: list[Path]) -> None:
    k1 = stage_key("score", inputs, {"model": "m", "batch": 20})
    k2 = stage_key("score", inputs, {"batch": 20, "model": "m"})
    assert k1 == k2
    assert len(k1) == 64


def test_key_changes_with_file_content(inputs: list[Path]) -> None:
    before = stage_key("score", inputs, {})
    inputs[0].write_text('{"x": 2}')
    assert stage_key("score", inputs, {}) != before


@pytest.mark.parametrize(
    "settings",
    [{"model": "other"}, {"model": "m", "extra": None}, {"model": "m", "w": {"hook": 0.31}}],
)
def test_key_changes_with_settings(inputs: list[Path], settings: dict[str, object]) -> None:
    base = stage_key("score", inputs, {"model": "m", "w": {"hook": 0.3}})
    assert stage_key("score", inputs, settings) != base


def test_key_changes_with_stage_and_input_order(inputs: list[Path]) -> None:
    base = stage_key("score", inputs, {})
    assert stage_key("select", inputs, {}) != base
    assert stage_key("score", inputs[::-1], {}) != base
    assert stage_key("score", inputs[:1], {}) != base


def test_key_ignores_input_path(inputs: list[Path], tmp_path: Path) -> None:
    moved = tmp_path / "elsewhere" / "renamed.json"
    moved.parent.mkdir()
    moved.write_bytes(inputs[0].read_bytes())
    assert stage_key("score", [moved, inputs[1]], {}) == stage_key("score", inputs, {})


def test_key_accepts_pydantic_settings(inputs: list[Path]) -> None:
    cfg = load_config(REPO_ROOT / "config.toml")
    k = stage_key("select", inputs, {"weights": cfg.weights})
    assert k == stage_key("select", inputs, {"weights": cfg.weights.model_dump()})
    changed = cfg.weights.model_copy(update={"hook": 0.99})
    assert stage_key("select", inputs, {"weights": changed}) != k


@pytest.mark.parametrize("bad", [{1, 2}, Path("x"), float("nan")])
def test_key_rejects_unhashable_settings(inputs: list[Path], bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        stage_key("score", inputs, {"bad": bad})


def test_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        stage_key("score", [tmp_path / "missing.json"], {})


@pytest.mark.parametrize(
    "call",
    [
        lambda w: stage_key("scoring", [], {}),
        lambda w: done_path(w, "Score"),
        lambda w: is_done(w, "nope", "k"),
        lambda w: mark_done(w, "nope", "k"),
        lambda w: invalidate_from(w, "nope"),
    ],
)
def test_unknown_stage_raises(tmp_path: Path, call: object) -> None:
    with pytest.raises(ValueError, match="unknown stage"):
        call(tmp_path)  # type: ignore[operator]


def test_done_round_trip(tmp_path: Path) -> None:
    work = tmp_path / "work" / "abc"
    out = work / "scores.json"
    assert not is_done(work, "score", "k1")
    out.parent.mkdir(parents=True)
    out.write_text("{}")
    mark_done(work, "score", "k1")
    assert done_path(work, "score") == work / "score.done"
    assert is_done(work, "score", "k1", [out])
    assert not is_done(work, "score", "k2", [out])
    assert not is_done(work, "select", "k1")


def test_done_requires_outputs(tmp_path: Path) -> None:
    mark_done(tmp_path, "render", "k")
    assert is_done(tmp_path, "render", "k")
    assert not is_done(tmp_path, "render", "k", [tmp_path / "clip_01.mp4"])


def test_mark_done_creates_folder_and_overwrites(tmp_path: Path) -> None:
    work = tmp_path / "new"
    mark_done(work, "ingest", "old")
    mark_done(work, "ingest", "new")
    assert is_done(work, "ingest", "new")
    assert sorted(p.name for p in work.iterdir()) == ["ingest.done"]


def test_invalidate_from(tmp_path: Path) -> None:
    for s in STAGES:
        mark_done(tmp_path, s, "k")
    invalidate_from(tmp_path, "score")
    kept = [s for s in STAGES if is_done(tmp_path, s, "k")]
    assert kept == ["ingest", "transcribe", "candidates", "signals"]
    invalidate_from(tmp_path, "score")  # idempotent with markers already gone
    invalidate_from(tmp_path, "ingest")
    assert list(tmp_path.iterdir()) == []
