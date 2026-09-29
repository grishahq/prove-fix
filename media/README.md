# Launch media

- [prove-fix-demo.mp4](prove-fix-demo.mp4): actual 20.000-second H.264 MP4,
  1920×1080, 30 fps, yuv420p, fast-start metadata, no audio. Approximately 393 KiB.
- [poster.png](poster.png): 1920×1080 comparison still.
- [captions.srt](captions.srt): English timed captions; all essential text is also visible in the video.
- [render-validation.json](render-validation.json): measured encoding/duration,
  MP4 atom order, source report hashes, layout bounds, and video hash.
- [Saved educational demo evidence](evidence/demo/summary.json): both actual comparisons,
  two runs per side, sanitized JSON, commands, CLI output and raw pytest stdout/stderr.

## What the video shows

**An explicitly labeled, edited CLI replay of real captured helper output.** It
is not a screen recording of a fabricated agent conversation. Five deliberate
holds: hook (0–3s), weak test (3–8s), an explicitly labeled switch to the boundary
test and its real assertion excerpt (8–14s), comparison (14–17s), project/link
(17–20s). Tests are unchanged within each of the two comparisons.

PASS/FAIL and classification labels are derived from saved structured executions;
the renderer refuses hash mismatches, skipped tests, or inconsistent reruns.
The displayed failure excerpt is read from captured pytest stdout. No planted
weak test is represented as an authentic Claude/Codex mistake. No loading wait
or agent slash command is fabricated. Agent names on the closing card describe
installation adapters. Live agent verification is recorded separately in
[validation notes](../docs/validation.md).

Timing is edited for legibility and does not claim checks always take 20 seconds.
Source fixture and forward fix patch are in `../demo/`. The evidence paths replace
machine-specific roots/interpreters with `<demo-repo>`, `<demo-work>`,
`<snapshot-root>`, `<python>`, and `<skill-scripts>`. File/test/patch hashes and
observed outcomes remain unchanged. Sanitization removes paths, not failure text.
Private project logs and authentication records are not distributed.

## Reproduce

Prepare the runtime/demo environment using the root README. Then create fresh
capture evidence and install separate rendering dependencies:

```bash
.venv/bin/python scripts/demo.py --out artifacts/video-evidence
python3 -m venv .venv-media
.venv-media/bin/python -m pip install -r requirements-media.txt
.venv-media/bin/python scripts/render_video.py --evidence artifacts/video-evidence --out artifacts/rendered-media
ffprobe -v error -show_streams -show_format -of json artifacts/rendered-media/prove-fix-demo.mp4
```

FFmpeg with `libx264` and ffprobe must already be available locally. Pillow is
required only for media generation. The checker/demo does not require it. The
renderer uses a local Menlo, DejaVu Sans Mono, or Liberation Mono font; alternatively
pass `--font /absolute/path/to/installed-monospace-font.ttf`. No font binary is shipped.
Different fonts or encoder versions may change pixels/bytes, while results and
timing remain based on the same evidence.

To refresh checked-in media, use a new capture directory, inspect its reports,
then render with `--out media`. That explicitly replaces generated media files.
Copy the reviewed evidence into `media/evidence/demo` and rerender against that
path before committing so `source_reports` matches retained evidence. Do not
replace retained evidence with logs from private projects.

The script checks duration 15–25s, H.264, yuv420p, dimensions, frame rate, fast-start
atom order, source hashes, and text bounds. It extracts frames at 0.1, 2.9, 3.1,
7.9, 8.1, 13.9, 14.1, 16.9, 17.1, and 19.9 seconds under the output's `frames/`.
Visually inspect those images for transitions, clipped text, blank frames, and
incorrect results. Generated intermediates/QA frames are ignored in Git.

The delivered frames were inspected at the beginning, each transition, and ending.
The English captions and poster work without audio and use written statuses as
well as color. Launch posts are prepared in `../launch/`; nothing is posted by these scripts.
