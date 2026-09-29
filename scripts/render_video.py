#!/usr/bin/env python3
"""Render a labeled, edited terminal replay from saved real helper/pytest evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080
BG = "#0b1117"
PANEL = "#141e28"
LINE = "#2d404e"
TEXT = "#eef4f7"
MUTED = "#a5b8c8"
MINT = "#79edbd"
AMBER = "#ffd382"
RED = "#ff9696"
DURATIONS = [3, 5, 6, 3, 3]
CAPTIONS = [
    (0, 3, "Your test is green. Put the bug back."),
    (3, 8, "Free shipping starts at 100. The weak test at 150 missed the bug."),
    (8, 14, "Switch to the boundary test at 100. This one catches it."),
    (14, 17, "Same test, with and without the fix. Two separate comparisons."),
    (17, 20, "prove-fix. A regression-checking skill. github.com/grishahq/prove-fix"),
]


def find_font(provided):
    candidates = [provided] if provided else [
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return str(Path(path).resolve())
    raise RuntimeError("No monospace font found; pass --font /path/to/installed-font.ttf. No font is bundled.")


class Canvas:
    def __init__(self, font):
        self.image = Image.new("RGB", (W, H), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.font = font
        self.boxes = []

    def text(self, xy, value, size=44, color=TEXT):
        font = ImageFont.truetype(self.font, size)
        bounds = self.draw.textbbox(xy, value, font=font)
        if bounds[0] < 60 or bounds[1] < 0 or bounds[2] > W - 60 or bounds[3] > H - 20:
            raise ValueError(f"Text clips frame at {bounds}: {value}")
        self.draw.text(xy, value, font=font, fill=color)
        self.boxes.append({"text": value, "size": size, "bounds": bounds})

    def common(self, step):
        self.text((110, 68), "prove-fix", 35, MINT)
        self.text((570, 76), "EDUCATIONAL DEMO / EDITED CLI REPLAY", 26, MUTED)
        self.text((1750, 68), step, 30, MUTED)
        self.draw.line((110, 132, 1810, 132), fill=LINE, width=2)
        self.text((110, 1000), "Real captured results. Tests unchanged within each comparison.", 26, MUTED)

    def terminal(self):
        self.draw.rounded_rectangle((110, 295, 1810, 810), radius=22, fill=PANEL, outline=LINE, width=2)
        for i, color in enumerate((RED, AMBER, MINT)):
            x = 148 + 30 * i
            self.draw.ellipse((x, 321, x + 12, 333), fill=color)
        self.text((260, 312), "prove-fix / captured helper + pytest output", 25, MUTED)
        self.draw.line((140, 363, 1780, 363), fill=LINE, width=2)


def load_evidence(directory):
    summary = json.loads((directory / "summary.json").read_text())
    results = {}
    for item in summary["comparisons"]:
        report_path = directory / item["report"]
        if hashlib.sha256(report_path.read_bytes()).hexdigest() != item["report_sha256"]:
            raise ValueError("Saved evidence hash mismatch.")
        report = json.loads(report_path.read_text())
        if not report["snapshots"]["non_selected_identical"]:
            raise ValueError("Snapshot invariant was not verified.")
        statuses = []
        for side in ("fixed", "reversed"):
            observations = []
            for pair in report["runs"]:
                run = pair[side]
                evidence = run["evidence"]
                call = next(e for e in evidence["events"] if e["phase"] == "call")
                if call.get("xfail") or call["outcome"] not in {"passed", "failed"}:
                    raise ValueError("Video requires actual executed pass/fail evidence.")
                observations.append("PASS" if call["outcome"] == "passed" else "FAIL")
            if len(set(observations)) != 1:
                raise ValueError("Video cannot summarize inconsistent reruns.")
            statuses.append(observations[0])
        results[item["name"]] = {"report": report, "statuses": statuses, "amount": item["amount"]}
    boundary = results["boundary"]["report"]
    reversed_ = boundary["runs"][0]["reversed"]
    call = reversed_["evidence"]["events"][1]
    assertion = boundary["interpretation"]["expected_assertion"]
    if (assertion not in call["assertions"] or call["exception"] != "AssertionError"
            or assertion != call["assertion_origin"]):
        raise ValueError("Expected assertion evidence is absent.")
    raw = (directory / "boundary" / reversed_["stdout"]).read_text().splitlines()
    excerpt = [line for line in raw if line.startswith("E   ") or line.startswith("E    ")]
    if len(excerpt) < 2:
        raise ValueError("Actual pytest assertion excerpt is absent.")
    results["assertion"] = assertion
    results["excerpt"] = excerpt[:2]
    return results, summary


def scenes(font, evidence):
    rendered = []
    c = Canvas(font)
    c.common("1/5")
    c.text((110, 240), "A green test is a starting point.", 40, MUTED)
    c.text((110, 365), "Your test is green.", 91)
    c.text((110, 500), "Put the bug back.", 100, MINT)
    c.text((110, 725), "Reverse only the fix. Run the same test.", 43, MUTED)
    rendered.append(c)

    c = Canvas(font)
    c.common("2/5")
    c.text((110, 160), "01 / WEAK TEST", 28, AMBER)
    c.text((110, 211), "Free shipping starts at 100.", 58)
    c.terminal()
    weak = evidence["weak"]
    weak_assert = weak["report"]["interpretation"]["expected_assertion"]["source"]
    c.text((150, 400), weak_assert, 46)
    c.text((150, 510), "With fix     " + weak["statuses"][0], 52, MINT)
    c.text((150, 585), "Without fix  " + weak["statuses"][1], 52, MINT)
    c.text((150, 698), "prove-fix | " + weak["report"]["classification"], 46, AMBER)
    c.text((110, 872), "This test missed the bug.", 58, AMBER)
    rendered.append(c)

    c = Canvas(font)
    c.common("3/5")
    c.text((110, 160), "02 / SWITCH TO BOUNDARY TEST", 28, MINT)
    c.text((110, 211), "Now test the boundary: 100.", 58)
    c.terminal()
    boundary = evidence["boundary"]
    c.text((150, 391), evidence["assertion"]["source"], 46)
    c.text((150, 475), "With fix  " + boundary["statuses"][0], 43, MINT)
    c.text((850, 475), "Without fix  " + boundary["statuses"][1], 43, RED)
    c.text((150, 548), evidence["excerpt"][0], 42, RED)
    c.text((150, 608), evidence["excerpt"][1], 42, RED)
    c.text((150, 710), "prove-fix | " + boundary["report"]["classification"], 46, MINT)
    c.text((110, 872), "This one catches it.", 58, MINT)
    rendered.append(c)

    c = Canvas(font)
    c.common("4/5")
    c.text((110, 195), "Same test. With and without the fix.", 61)
    c.text((110, 286), "Two separate comparisons. Only >= becomes >.", 34, MUTED)
    c.draw.rounded_rectangle((110, 391, 1810, 775), radius=22, fill=PANEL, outline=LINE, width=2)
    xs = [160, 680, 1030, 1390]
    for x, label in zip(xs, ["TEST", "WITH FIX", "WITHOUT FIX", "RESULT"]):
        c.text((x, 432), label, 32, MUTED)
    c.draw.line((150, 502, 1760, 502), fill=LINE, width=2)
    for y, name in ((545, "weak"), (659, "boundary")):
        result = evidence[name]
        color = AMBER if name == "weak" else MINT
        c.text((xs[0], y), f"{name} / {result['amount']}", 37)
        c.text((xs[1], y), result["statuses"][0], 41, MINT)
        c.text((xs[2], y), result["statuses"][1], 41, MINT if result["statuses"][1] == "PASS" else RED)
        c.text((xs[3], y + 4), result["report"]["classification"], 34, color)
    c.text((110, 876), "Evidence for this regression. No correctness guarantee.", 39, MUTED)
    rendered.append(c)

    c = Canvas(font)
    c.common("5/5")
    c.text((110, 260), "prove-fix", 115, MINT)
    c.text((110, 435), "A regression-checking skill", 63)
    c.text((110, 565), "github.com/grishahq/prove-fix", 53)
    c.text((110, 733), "v0.1 / Python + pytest / explicit implementation patch", 32, MUTED)
    c.text((110, 815), "Claude Code + Codex installation adapters", 33, MUTED)
    rendered.append(c)
    return rendered


def timestamp(value):
    return f"00:00:{value:02d},000"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, default=ROOT / "media/evidence/demo")
    p.add_argument("--out", type=Path, default=ROOT / "media")
    p.add_argument("--font", help="Installed monospace .ttf/.ttc; never copied into the repository")
    args = p.parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("Install local FFmpeg/ffprobe before rendering.")
    font = find_font(args.font)
    evidence, summary = load_evidence(args.evidence.resolve())
    cards = scenes(font, evidence)
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="prove-fix-render-") as temp:
        frames = Path(temp)
        for i, card in enumerate(cards):
            card.image.save(frames / f"scene-{i}.png")
        concat = frames / "timeline.txt"
        concat.write_text("".join(f"file 'scene-{i}.png'\nduration {seconds}\n" for i, seconds in enumerate(DURATIONS))
                          + "file 'scene-4.png'\n")
        output = args.out / "prove-fix-demo.mp4"
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                   "-i", str(concat), "-t", "20", "-r", "30", "-c:v", "libx264", "-preset", "medium",
                   "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
        subprocess.run(command, check=True)
    cards[3].image.save(args.out / "poster.png")
    (args.out / "captions.srt").write_text("\n".join(f"{i}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n"
                                          for i, (start, end, text) in enumerate(CAPTIONS, 1)), encoding="utf-8")
    probe_cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]
    probe = json.loads(subprocess.check_output(probe_cmd))
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    duration = float(probe["format"]["duration"])
    if not (15 <= duration <= 25 and stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p"
            and stream["width"] == W and stream["height"] == H and stream["r_frame_rate"] == "30/1"):
        raise RuntimeError("Rendered video violates the requested duration/encoding constraints.")
    # Top-level MP4 atoms: fast-start requires moov before mdat.
    data = output.read_bytes()
    offset, atoms = 0, []
    while offset + 8 <= len(data):
        size = int.from_bytes(data[offset:offset + 4], "big")
        atoms.append(data[offset + 4:offset + 8].decode("ascii"))
        if size < 8:
            raise RuntimeError("Unexpected MP4 atom size.")
        offset += size
    if atoms.index("moov") > atoms.index("mdat"):
        raise RuntimeError("MP4 metadata is not fast-start.")
    qa = args.out / "frames"
    qa.mkdir(exist_ok=True)
    for moment in (0.1, 2.9, 3.1, 7.9, 8.1, 13.9, 14.1, 16.9, 17.1, 19.9):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(moment),
            "-i", str(output), "-frames:v", "1", str(qa / f"{moment:04.1f}.png")], check=True)
    record = {"duration_seconds": duration, "codec": stream["codec_name"], "pixel_format": stream["pix_fmt"],
        "width": W, "height": H, "fps": stream["r_frame_rate"], "fast_start_atoms": atoms,
        "video_bytes": output.stat().st_size, "video_sha256": hashlib.sha256(data).hexdigest(),
        "source": "Explicitly labeled edited replay of real saved helper/pytest output; no fabricated agent session.",
        "source_reports": summary["comparisons"], "font": Path(font).name,
        "text_layout": [c.boxes for c in cards],
        "encoding_command": [part.replace(str(frames), "<render-work>").replace(str(args.out), "<media>")
                             for part in command],
        "frame_checks": [p.name for p in sorted(qa.glob("*.png"))]}
    (args.out / "render-validation.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Rendered {output}: {duration:.3f}s, {W}x{H}, 30 fps, H.264/yuv420p, fast-start; {output.stat().st_size} bytes")
    print(f"Inspect extracted frames in {qa}.")


if __name__ == "__main__":
    main()
