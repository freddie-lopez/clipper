"""Load and validate config.toml."""

import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path("config.toml")


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hook: float = Field(ge=0)
    standalone: float = Field(ge=0)
    payoff: float = Field(ge=0)
    energy: float = Field(ge=0)
    loudness: float = Field(ge=0)
    rate: float = Field(ge=0)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scoring_model: str = Field(min_length=1)
    scoring_price_input_per_mtok: float = Field(ge=0)
    scoring_price_output_per_mtok: float = Field(ge=0)
    batch_size: int = Field(gt=0)
    weights: Weights
    clip_min_s: float = Field(gt=0)
    clip_max_s: float = Field(gt=0)
    candidates_per_hour_max: int = Field(gt=0)
    whisper_engine: Literal["faster-whisper", "mlx-whisper"]
    whisper_model: str = Field(min_length=1)
    ffmpeg_bin: str = Field(min_length=1)

    @model_validator(mode="after")
    def _clip_bounds(self) -> Self:
        if self.clip_min_s >= self.clip_max_s:
            raise ValueError(
                f"clip_min_s ({self.clip_min_s}) must be < clip_max_s ({self.clip_max_s})"
            )
        return self


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read a TOML config file; raises on missing, unknown or invalid keys."""
    with path.open("rb") as f:
        return Config.model_validate(tomllib.load(f))
