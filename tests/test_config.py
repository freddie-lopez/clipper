import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from clipper.config import Config, load_config
from tests.conftest import REPO_ROOT

CONFIG_PATH = REPO_ROOT / "config.toml"

PLAN_KEYS = {
    "scoring_model",
    "scoring_price_input_per_mtok",
    "scoring_price_output_per_mtok",
    "batch_size",
    "weights",
    "clip_min_s",
    "clip_max_s",
    "candidates_per_hour_max",
    "whisper_engine",
    "whisper_model",
    "ffmpeg_bin",
}
WEIGHT_KEYS = {"hook", "standalone", "payoff", "energy", "loudness", "rate"}


def _raw() -> dict[str, object]:
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(text)
    return p


def test_repo_config_has_every_plan_key() -> None:
    raw = _raw()
    assert set(raw) == PLAN_KEYS
    assert isinstance(raw["weights"], dict)
    assert set(raw["weights"]) == WEIGHT_KEYS


def test_repo_config_loads() -> None:
    cfg = load_config(CONFIG_PATH)
    assert cfg.clip_min_s == 20.0
    assert cfg.clip_max_s == 60.0
    assert cfg.candidates_per_hour_max == 300
    assert cfg.batch_size > 0
    assert cfg.scoring_model


def test_missing_key_rejected(tmp_path: Path) -> None:
    text = CONFIG_PATH.read_text().replace('ffmpeg_bin = "ffmpeg"', "")
    with pytest.raises(ValidationError, match="ffmpeg_bin"):
        load_config(_write(tmp_path, text))


def test_unknown_key_rejected(tmp_path: Path) -> None:
    text = "typo_key = 1\n" + CONFIG_PATH.read_text()
    with pytest.raises(ValidationError, match="typo_key"):
        load_config(_write(tmp_path, text))


def test_missing_weight_rejected() -> None:
    raw = _raw()
    weights = dict(raw["weights"])  # type: ignore[call-overload]
    del weights["rate"]
    with pytest.raises(ValidationError, match="rate"):
        Config.model_validate({**raw, "weights": weights})


@pytest.mark.parametrize(("lo", "hi"), [(60.0, 20.0), (30.0, 30.0)])
def test_clip_bounds_must_be_ordered(lo: float, hi: float) -> None:
    with pytest.raises(ValidationError, match="clip_min_s"):
        Config.model_validate({**_raw(), "clip_min_s": lo, "clip_max_s": hi})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("batch_size", 0),
        ("candidates_per_hour_max", -1),
        ("scoring_price_input_per_mtok", -0.5),
        ("whisper_engine", "openai-whisper"),
        ("scoring_model", ""),
    ],
)
def test_invalid_values_rejected(key: str, value: object) -> None:
    with pytest.raises(ValidationError, match=key):
        Config.model_validate({**_raw(), key: value})


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")
