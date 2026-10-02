"""Typer entry point: `clipper setup | run | eval`."""

from pathlib import Path
from typing import Annotated

import typer
from dotenv import find_dotenv, load_dotenv
from pydantic import ValidationError

from clipper.config import DEFAULT_CONFIG_PATH, Config, load_config

app = typer.Typer(
    help="Long video in, top-K vertical captioned clips out.",
    no_args_is_help=True,
    add_completion=False,
)

ConfigOption = Annotated[
    Path,
    typer.Option("--config", "-c", dir_okay=False, help="Path to config.toml."),
]


@app.callback()
def main() -> None:
    # The Anthropic SDK reads ANTHROPIC_API_KEY from the environment but not from
    # .env, so load it here. Existing environment variables win.
    load_dotenv(find_dotenv(usecwd=True), override=False)


def _load_config_or_exit(path: Path) -> Config:
    try:
        return load_config(path)
    except FileNotFoundError:
        typer.echo(f"Config file not found: {path}", err=True)
    except ValidationError as e:
        typer.echo(f"Invalid config {path}:\n{e}", err=True)
    raise typer.Exit(code=2)


def _not_implemented(command: str, phase: str) -> None:
    typer.echo(
        f"`clipper {command}` is not implemented yet (docs/plan.md phase {phase}).", err=True
    )
    raise typer.Exit(code=1)


@app.command()
def setup() -> None:
    """Download pinned model files to models/ (SHA-256 checked)."""
    _not_implemented("setup", "6")


@app.command()
def run(
    video: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Input video file."),
    ],
    top: Annotated[int, typer.Option("--top", "-k", min=1, help="Number of clips to make.")] = 5,
    config: ConfigOption = DEFAULT_CONFIG_PATH,
) -> None:
    """Make the top clips from VIDEO into out/<name>/."""
    _load_config_or_exit(config)
    _not_implemented("run", "2-9")


@app.command("eval")
def eval_(
    videos: Annotated[
        Path,
        typer.Option(
            "--videos", exists=True, file_okay=False, help="Folder of labeled source videos."
        ),
    ],
    config: ConfigOption = DEFAULT_CONFIG_PATH,
) -> None:
    """Score picks against hand labels in eval/labels/ (precision@5, recall@10)."""
    _load_config_or_exit(config)
    _not_implemented("eval", "8")
