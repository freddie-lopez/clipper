from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Run every test from an empty temp dir so the CLI never finds the repo's .env.
    monkeypatch.chdir(tmp_path)
