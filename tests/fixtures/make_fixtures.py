"""Make tests/fixtures/talk.mp4 + talk.txt: a 150 s, 480x270 talk with several topics.

macOS only (speech comes from `say`). Run from the repo root:
    uv run python tests/fixtures/make_fixtures.py
The output is committed so CI never needs `say`. Keep it under 2 MB.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from clipper.config import load_config  # noqa: E402

FIXTURES = Path(__file__).resolve().parent
VIDEO = FIXTURES / "talk.mp4"
TEXT = FIXTURES / "talk.txt"

DURATION_S = 150.0
WIDTH, HEIGHT, FPS = 480, 270, 30
VOICE, RATE_WPM = "Samantha", 175
GAP_S = 0.8
MAX_BYTES = 2_000_000

# (background color, paragraph). Distinct topics so later phases can find topic changes.
TOPICS: list[tuple[str, str]] = [
    (
        "0x6b4226",
        "Let's talk about sourdough bread. A starter is just flour and water that wild yeast "
        "has moved into. You feed it every day, and after about a week it doubles in size. "
        "Why does the bread taste sour? Bacteria in the starter make lactic acid. "
        "The longer the dough rests in the fridge, the more sour it gets.",
    ),
    (
        "0x1f3a5f",
        "Now for something different: vintage watches. A mechanical watch has no battery. "
        "A coiled spring stores energy, and a balance wheel ticks it out a little at a time. "
        "Collectors care about original dials more than almost anything else. "
        "A watch that was polished too hard can lose half its value overnight!",
    ),
    (
        "0x2e5e3e",
        "Here is a quick tip about credit card points. Points are worth the most when you "
        "transfer them to an airline partner. One hundred thousand points might buy a gift card "
        "worth one thousand dollars. The same points can book a business class seat worth five "
        "times as much. Always check the transfer ratio first.",
    ),
    (
        "0x5e2e4e",
        "Training for a marathon takes about four months. Most of your runs should feel easy. "
        "You should be able to hold a conversation while you run. Once a week, add one long run "
        "and build it up slowly. Is it really that simple? Mostly, yes. "
        "Sleep and patience matter more than fancy shoes.",
    ),
    (
        "0x4e4e1f",
        "Houseplants die from too much water far more often than too little. "
        "Before you water, push a finger into the soil. If it is still damp, wait. "
        "Most plants also want more light than you think. A snake plant will survive a dark "
        "corner, but a fiddle leaf fig will drop its leaves in protest.",
    ),
    (
        "0x3f2a1a",
        "Let me share a secret about coffee at home. The grinder matters more than the machine. "
        "Beans start to go stale about two weeks after roasting, so check the roast date on the "
        "bag. Use water just off the boil, not boiling. And weigh your coffee! A cheap kitchen "
        "scale will improve your cup more than any gadget you can buy.",
    ),
    (
        "0x1a3f3f",
        "Next, a bike repair that everyone should know. Most flat tires come from a tiny thorn "
        "or a sliver of glass still stuck in the tire. Before you put in a new tube, run your "
        "fingers slowly around the inside of the tire. Did you find something sharp? Pull it "
        "out, or the new tube will go flat in ten minutes.",
    ),
    (
        "0x202030",
        "Finally, a fact about space. A day on Venus is longer than its year! "
        "Venus spins so slowly that it goes around the sun before it turns around once. "
        "It also spins backwards, so the sun rises in the west. "
        "That is all for today. Thanks for listening.",
    ),
]


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def _probe_duration(path: Path) -> float:
    # ffprobe ships next to ffmpeg; config.toml only names ffmpeg_bin.
    out = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]
    )
    return float(json.loads(out)["format"]["duration"])


def main() -> int:
    if sys.platform != "darwin":
        print("make_fixtures.py needs macOS (it uses `say`).", file=sys.stderr)
        return 1
    ffmpeg = load_config(REPO_ROOT / "config.toml").ffmpeg_bin
    for tool in ("say", ffmpeg, "ffprobe"):
        if shutil.which(tool) is None:
            print(f"`{tool}` not found on PATH.", file=sys.stderr)
            return 1

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        segments: list[tuple[str, float]] = []
        for i, (color, text) in enumerate(TOPICS):
            aiff = tmp / f"{i:02d}.aiff"
            _run(["say", "-v", VOICE, "-r", str(RATE_WPM), "-o", str(aiff), text])
            segments.append((color, _probe_duration(aiff)))

        speech_s = sum(d for _, d in segments) + GAP_S * (len(segments) - 1)
        for i, (_, d) in enumerate(segments):
            print(f"topic {i + 1}: {d:.2f} s speech")
        print(f"speech + gaps: {speech_s:.2f} s of {DURATION_S:.0f} s")
        if speech_s > DURATION_S:
            print("Speech is longer than the fixture; shorten TOPICS.", file=sys.stderr)
            return 1

        # Each topic gets its own background color for its speech plus the gap after it;
        # the last color runs to the end.
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        for i in range(len(TOPICS)):
            cmd += ["-i", str(tmp / f"{i:02d}.aiff")]
        n = len(TOPICS)
        filters = []
        audio_parts = []
        video_parts = []
        for i, (color, d) in enumerate(segments):
            last = i == n - 1
            video_d = (
                DURATION_S - sum(s for _, s in segments[:i]) - GAP_S * i if last else d + GAP_S
            )
            # Mono 22.05 kHz like `say`'s output; pad every topic but the last with a gap.
            pad = "" if last else f",apad=pad_dur={GAP_S}"
            filters.append(f"[{i}:a]aformat=sample_rates=22050:channel_layouts=mono{pad}[a{i}]")
            filters.append(f"color=c={color}:s={WIDTH}x{HEIGHT}:r={FPS}:d={video_d:.6f}[v{i}]")
            audio_parts.append(f"[a{i}]")
            video_parts.append(f"[v{i}]")
        filters.append(
            f"{''.join(audio_parts)}concat=n={n}:v=0:a=1,apad,atrim=0:{DURATION_S}[aout]"
        )
        # A white square slides across so the picture isn't static (overlay, unlike drawbox,
        # re-evaluates x on every frame).
        filters.append(f"color=c=white:s=40x40:r={FPS}[box]")
        filters.append(
            f"{''.join(video_parts)}concat=n={n}:v=1:a=0[bg];"
            f"[bg][box]overlay=x='mod(t*60,{WIDTH - 40})':y={HEIGHT // 2 - 20}:shortest=1,"
            f"trim=0:{DURATION_S},setpts=PTS-STARTPTS[vout]"
        )
        cmd += [
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "30", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-g", str(FPS * 5),
            "-c:a", "aac", "-b:a", "48k", "-ac", "1",
            "-t", str(DURATION_S),
            "-map_metadata", "-1", "-fflags", "+bitexact",
            "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-movflags", "+faststart",
            str(VIDEO),
        ]  # fmt: skip
        _run(cmd)

    TEXT.write_text("\n\n".join(text for _, text in TOPICS) + "\n", encoding="utf-8")
    size = VIDEO.stat().st_size
    words = sum(len(text.split()) for _, text in TOPICS)
    print(f"{VIDEO.name}: {size / 1e6:.2f} MB, {_probe_duration(VIDEO):.2f} s; {words} words")
    if size >= MAX_BYTES:
        print(f"{VIDEO.name} is over 2 MB; lower the bitrate.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
