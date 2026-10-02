from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from clipper.models import (
    Candidate,
    CandidateSet,
    ClipPlan,
    ClipResult,
    CropTrack,
    Features,
    LabelSet,
    Moment,
    Score,
    ScoreSet,
    Selection,
    Sentence,
    Transcript,
    Word,
    read_model,
    write_model,
)

SHA = "a" * 64


def _words() -> list[Word]:
    return [
        Word(text="Hello", start=0.0, end=0.4, probability=0.99),
        Word(text="there.", start=0.4, end=0.9, probability=0.95),
        Word(text="Bye.", start=1.2, end=1.5, probability=0.9),
    ]


def _transcript() -> Transcript:
    return Transcript(
        words=_words(),
        sentences=[
            Sentence(start=0.0, end=0.9, first_word=0, last_word=1),
            Sentence(start=1.2, end=1.5, first_word=2, last_word=2),
        ],
    )


def _score(cid: str = "c1", **kw: Any) -> Score:
    base: dict[str, Any] = dict(
        candidate_id=cid,
        hook=4,
        standalone=3,
        payoff=5,
        energy=0,
        reason="Strong opening question.",
        title="Why sourdough needs time",
    )
    return Score(**{**base, **kw})


def _clip(rank: int, cid: str) -> ClipPlan:
    return ClipPlan(
        rank=rank, candidate_id=cid, start=10.0, end=40.0, title="A title", final_score=3.2
    )


FEATURES = Features(loudness_db=-18.5, peaks=3, words_per_sec=2.7, questions=1, exclamations=0)

EXAMPLES: list[BaseModel] = [
    _transcript(),
    CandidateSet(
        candidates=[
            Candidate(id="c1", start=0.0, end=30.0, text="Hi."),
            Candidate(id="c2", start=15.0, end=45.0, text="Yo!", features=FEATURES),
        ]
    ),
    ScoreSet(scores=[_score("c1"), _score("c2")]),
    Selection(clips=[_clip(2, "c2"), _clip(1, "c1")]),
    CropTrack(rank=1, fps=30, center_x=[0.5, 0.52, 1.0], face_found=[True, True, False]),
    ClipResult(
        path=Path("out/talk/clip_01.mp4"),
        duration=31.2,
        width=1080,
        height=1920,
        checks={"format": True, "sync": False},
    ),
    LabelSet(
        video_sha256=SHA,
        heldout=True,
        moments=[Moment(start=12.0, end=40.5, note="the reveal"), Moment(start=60, end=90)],
    ),
]


@pytest.mark.parametrize("model", EXAMPLES, ids=lambda m: type(m).__name__)
def test_json_round_trip(model: BaseModel) -> None:
    assert type(model).model_validate_json(model.model_dump_json()) == model


@pytest.mark.parametrize("model", EXAMPLES, ids=lambda m: type(m).__name__)
def test_write_read_round_trip(model: BaseModel, tmp_path: Path) -> None:
    path = tmp_path / "sub" / "stage.json"
    write_model(path, model)
    assert read_model(path, type(model)) == model
    assert [p.name for p in path.parent.iterdir()] == ["stage.json"]  # no temp files left


def test_write_model_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "scores.json"
    write_model(path, ScoreSet(scores=[_score("c1")]))
    write_model(path, ScoreSet(scores=[]))
    assert read_model(path, ScoreSet).scores == []


def test_read_model_rejects_wrong_contract(tmp_path: Path) -> None:
    path = tmp_path / "scores.json"
    write_model(path, ScoreSet(scores=[_score()]))
    with pytest.raises(ValidationError):
        read_model(path, Selection)


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError, match="extra"):
        Word.model_validate({"text": "a", "start": 0, "end": 1, "probability": 1, "speaker": 1})


def test_models_are_frozen() -> None:
    w = _words()[0]
    with pytest.raises(ValidationError):
        w.start = 5.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "build",
    [
        lambda: Word(text="a", start=1.0, end=0.5, probability=1),
        lambda: Word(text="", start=0, end=1, probability=1),
        lambda: Word(text="a", start=0, end=1, probability=1.5),
        lambda: Word(text="a", start=-0.1, end=1, probability=1),
        lambda: Word(text="a", start=float("nan"), end=1, probability=1),
        lambda: Sentence(start=2, end=1, first_word=0, last_word=0),
        lambda: Sentence(start=0, end=1, first_word=3, last_word=2),
        lambda: Candidate(id="c", start=5, end=5, text=""),
        lambda: Candidate(id="", start=0, end=5, text=""),
        lambda: ClipPlan(rank=0, candidate_id="c", start=0, end=1, title="t", final_score=0),
        lambda: ClipPlan(rank=1, candidate_id="c", start=3, end=1, title="t", final_score=0),
        lambda: Moment(start=10, end=9),
        lambda: Features(loudness_db=-10, peaks=-1, words_per_sec=1, questions=0, exclamations=0),
    ],
)
def test_invalid_values_rejected(build: Any) -> None:
    with pytest.raises(ValidationError):
        build()


def test_zero_length_word_allowed() -> None:
    assert Word(text="a", start=1.0, end=1.0, probability=0).end == 1.0


@pytest.mark.parametrize("field", ["hook", "standalone", "payoff", "energy"])
@pytest.mark.parametrize("value", [-1, 6, 2.5])
def test_score_range(field: str, value: Any) -> None:
    with pytest.raises(ValidationError, match=field):
        _score(**{field: value})


def test_score_bounds_inclusive() -> None:
    s = _score(hook=0, standalone=5)
    assert (s.hook, s.standalone) == (0, 5)


