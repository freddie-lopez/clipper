# ADR 0001: Local-first pipeline of file-based stages

Status: accepted · Date: 2026-10-02 · Phase 1a

## Context
Clipper turns one long local video into the top-K vertical captioned clips. Its work is
heavy (transcription, face tracking, encoding) and runs on one M-series Mac. Only the
scoring step needs the network. The build is iterative: each stage must be testable on
its own, and reruns with tweaked settings must not redo hours of earlier work.

## Decision
- v1 is a local Python CLI (`clipper`, Typer). There is no server, queue or database.
- The pipeline has ten stages that run in order. Each stage talks to the others only
  through files in `work/<video-hash>/`, and each file is defined by a pydantic model in
  `clipper/models.py`. A stage never imports another stage's internals.
- Each stage writes a `.done` file holding the hash of its inputs plus settings, so a
  matching hash skips the stage and `--force <stage>` reruns it and every later stage.
- Every tunable, including the scoring model name and price, lives in `config.toml`
  and is validated at load time (`clipper/config.py`, unknown keys rejected).
- Final outputs go only to `out/<name>/`.

## Consequences
- Any stage can be tested from fixture files, without running the stages before it.
  CI runs offline with mocked AI and no model downloads.
- Reruns are cheap, and the cache also makes repeat AI scoring free.
- Disk use grows with `work/` (audio WAV, crop tracks), so it needs manual cleanup.
- No concurrency across videos and no remote use. Both are deferred; the v2 dashboard
  would wrap this pipeline rather than replace it.

## Alternatives rejected
- In-memory pipeline in one process: no caching, so stages can't be tested in isolation.
- Service plus job queue: unnecessary for a single-user local tool.
