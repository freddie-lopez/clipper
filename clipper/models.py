"""Pydantic contracts for every stage file in work/<hash>/. Stages talk only through these."""

import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]
# Strict: the AI's JSON must give real integers; true or 4.0 is invalid and triggers the retry.
Score05 = Annotated[int, Field(ge=0, le=5, strict=True)]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

TITLE_MAX_CHARS = 40


def _plain_title(value: str) -> str:
    # Category C covers control and format characters (incl. emoji joiners): titles stay plain.
    value = value.strip()
    if not 1 <= len(value) <= TITLE_MAX_CHARS:
        raise ValueError(f"title must be 1-{TITLE_MAX_CHARS} characters, got {len(value)}")
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        raise ValueError("title must be plain text (no newlines or control characters)")
    return value


Title = Annotated[str, AfterValidator(_plain_title)]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Span(_Contract):
    """A time span in seconds of the source video with end > start."""

    start: Seconds
    end: Seconds

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be > start ({self.start})")
        return self


class Word(_Contract):
    text: NonEmpty
    start: Seconds
    end: Seconds
    probability: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) must be >= start ({self.start})")
        return self


class Sentence(_Contract):
    start: Seconds
    end: Seconds
    first_word: int = Field(ge=0)
    last_word: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) must be >= start ({self.start})")
        if self.last_word < self.first_word:
            raise ValueError(
                f"last_word ({self.last_word}) must be >= first_word ({self.first_word})"
            )
        return self


class Transcript(_Contract):
    """transcript.json"""

    words: list[Word]
    sentences: list[Sentence]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        for prev, cur in zip(self.words, self.words[1:], strict=False):
            if cur.start < prev.start:
                raise ValueError(f"word starts go backwards at {cur.start}")
        prev_last = -1
        for s in self.sentences:
            if s.last_word >= len(self.words):
                raise ValueError(f"sentence word index {s.last_word} out of range")
            if s.first_word <= prev_last:
                raise ValueError("sentences must be ordered and not overlap")
            first, last = self.words[s.first_word], self.words[s.last_word]
            if (s.start, s.end) != (first.start, last.end):
                raise ValueError(
                    f"sentence {s.start}-{s.end} must span its words {first.start}-{last.end}"
                )
            prev_last = s.last_word
        return self


class Features(_Contract):
    loudness_db: float = Field(allow_inf_nan=False)
    peaks: int = Field(ge=0)
    words_per_sec: float = Field(ge=0, allow_inf_nan=False)
    questions: int = Field(ge=0)
    exclamations: int = Field(ge=0)


class Candidate(_Span):
    id: NonEmpty
    text: str
    features: Features | None = None


class CandidateSet(_Contract):
    """candidates.json (features unset) and signals.json (features filled)."""

    candidates: list[Candidate]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        _require_unique([c.id for c in self.candidates], "candidate id")
        return self


class Score(_Contract):
    candidate_id: NonEmpty
    hook: Score05
    standalone: Score05
    payoff: Score05
    energy: Score05
    reason: NonEmpty
    title: Title


class ScoreSet(_Contract):
    """scores.json"""

    scores: list[Score]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        _require_unique([s.candidate_id for s in self.scores], "candidate_id")
        return self


class ClipPlan(_Span):
    rank: int = Field(ge=1)
    candidate_id: NonEmpty
    title: Title
    final_score: float = Field(allow_inf_nan=False)


class Selection(_Contract):
    """selection.json"""

    clips: list[ClipPlan]

    @model_validator(mode="after")
    def _ranks(self) -> Self:
        ranks = sorted(c.rank for c in self.clips)
        if ranks != list(range(1, len(self.clips) + 1)):
            raise ValueError(f"ranks must be 1..{len(self.clips)} with no gaps, got {ranks}")
        _require_unique([c.candidate_id for c in self.clips], "candidate_id")
        return self


class CropTrack(_Contract):
    """crops/clip_NN.json. center_x is the crop center as a fraction of source width."""

    rank: int = Field(ge=1)
    fps: float = Field(gt=0, allow_inf_nan=False)
    center_x: list[Annotated[float, Field(ge=0, le=1)]]
    face_found: list[bool]

    @model_validator(mode="after")
    def _same_length(self) -> Self:
        if len(self.center_x) != len(self.face_found):
            raise ValueError(
                f"center_x ({len(self.center_x)}) and face_found ({len(self.face_found)}) "
                "must have one entry per frame"
            )
        return self


class ClipResult(_Contract):
    path: Path
    duration: float = Field(gt=0, allow_inf_nan=False)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    checks: dict[str, bool]

    @property
    def ok(self) -> bool:
        return all(self.checks.values())


class Moment(_Span):
    note: str = ""


class LabelSet(_Contract):
    """eval/labels/<name>.json: hand-picked moments for one video."""

    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    heldout: bool
    moments: list[Moment] = Field(min_length=1)


def _require_unique(values: list[str], what: str) -> None:
    seen: set[str] = set()
    for v in values:
        if v in seen:
            raise ValueError(f"duplicate {what}: {v!r}")
        seen.add(v)


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file in the same folder, then rename, so readers never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_model(path: Path, model: BaseModel) -> None:
    """Write a stage file as indented JSON, atomically."""
    atomic_write_text(path, model.model_dump_json(indent=2) + "\n")


def read_model[M: BaseModel](path: Path, cls: type[M]) -> M:
    """Read and validate a JSON stage file."""
    return cls.model_validate_json(path.read_bytes())