def test_title_stripped_and_40_chars_allowed() -> None:
    assert _score(title="  " + "x" * 40 + " ").title == "x" * 40


@pytest.mark.parametrize("title", ["x" * 41, "", "   ", "two\nlines", "tab\there", "nul\x00"])
def test_bad_title_rejected(title: str) -> None:
    with pytest.raises(ValidationError, match="title"):
        _score(title=title)
    with pytest.raises(ValidationError, match="title"):
        ClipPlan(rank=1, candidate_id="c", start=0, end=1, title=title, final_score=0)


def test_empty_reason_rejected() -> None:
    with pytest.raises(ValidationError, match="reason"):
        _score(reason="")


def test_transcript_index_out_of_range() -> None:
    with pytest.raises(ValidationError, match="out of range"):
        Transcript(words=_words(), sentences=[Sentence(start=0, end=1, first_word=0, last_word=3)])


def test_transcript_word_starts_backwards() -> None:
    words = _words()
    words[2] = Word(text="Bye.", start=0.3, end=1.5, probability=0.9)
    with pytest.raises(ValidationError, match="backwards"):
        Transcript(words=words, sentences=[])


@pytest.mark.parametrize("spans", [[(0, 1), (1, 2)], [(1, 2), (0, 0)]])
def test_transcript_sentences_overlap_or_unordered(spans: list[tuple[int, int]]) -> None:
    words = _words()
    sentences = [
        Sentence(start=words[a].start, end=words[b].end, first_word=a, last_word=b)
        for a, b in spans
    ]
    with pytest.raises(ValidationError, match="ordered"):
        Transcript(words=_words(), sentences=sentences)


def test_empty_transcript_allowed() -> None:
    assert Transcript(words=[], sentences=[]).words == []


def test_duplicate_candidate_ids() -> None:
    c = Candidate(id="c1", start=0, end=30, text="")
    with pytest.raises(ValidationError, match="duplicate candidate id"):
        CandidateSet(candidates=[c, c])


def test_duplicate_score_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate candidate_id"):
        ScoreSet(scores=[_score("c1"), _score("c1")])


@pytest.mark.parametrize("ranks", [[1, 1], [1, 3], [2]])
def test_selection_ranks_contiguous(ranks: list[int]) -> None:
    with pytest.raises(ValidationError, match="ranks"):
        Selection(clips=[_clip(r, f"c{i}") for i, r in enumerate(ranks)])


def test_selection_duplicate_candidate() -> None:
    with pytest.raises(ValidationError, match="duplicate candidate_id"):
        Selection(clips=[_clip(1, "c1"), _clip(2, "c1")])


def test_crop_track_lengths_must_match() -> None:
    with pytest.raises(ValidationError, match="one entry per frame"):
        CropTrack(rank=1, fps=30, center_x=[0.5, 0.5], face_found=[True])


@pytest.mark.parametrize("x", [-0.01, 1.01])
def test_crop_center_is_fraction(x: float) -> None:
    with pytest.raises(ValidationError, match="center_x"):
        CropTrack(rank=1, fps=30, center_x=[x], face_found=[True])


def test_crop_fps_positive() -> None:
    with pytest.raises(ValidationError, match="fps"):
        CropTrack(rank=1, fps=0, center_x=[], face_found=[])


def test_clip_result_ok() -> None:
    def result(checks: dict[str, bool]) -> ClipResult:
        return ClipResult(path=Path("c.mp4"), duration=30, width=1080, height=1920, checks=checks)

    assert result({"a": True, "b": True}).ok
    assert not result({"a": True, "b": False}).ok


@pytest.mark.parametrize("sha", ["A" * 64, "a" * 63, "g" * 64, ""])
def test_label_set_bad_sha(sha: str) -> None:
    with pytest.raises(ValidationError, match="video_sha256"):
        LabelSet(video_sha256=sha, heldout=False, moments=[Moment(start=0, end=20)])


def test_label_set_requires_heldout_and_moments() -> None:
    with pytest.raises(ValidationError, match="heldout"):
        LabelSet.model_validate({"video_sha256": SHA, "moments": [{"start": 0, "end": 20}]})
    with pytest.raises(ValidationError, match="moments"):
        LabelSet(video_sha256=SHA, heldout=False, moments=[])


def test_label_set_from_hand_written_json() -> None:
    text = '{"video_sha256": "%s", "heldout": false, "moments": [{"start": 61, "end": 95.5}]}'
    labels = LabelSet.model_validate_json(text % SHA)
    assert labels.moments[0] == Moment(start=61.0, end=95.5, note="")


@pytest.mark.parametrize("value", ["true", "4.0", '"3"'])
def test_score_from_json_must_be_integer(value: str) -> None:
    raw = (
        '{"candidate_id": "c1", "hook": %s, "standalone": 4, "payoff": 3, "energy": 2,'
        ' "reason": "r", "title": "t"}'
    )
    assert Score.model_validate_json(raw % "4").hook == 4
    with pytest.raises(ValidationError, match="hook"):
        Score.model_validate_json(raw % value)


@pytest.mark.parametrize(("start", "end"), [(0.1, 0.9), (0.0, 1.0), (5.0, 6.0)])
def test_transcript_sentence_must_span_its_words(start: float, end: float) -> None:
    with pytest.raises(ValidationError, match="must span its words"):
        Transcript(
            words=_words(), sentences=[Sentence(start=start, end=end, first_word=0, last_word=1)]
        )


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_strings_rejected(blank: str) -> None:
    with pytest.raises(ValidationError, match="reason"):
        _score(reason=blank)
    with pytest.raises(ValidationError, match="id"):
        Candidate(id=blank, start=0, end=5, text="")
