# Clipper
Local CLI: long video in, top-K vertical captioned clips out.
Plan (source of truth): docs/plan.md. Decisions: docs/decisions/.

## Commands
- uv run clipper run <video> --top 5      # cli.py loads .env via python-dotenv
- uv run clipper setup                    # downloads pinned model files to models/ (SHA-256 checked)
- uv run pytest -q                        # fast, offline; slow tests excluded by default (addopts)
- uv run pytest -q -m slow                # real Whisper/MediaPipe/ffmpeg runs, local only
- uv run ruff check . && uv run mypy clipper
- uv run python tests/fixtures/make_fixtures.py   # macOS only (uses `say`)

## Environment
- Python 3.12 exactly (requires-python = ">=3.12,<3.13").
- ffmpeg must have the `subtitles` filter (Homebrew `ffmpeg-full`). Ingest fails fast if it's missing.
- OpenCV comes only from `opencv-contrib-python` (MediaPipe's dependency). Never add `opencv-python`.
- MediaPipe >= 1.0 has no `mp.solutions`: use the Tasks API (`mediapipe.tasks.python.vision.FaceDetector`).
- mlx-whisper is macOS-arm64 only: platform marker, never imported at module top level.

## Rules
- Work one phase of docs/plan.md at a time. Plan before editing.
- Stages talk only through files in work/<hash>/, defined in clipper/models.py.
- Every stage has tests. AI calls are mocked in tests; pytest never calls the API or downloads models.
- Tests needing models or real decoding are marked @pytest.mark.slow; CI runs the rest.
- Read the model name and every tunable from config.toml; never hard-code them.
- Build subprocess commands as argument lists, never shell strings.
- Never read or print .env. Never commit work/, out/, models/, or media outside tests/fixtures/
  (each fixture under 2 MB).
- Never git push. Commit only after the reviewer agent returns SIGN-OFF.
- Only use videos we have rights to clip (own recordings or sources that allow clipping).

## Definition of done for every phase
1. Tests, ruff and mypy pass locally; the previous phase's CI run is green (`gh run list -L 1`).
2. The phase's done criteria in docs/plan.md are met, with evidence.
3. A devlog entry exists: docs/devlog/YYYY-MM-DD-phase-N.md (what was built, what broke, numbers).
4. The reviewer agent returns SIGN-OFF (it checks the devlog too).
