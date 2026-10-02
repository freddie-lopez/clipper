# Clipper v1: Build Plan

Owner: Tsuki · Revised 2026-10-02 after review · Source of truth for every build phase.

Terms used here: an **ADR** is a one-page decision record. **precision@5** is how many of the tool's top 5 picks match your own picks. **VFR** means variable frame rate (common in phone and screen recordings).

## Goal and scope

v1 is a local command-line tool: one long video file in, the 5 best vertical, captioned clips out, plus a report explaining why each was picked. It runs on your Mac, is built in Claude Code, and is ready for GitHub.

```
clipper run talk.mp4 --top 5
→ out/talk/clip_01.mp4 … clip_05.mp4
→ out/talk/report.json + report.html
```

**In scope for v1:**
- Transcription with word-level timestamps
- Candidate moments scored by one structured AI call per batch
- Top clips picked with no overlaps
- 16:9 reframed to 9:16 by tracking faces
- Animated word-by-word captions and a hook title
- Rendering with ffmpeg, a report, and an evaluation harness

**Out of scope for v1 (the v2 list):**
- Downloading from YouTube or Twitch (v1 takes a local file)
- Posting to TikTok, Instagram or YouTube
- A review dashboard
- Twitch chat signals
- Languages other than English
- Multi-speaker split screen

## Success criteria

v1 is done when every row passes on your Mac and the reviewer agent signs off. These are starting targets: tune them after the first real runs and record any change in the devlog. Find or record one 60-minute source early, since criteria 1 and 2 need it.

