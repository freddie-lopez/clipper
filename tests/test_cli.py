import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from clipper.cli import app
from tests.conftest import REPO_ROOT

runner = CliRunner()
CONFIG = str(REPO_ROOT / "config.toml")


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("setup", "run", "eval"):
        assert cmd in result.output


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage" in result.output


@pytest.mark.parametrize("cmd", ["setup", "run", "eval"])
def test_subcommand_help(cmd: str) -> None:
    result = runner.invoke(app, [cmd, "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_setup_stub_fails_loudly() -> None:
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 1
    assert "not implemented" in result.output


def test_run_stub_fails_loudly(tmp_path: Path) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"")
    result = runner.invoke(app, ["run", str(video), "--top", "3", "--config", CONFIG])
    assert result.exit_code == 1
    assert "not implemented" in result.output


def test_run_rejects_missing_video(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(tmp_path / "missing.mp4"), "--config", CONFIG])
    assert result.exit_code == 2


def test_run_rejects_top_zero(tmp_path: Path) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"")
    result = runner.invoke(app, ["run", str(video), "--top", "0", "--config", CONFIG])
    assert result.exit_code == 2


def test_run_reports_missing_config(tmp_path: Path) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"")
    result = runner.invoke(app, ["run", str(video), "--config", str(tmp_path / "nope.toml")])
    assert result.exit_code == 2
    assert "Config file not found" in result.output


def test_run_reports_invalid_config(tmp_path: Path) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"")
    bad = tmp_path / "bad.toml"
    bad.write_text("batch_size = 0\n")
    result = runner.invoke(app, ["run", str(video), "--config", str(bad)])
    assert result.exit_code == 2
    assert "Invalid config" in result.output


def test_eval_stub_fails_loudly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["eval", "--videos", str(tmp_path), "--config", CONFIG])
    assert result.exit_code == 1
    assert "not implemented" in result.output


def test_dotenv_loaded_from_cwd(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("CLIPPER_TEST_DOTENV=from-file\n")
    os.environ.pop("CLIPPER_TEST_DOTENV", None)
    try:
        runner.invoke(app, ["setup"])
        assert os.environ.get("CLIPPER_TEST_DOTENV") == "from-file"
    finally:
        os.environ.pop("CLIPPER_TEST_DOTENV", None)


def test_dotenv_does_not_override_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("CLIPPER_TEST_DOTENV=from-file\n")
    monkeypatch.setenv("CLIPPER_TEST_DOTENV", "from-shell")
    runner.invoke(app, ["setup"])
    assert os.environ["CLIPPER_TEST_DOTENV"] == "from-shell"
