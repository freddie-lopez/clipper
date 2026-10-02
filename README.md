# Clipper

Clipper turns a long video into the best short, vertical, captioned clips for TikTok, Reels and Shorts. It transcribes the video, finds the strongest moments, frames the speaker for a phone screen, adds word-by-word captions and explains why it picked each clip.

> **Status: planned, not built yet.** This repo holds the full build plan, the project rules and three review agents. The code gets built phase by phase in [Claude Code](https://claude.com/claude-code), and each phase is reviewed before it's committed. Progress goes in [`docs/devlog/`](docs/devlog/).

## What's in here

The Claude Code files arrive in `claude-setup/` and move into the hidden `.claude/` folder during setup (Part 1, step 5).

| Path | What it is |
| --- | --- |
| [`docs/plan.md`](docs/plan.md) | The build plan: goal, success criteria, architecture, and a ready-to-paste prompt for every phase |
| [`CLAUDE.md`](CLAUDE.md) | Rules Claude Code reads at the start of every session |
| [`.claude/agents/`](.claude/agents/) | Three review agents: `reviewer` (signs off each phase), `media-qa` (checks the output videos), `eval-analyst` (measures pick quality) |
| [`.claude/settings.json`](.claude/settings.json) | Pre-approved safe commands, blocked risky ones, and auto-formatting for Python files |
| `docs/decisions/` | One-page decision records, written as the build goes |
| `docs/devlog/` | A dated log of what was built and what broke |

## How to use it, in easy steps

You need a Mac with Apple Silicon (M1 or newer) and a Claude account.

### Part 1: set up (once, about 45 minutes)

1. **Install Claude Code.** Open Terminal and run:
   ```
   curl -fsSL https://claude.ai/install.sh | bash
   ```
2. **Install the other tools.** If you don't have Homebrew yet, install it from [brew.sh](https://brew.sh), then put it on your PATH:
   ```
   echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
   eval "$(/opt/homebrew/bin/brew shellenv)"
   ```
   Then install the tools. `ffmpeg-full` isn't added to your PATH automatically, so the second line does that:
   ```
   brew install ffmpeg-full uv gh jq
   echo 'export PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH"' >> ~/.zshrc
   ```
3. **Open a new Terminal window**, then check that ffmpeg can burn captions. This should print two lines:
   ```
   ffmpeg -hide_banner -filters | grep -E " (subtitles|ass) "
   ```
4. **Sign in to GitHub** from Terminal:
   ```
   gh auth login
   ```
5. **Make the first commit and put it on your GitHub.** First time only, from the starter folder. Before you start, run `git config --global user.email`. If it prints nothing, or doesn't print the email on your GitHub account, first run `git config --global user.name "Your Name"` and `git config --global user.email "the email on your GitHub account"`. Then this block moves the Claude Code files into the hidden `.claude` folder, makes the first commit with your name, and creates the GitHub repo:
   ```
   cd ~/VSCode/clipper
   mkdir -p .claude/agents
   mv claude-setup/settings.json .claude/ && mv claude-setup/agents/*.md .claude/agents/ && rm -rf claude-setup
   git init -b main
   git add -A
   git commit -m "Starter kit: plan, rules and review agents"
   gh repo create clipper --public --source=. --remote=origin --push
   ```
   If only the last line failed, fix the problem and run just that line again; don't rerun the whole block. (Already on GitHub? Get it on another computer with `gh repo clone <your-username>/clipper` instead.)
6. **Add your API key (optional for now).** The AI scoring step uses the Claude API, which is billed separately from your Claude subscription. Create a key at [console.anthropic.com](https://console.anthropic.com), set a spend limit, then:
   ```
   cp .env.example .env
   ```
   Open `.env` and paste your key after `ANTHROPIC_API_KEY=`. Don't `export` the key in your Terminal.
7. **Start Claude Code** inside the folder:
   ```
   claude
   ```
   Sign in when asked. Type `/agents` and check that `reviewer`, `media-qa` and `eval-analyst` are listed.

### Part 2: build it, one phase at a time

Repeat these steps for each phase in the [build table](docs/plan.md#the-build-phases) (1a, 1b, 2, 3 … 9):

1. Type `/clear` to start the phase fresh.
2. Press **Shift+Tab** until the mode says **plan**.
3. Copy the phase's prompt from `docs/plan.md` and paste it in.
4. Read Claude's plan. If it looks right, approve it and let it build.
5. Ask: *"Write the devlog entry for this phase."*
6. Ask for the review: *"Use the reviewer agent to review phase 1a against docs/plan.md."* (Change the phase number each time.)
7. If the verdict is **CHANGES REQUIRED**, ask Claude to fix the findings, then review again. Repeat until **SIGN-OFF**.
8. Ask: *"Commit this phase."*
9. In a second Terminal window, inside the folder, push and wait for GitHub's checks (you push, not Claude):
   ```
   git push
   sleep 10 && gh run watch --exit-status
   ```
   If the checks fail, run `gh run view --log-failed` and paste the output into Claude. Start the next phase only once they pass.

Two phases need you first: **before phase 4** and **before phase 9** you pick the best moments in a few of your own videos yourself. The plan explains how. That's how the tool's picks get measured fairly. Then ask Claude to commit `eval/labels/`, and push it yourself.

### Part 3: use Clipper (after phase 8 is done; polished after phase 9)

1. Make sure `.env` has your `ANTHROPIC_API_KEY` (Part 1, step 6). The first run also downloads the Whisper model, so it's slower.
2. Download the face-detection model (once):
   ```
   uv run clipper setup
   ```
3. Make clips from any video you have the rights to:
   ```
   uv run clipper run my-video.mp4 --top 5
   ```
4. Open `out/my-video/` to find `clip_01.mp4` … `clip_05.mp4`, and open `report.html` to see why each clip was picked.

## Rules

- Only clip videos you own or have permission to clip.
- Claude Code never pushes to GitHub on its own; you do.
- Every phase needs the reviewer agent's **SIGN-OFF** before it's committed.

## License

MIT. See [LICENSE](LICENSE).