| # | Criterion | Target | How it's checked |
| --- | --- | --- | --- |
| 1 | End to end | A 60-minute video produces 5 clips with no manual steps | `clipper run` on a real video |
| 2 | Speed | 60-minute video in ≤ 15 minutes on an M-series Mac (tune after first measurement) | Per-stage timings in the report |
| 3 | Clip length | 20 to 60 seconds each | Selector unit test + `ffprobe` on outputs |
| 4 | Clean cuts | Clips start and end on sentence boundaries, with padding: first word start − 0.15 s to last word end + 0.30 s, never reaching into a neighboring word | Unit test against word timestamps |
| 5 | No overlap | No two clips share more than 2 seconds | Selector unit test |
| 6 | Format and sync | 1080×1920, H.264 yuv420p + AAC, constant 30 fps, audio and video durations within 0.1 s | `ffprobe` check by the media-qa agent |
| 7 | Caption timing | Each caption word within ±150 ms of its transcript time | Caption file vs transcript |
| 8 | Framing | When the source shows a face, it's inside the crop in ≥ 90% of sampled seconds | Source-frame face boxes vs crop windows |
| 9 | Pick quality | precision@5 ≥ 0.6 on the held-out labeled videos (definition in Phase 8) | `clipper eval` |
| 10 | Repeatable | Reruns with the same input and settings reuse cached stages and give the same clips (a cold rerun of the AI step may differ slightly) | Run twice, diff the report |
| 11 | Offline tests | `pytest` passes in CI with no network, no API key and no model downloads (AI mocked, slow tests skipped) | GitHub Actions on every push |
| 12 | Cost | AI scoring under $0.50 per hour of video (depends on the model's price; tune after first measurement) | Token counts and model price logged in the report |

## Pipeline architecture

Ten stages run in order. Each stage reads files earlier stages wrote and writes its own file to `work/<video-hash>/`, so every stage is testable alone and a rerun only redoes stages whose inputs changed. After the first-run downloads of the Whisper and face-detector models, only stage 5 needs the network.

```
 1 Ingest → 2 Transcribe → 3 Candidates → 4 Signals → 5 Score (the one AI call)
                                                            ↓
10 Report ← 9 Render ← 8 Captions ← 7 Reframe ← 6 Select
          all stages read/write work/<video-hash>/ (cache)
```

| # | Stage | Reads | Writes | Tool |
| --- | --- | --- | --- | --- |
| 1 | Ingest | input video | `meta.json`, `audio.wav` (16 kHz mono); fails fast if ffmpeg lacks the `subtitles` filter | ffprobe, ffmpeg |
| 2 | Transcribe | `audio.wav` | `transcript.json`: words with start/end times, sentences | Whisper (engine picked in phase 2, ADR 0002) |
| 3 | Candidates | `transcript.json` | `candidates.json`: windows on sentence boundaries, 20–60 s, capped at 300 per hour | Python |
| 4 | Signals | `audio.wav`, candidates | `signals.json`: loudness peaks, speech rate, question/exclamation counts | numpy |
| 5 | Score | candidates + text | `scores.json`: hook, standalone, payoff, energy (0–5), reason, hook title (≤ 40 chars) | Claude API, one structured call per ~20 candidates |
| 6 | Select | scores + signals | `selection.json`: top K, weighted, no overlaps, spread out | Python |
| 7 | Reframe | video, selection | `crops/clip_NN.json`: smoothed crop center per frame | MediaPipe Tasks face detector at 5 fps + smoothing |
| 8 | Captions | transcript, selection | `captions/clip_NN.ass`: word-by-word, current word highlighted | Python writing ASS |
| 9 | Render | video, crops, captions, titles | `out/<name>/clip_NN.mp4` (1080×1920) | ffmpeg decode → numpy crop → ffmpeg encode |
| 10 | Report | everything | `report.json`, `report.html` | Python + Jinja2 |

**Caching rule.** Each stage writes a `.done` file holding the hash of its inputs plus settings. A matching hash means the stage is skipped. `--force <stage>` reruns that stage and everything after it.

**Data contracts** (pydantic models in `clipper/models.py`; stages talk only through these files):

| Model | Fields |
| --- | --- |
| `Word` | text, start, end, probability |
| `Sentence` | start, end, first_word, last_word (indices into the word list) |
| `Candidate` | id, start, end, text, features (loudness, peaks, words/sec, punctuation) |
| `Score` | candidate_id, hook, standalone, payoff, energy (0–5 each), reason, title (≤ 40 chars, plain text) |
| `ClipPlan` | rank, candidate_id, start, end, title, final_score |
| `CropTrack` | clip rank, fps, crop center x per frame, face_found per frame |
| `ClipResult` | path, duration, width, height, checks passed/failed |
| `LabelSet` | video_sha256, heldout (bool), moments: [{start, end, note}] |

**`config.toml` keys:** `scoring_model` (with its price per million input/output tokens next to it), `scoring_effort` (added in phase 4), `batch_size`, `weights.{hook, standalone, payoff, energy, loudness, rate}`, `clip_min_s`, `clip_max_s`, `candidates_per_hour_max`, `whisper_engine`, `whisper_model`, `ffmpeg_bin`.

**Scoring is one call, not an agent.** Stage 5 sends each batch with a fixed rubric and gets JSON back, validated by `Score`. Current models reject `temperature`: Opus 5.5 rejects `temperature`, `top_p` and `top_k` outright and Sonnet 5.5 rejects non-default values (400), so the call sends no sampling parameters; repeatability comes from the cache. Prompt version + model name + input text are hashed for caching, so a rerun on the same input returns the stored scores. No tools, loops or memory are needed, so a plain call is cheaper, faster and repeatable (ADR 0003).

## Tech stack and repo layout

Python 3.12 exactly (`uv python pin 3.12`; `requires-python = ">=3.12,<3.13"`), which has the widest wheel support across MediaPipe, PyAV, mlx and ctranslate2. Pin versions in `pyproject.toml` and commit `uv.lock`.

| Need | Choice | Why |
| --- | --- | --- |
| Packages | uv | Fast, one lockfile, `uv run` everywhere |
| CLI | Typer | Typed commands, free `--help` |
| Data models | pydantic v2 | Validates every stage file and the AI's JSON |
| Secrets | python-dotenv | `cli.py` loads `.env`; the SDK alone doesn't |
| Transcription | mlx-whisper (Apple GPU; marker `sys_platform == 'darwin' and platform_machine == 'arm64'`; pulls in torch, a large download) or faster-whisper (CPU), behind one `Transcriber` interface | Phase 2 timing test decides (ADR 0002); Linux CI never needs mlx |
| Audio features | numpy + soundfile | Loudness and peaks need nothing heavier |
| Faces | MediaPipe ≥ 1.0, Tasks API (`vision.FaceDetector`, VIDEO mode). There is no `mp.solutions` in 1.x | The model file is downloaded by `clipper setup` (pinned URL + SHA-256), never during tests |
| Video frames | `opencv-contrib-python` only (MediaPipe's dependency); never also `opencv-python`, which conflicts | Drawing debug overlays, image ops |
| Encode, subtitles | ffmpeg with libass: Homebrew `ffmpeg-full` (the slim `ffmpeg` formula no longer has the `subtitles` filter) | Decode, burn ASS captions, encode |
| AI scoring | `anthropic` Python SDK | Model name in `config.toml`, never hard-coded |
| Report | Jinja2 | One self-contained HTML file |
| Quality | pytest (`addopts = "-m 'not slow'"`), ruff, mypy strict on `clipper/` with `ignore_missing_imports` for mlx_whisper, mediapipe, faster_whisper, soundfile | Same checks locally and in CI |
| CI | GitHub Actions on Ubuntu: `astral-sh/setup-uv`, `uv sync --locked`, `sudo apt-get install -y ffmpeg` (Ubuntu's ffmpeg includes libass) | Offline tests + lint on every push |

```
clipper/
  CLAUDE.md                  project rules Claude Code reads every session
  .claude/
    settings.json            shared permissions + format hook (committed)
    settings.local.json      personal overrides (gitignored)
    agents/                  reviewer.md, media-qa.md, eval-analyst.md
  pyproject.toml  uv.lock  config.toml  .env.example  README.md
  clipper/
    cli.py                   Typer app: setup, run, eval
    models.py                pydantic contracts
    cache.py                 hashing + .done files
    stages/                  ingest, transcribe, candidates, signals,
                             score, select, reframe, captions, render, report
    prompts/score_v1.md      the scoring rubric, versioned
  tests/
    fixtures/                small committed fixtures (each < 2 MB) + their known text
    test_<stage>.py          one file per stage
  eval/
    labels/                  your hand-picked moments per video (LabelSet JSON)
    runs/                    eval results, one folder per run
  docs/
    plan.md                  this plan
    decisions/               ADRs
    devlog/                  dated entries
  work/  out/  models/       gitignored (agents' scratch lives in work/)
```

## Build it in Claude Code, step by step

Set up once (phase 0), then repeat the same loop for each build phase. Every phase ends with the reviewer's sign-off, a commit and a push, and the next phase starts only once CI is green.

### Phase 0: one-time setup (about 45 minutes)

1. Install the tools in Terminal (install Homebrew from brew.sh first if needed, and run the `brew shellenv` lines it prints). `ffmpeg-full` is "keg-only", meaning Homebrew doesn't put it on your PATH, so the `echo` line does that:
   ```
   curl -fsSL https://claude.ai/install.sh | bash
   brew install ffmpeg-full uv gh jq
   echo 'export PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH"' >> ~/.zshrc
   gh auth login
   ```
   Then open a new Terminal window and check that ffmpeg has the subtitle filters:
   ```
   ffmpeg -hide_banner -filters | grep -E " (subtitles|ass) "   # must print two lines
   ```
2. Make the first commit and put the repo on GitHub (step 5 in the README): move `claude-setup/` into `.claude/`, then `git init -b main`, `git add -A`, `git commit`, and `gh repo create clipper --public --source=. --remote=origin --push`, which also sets the upstream branch.
3. Get an API key at console.anthropic.com. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`; `.env` is already gitignored. API usage is **billed to your API account, separately from your Claude subscription**. Set a monthly spend limit in the console. Don't `export` the key in your shell: if `ANTHROPIC_API_KEY` is set when you start `claude`, Claude Code may bill your API account instead of your subscription.
4. Run `claude` in the repo and sign in with your Claude account when asked. Type `/agents` and confirm reviewer, media-qa and eval-analyst are listed.

### The loop for every phase

1. Run `/clear` so the phase starts fresh. CLAUDE.md and `docs/plan.md` carry everything that matters.
2. Press **Shift+Tab** until the mode shows **plan**, then paste the phase prompt.
3. Read Claude's plan, push back on anything that breaks the architecture, then approve.
4. Let it build. It runs tests itself because `uv run` is pre-approved.
5. Have Claude write the devlog entry for the phase, so the reviewer can check it too.
6. Gate: *"Use the reviewer agent to review phase N against docs/plan.md."* Add media-qa from phase 6 and eval-analyst in phases 4, 8 and 9 (see the table). Fix and re-review until **SIGN-OFF**.
7. Have Claude commit; then you run `git push` yourself in a second Terminal window, and wait for CI with `sleep 10 && gh run watch --exit-status` before starting the next phase. If it fails, paste `gh run view --log-failed` into Claude.

### The build phases

| Phase | Paste this prompt (plan mode) | Done when |
| --- | --- | --- |
| 1a. Project | "Phase 1a of docs/plan.md: pyproject (Python 3.12 pin, dependencies per the Tech stack table), the Typer CLI with setup/run/eval stubs, python-dotenv loading in cli.py, config.toml with every key listed in the plan, pytest with a `slow` marker and `addopts = \"-m 'not slow'\"`, ruff, mypy strict with the listed overrides, and .github/workflows/ci.yml using astral-sh/setup-uv, `uv sync --locked`, apt ffmpeg, then pytest, ruff and mypy." | `uv run clipper --help` works; pytest, ruff, mypy green locally; the workflow passes `uv run --with check-jsonschema check-jsonschema --builtin-schema vendor.github-workflows .github/workflows/ci.yml`; after push, CI is green |
| 1b. Contracts + fixture | "Phase 1b: models.py with every contract in the plan (including LabelSet), cache.py with .done hashing, and tests/fixtures/make_fixtures.py (macOS only) that makes a 150-second, 480x270, low-bitrate test video with ffmpeg and speech from macOS `say` (several distinct topics), saves the spoken text next to it, and keeps it under 2 MB so we commit it for CI." | Model and cache tests pass; fixture committed and under 2 MB; CI green |
| 2. Ingest + transcribe | "Phase 2: ingest (ffprobe meta, 16 kHz mono WAV, fail fast if ffmpeg has no `subtitles` filter) and transcription behind a Transcriber interface. mlx-whisper only on macOS arm64 via the platform marker and imported lazily; faster-whisper everywhere. Time both with the same model size on a 10-minute recording, record the numbers in ADR 0002, make the faster one the Mac default. Commit a canned transcript.json of the fixture so CI tests never run Whisper." | Fixture word error rate ≤ 5% after lowercasing and stripping punctuation (slow test); every word has end ≥ start and starts never go backwards; ADR 0002 has timings |
| 3. Candidates + signals | "Phase 3: sentence splitting; candidate windows that start at a sentence boundary at most every 15 s, and for each start the sentence ends nearest 30 s and 45 s (within 20–60 s), capped by `candidates_per_hour_max`; cut padding per success criterion 4 (`clip_min_s`/`clip_max_s` bound the padded clip: windows are at most `clip_max_s − 0.45` s and at least `clip_min_s` s); audio and text features per candidate." | Every candidate starts and ends on a sentence; count cap holds; features tested on the fixture |
| Before phase 4 (you) | Label 2 of your own videos **before** seeing any model output: watch each, note 5–10 moments you'd clip, with start/end seconds from QuickTime, saved as `eval/labels/<name>.json` in the LabelSet format. Mark one of them `heldout: true`. | Claude commits `eval/labels/`; you push |
| 4. Score | "Phase 4: the scoring stage. Rubric in clipper/prompts/score_v1.md asking for the four 0–5 scores, a one-line reason and a hook title ≤ 40 chars; batches of `batch_size`; JSON validated by the Score model; one retry on invalid JSON; cache by hash of prompt version + model + text; token and cost logging using the price in config.toml. Current models reject `temperature`, so send no sampling parameters and rely on the cache for repeatability. Tests use a mocked client with recorded responses. Run scoring with both claude-sonnet-5-5 and claude-opus-5-5 on the labeled videos; keep Opus only if it beats Sonnet on precision@5 by at least 0.1, otherwise use Sonnet so criterion 12 ($0.50/hour) holds. Record the comparison in ADR 0003. Choose using the tuning (non-held-out) video only; report held-out numbers but don't use them to choose. precision@5 is computed by eval-analyst with the phase 8 matching rule (overlap ≥ 50% of the shorter span, each label matched at most once, greedy by rank); with one tuning video it moves in steps of 0.2, so 0.1 means at least one more matched pick. Run both models at the same `scoring_effort` (a new config.toml key) and record it. If Opus is kept, either tune it under $0.50/hour or raise the criterion 12 target, with the reason in ADR 0003." | Offline tests pass; each live run logs its cost; eval-analyst compares ranked scores to your labels; Sonnet vs Opus precision@5 and cost compared and the model chosen by the 0.1 rule; ADR 0003 written |
| 5. Select | "Phase 5: final score = weighted sum (weights in config.toml); no overlaps over 2 s; spread = no two picks start within max(60 s, duration / (2K)) of each other, relaxed if fewer than K remain; top K." | Selector tests for overlap, length, spread and ordering pass |
| 6. Reframe | "Phase 6: `clipper setup` downloads the MediaPipe face detector model to models/ (pinned URL + SHA-256). Face detection with the MediaPipe ≥ 1.0 Tasks API (vision.FaceDetector, VIDEO mode) at 5 fps, a smoothed crop path for 9:16, center-crop fallback when there's no face, and a --debug-crops flag that writes a preview video with the crop box drawn." | Framing ≥ 90% on a talking-head recording; media-qa checks framing on the debug preview only (no clips exist yet). Note: the short-range model may miss small faces in wide shots, so measure it |
| 7. Captions + render | "Phase 7: word-by-word ASS captions with the current word highlighted, escaping `{`, `}`, `\\` and newlines; the hook title for the first 3 s. Render without OpenCV seeking: decode with `ffmpeg -ss S -t D -i src -vf fps=30 -f rawvideo -pix_fmt bgr24 -`, crop each numpy frame, and write exactly N = round(D*30) frames to a second ffmpeg that takes the raw frames plus the source audio (`-ss S -t N/30`), applies `scale=1080:1920,subtitles=filename='<escaped .ass path>',format=yuv420p`, and encodes libx264 + aac 48 kHz with `-movflags +faststart -t N/30`. Pass all arguments as lists. Stop the decoder after N frames." | Format, sync and caption criteria pass; media-qa PASS; you watch the 5 clips; ADR 0004 (render approach) written |
| 8. Report + eval | "Phase 8: report.json and a self-contained report.html, then `clipper eval --videos <dir>` that hashes the video files in `<dir>`, matches them to each label's `video_sha256`, errors listing any unmatched labels, runs stages 1–6 with K=10 (no render) on each, and computes: a pick matches a label when their overlap is ≥ 50% of the shorter of the two; each label matches at most one pick (greedy by rank); precision@5 = matched picks in the top 5 / 5, averaged over videos; recall@10 = labels matched by the top 10 / labels. Report the tuning and held-out sets separately." | Report opens offline; eval runs on the 2 labeled videos; ADR 0005 written |
| Before phase 9 (you) | Label 3 more videos the same blind way, marking 1 more `heldout: true` (5 labeled, 2 held out). | Claude commits `eval/labels/`; you push |
| 9. Tune + ship | "Phase 9: I've labeled 5 videos total (2 held out). Run eval, tune weights, window settings and the prompt (score_v2 if needed) on the tuning set only, logging every run; then write the README with a demo GIF (≤ 5 MB), the final devlog and any missing ADRs." | All 12 success criteria pass (criterion 9 on held-out videos); eval-analyst report saved; README and GIF published |

**Videos to test with.** Use your own recordings (for example 10–30 minutes of you talking about vintage or points, plus one 60-minute session), or sources whose owners explicitly allow clipping. TED talks are CC BY-NC-ND: fine for private local testing, never for posting or for paid clipping campaigns. Remember that a public README GIF of you is public.

## Are agents worth it here?

**Yes, for checking the work, not for writing it.** One main Claude Code session builds everything, and three narrow subagents check it. Each subagent starts with a fresh context and sees only the repo, not the conversation that wrote the code, which is what makes the review honest.

| Use agents for | Why | Don't use agents for | Why not |
| --- | --- | --- | --- |
| Reviewing each phase | Fresh eyes catch what the author's context hides | Splitting coding across parallel agents | Stages share contracts that change early; parallel writers conflict |
| Checking output videos | Long ffprobe output and frame dumps stay out of the main context | The scoring step inside the product | One structured API call is cheaper and repeatable (ADR 0003) |
| Analyzing eval runs | Numbers-heavy work with a fixed method | Planning phases | Plan mode in the main session does this |

| Agent | Role | Tools | Model | Runs in |
| --- | --- | --- | --- | --- |
| `reviewer` | Manager: adversarial review and sign-off gate | Read, Grep, Glob, Bash (Edit and Write disallowed) | `opus` | Every phase |
| `media-qa` | Checks clips against format, sync, framing and caption criteria | Read, Grep, Glob, Bash (Edit and Write disallowed) | `sonnet` | Phase 6 (framing only), 7–9 |
| `eval-analyst` | Runs the eval and explains what drives scores | Read, Grep, Glob, Bash, Write | `sonnet` | Phases 4, 8, 9 |

None of them edits code: they report, the main session fixes. Agents put scratch files under `work/` (gitignored), which avoids permission prompts for paths outside the project. "Writes only in eval/runs/" is enforced by the eval-analyst's instructions, not by Claude Code. Optional: for the phase 2 timing test, run two sessions at once with `claude --worktree mlx` and `claude --worktree faster`.

The full agent definitions are in `.claude/agents/`.

## Risks, rules and costs

| Risk | What could happen | Mitigation |
| --- | --- | --- |
| Copyright | Takedowns or strikes | Own recordings or sources that allow clipping; rule in CLAUDE.md |
| Campaign rules | Clips rejected as low-effort or auto-generated | Read each campaign's terms; a human picks and polishes |
| Platform automation (v2) | Accounts throttled or banned | Official APIs only, posting after approval, normal volume |
| API cost | Surprise bill | Console spend limit; candidate cap; cost logged per run; cache makes reruns free |
| A/V drift in render | Captions and lips out of sync on 29.97 fps or VFR sources | ffmpeg-decode-at-30-fps render path (Phase 7); A/V duration check |
| Library traps | Claude writes old MediaPipe code; two OpenCV packages conflict; ffmpeg without libass | Rules in CLAUDE.md; reviewer checks for them; ingest fails fast |
| Permissions gaps | `uv run` can run any Python, which could read `.env`; `Bash(rm -rf *)` doesn't catch `rm -fr` | Keep the deny rules as a seatbelt, not a guarantee; review diffs before committing |
| Overfitting the eval | Great on your videos, mediocre elsewhere | Held-out videos; small changes = noise; add labels over time |
| Scope creep | Never shipping | Out-of-scope list waits for v2 |

**Cost estimate.** A 60-minute video is roughly 9,000 spoken words. With the candidate cap (300 per hour) and batches of ~20, scoring is roughly 60,000 input and 18,000 output tokens per hour of video. At Sonnet 5.5's $2 / $10 per million tokens that's about $0.30, inside criterion 12; at Opus 5.5's $4 / $20 it's about $0.60, over it, before counting thinking tokens (which bill as output). Phase 4 picks between them with the 0.1 precision@5 rule. Check current prices at anthropic.com/pricing before changing `scoring_model`. Transcription, face tracking and rendering run locally for free.

## Decision records and v2

| ADR | Decision | Written in |
| --- | --- | --- |
| 0001 | Local-first Python pipeline of file-based stages; no server in v1 | Phase 1a |
| 0002 | Transcription engine, decided by measured timings | Phase 2 |
| 0003 | Moment scoring is one structured API call per batch, not an agent; scoring model choice (Sonnet vs Opus) | Phase 4 |
| 0004 | Render path: ffmpeg decode → numpy crop → ffmpeg encode, for exact frame counts and A/V sync | Phase 7 |
| 0005 | Eval method: precision@5 against blind hand labels, with held-out videos | Phase 8 |

**v2, only after v1 ships:**
1. Review dashboard (FastAPI + small frontend) to approve, trim or reject clips
2. Downloading with `yt-dlp`, and Twitch chat-spike signals
3. Posting through official APIs: YouTube Data API first, then TikTok Content Posting API and Instagram Graph API
4. Views feedback loop: pull view counts back and learn which features predict views
5. Pointing it at your own resale or brand content
