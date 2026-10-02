"""Stage caching: hash inputs + settings, skip a stage when its .done file matches."""

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel

from clipper.models import atomic_write_text

# Bump to invalidate every cached stage (e.g. after a change to how keys are built).
CACHE_VERSION = 1

STAGES = (
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

_CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def work_dir(video: Path, root: Path = Path("work")) -> Path:
    """work/<first 16 hex chars of the video's SHA-256>/ (not created here)."""
    return root / sha256_file(video)[:16]


def _check_stage(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"setting of type {type(value).__name__} is not JSON-serializable")


def stage_key(stage: str, inputs: Sequence[Path], settings: Mapping[str, object]) -> str:
    """Hash of the stage name, input file contents (in order, paths ignored) and settings.

    Pass settings from the validated Config so types are stable: 1 and 1.0 hash differently.
    """
    _check_stage(stage)
    payload = {
        "version": CACHE_VERSION,
        "stage": stage,
        "inputs": [sha256_file(p) for p in inputs],
        "settings": settings,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def done_path(work: Path, stage: str) -> Path:
    _check_stage(stage)
    return work / f"{stage}.done"


def is_done(work: Path, stage: str, key: str, outputs: Iterable[Path] = ()) -> bool:
    """True when <stage>.done holds this key and every output file still exists."""
    marker = done_path(work, stage)
    try:
        stored = marker.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return False
    return stored == key and all(p.exists() for p in outputs)


def mark_done(work: Path, stage: str, key: str) -> None:
    """Record a finished stage. Call only after its outputs are written."""
    atomic_write_text(done_path(work, stage), key + "\n")


def invalidate_from(work: Path, stage: str) -> None:
    """Remove the .done markers of `stage` and every later stage (`--force <stage>`)."""
    _check_stage(stage)
    for later in STAGES[STAGES.index(stage) :]:
        done_path(work, later).unlink(missing_ok=True)
