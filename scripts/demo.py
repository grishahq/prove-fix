#!/usr/bin/env python3
"""Run two explicitly separate educational comparisons using the actual helper."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "skills/prove-fix/scripts/check.py"


def sanitize(value, replacements):
    if isinstance(value, str):
        for source, target in replacements:
            value = value.replace(source, target)
        # Independently generated helper temporary roots in commands and tracebacks.
        value = re.sub(r"(?:/[^\s\"']*)?/prove-fix-[A-Za-z0-9_-]+", "<snapshot-root>", value)
        return value
    if isinstance(value, dict):
        return {k: sanitize(v, replacements) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, replacements) for v in value]
    return value


def capture(out, checker=CHECKER, repeats=2):
    if out.exists():
        raise ValueError("Use a new demo output directory; existing evidence is never overwritten.")
    out.mkdir(parents=True)
    summary = {"label": "Deterministic educational example; edited CLI replay source", "comparisons": []}
    with tempfile.TemporaryDirectory(prefix="prove-fix-demo-") as temp:
        work = Path(temp).resolve()
        repo = work / "fixture"
        repo.mkdir()
        shutil.copyfile(ROOT / "demo/shipping.py", repo / "shipping.py")
        # The implementation is tracked; the new regression test is included explicitly.
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "shipping.py"], check=True)
        shutil.copyfile(ROOT / "demo/test_shipping.py", repo / "test_shipping.py")
        patch = work / "fix.patch"
        shutil.copyfile(ROOT / "demo/fix.patch", patch)
        replacements = [(str(repo), "<demo-repo>"), (str(work), "<demo-work>"),
                        (str(ROOT), "<prove-fix>"), (str(checker.parent), "<skill-scripts>"),
                        (sys.executable, "<python>"), (str(out), "<evidence>")]
        replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
        for name, line, amount in (("weak", 5, 150), ("boundary", 9, 100)):
            print(f"\nEducational comparison: {name} test (amount {amount}); test unchanged within this comparison.", flush=True)
            raw = work / name
            command = [sys.executable, str(checker), "--repo", str(repo), "--patch", str(patch),
                       "--allow", "shipping.py", "--protect", "test_shipping.py", "--include", "test_shipping.py",
                       "--test", f"test_shipping.py::test_{name}", "--expect-assert", f"test_shipping.py:{line}",
                       "--bug-description", "At the free-shipping threshold of 100, > incorrectly rejects eligibility.",
                       "--runs", str(repeats), "--out", str(raw)]
            result = subprocess.run(command, capture_output=True, text=True)
            if not (raw / "report.json").exists():
                raise RuntimeError(result.stderr or result.stdout)
            report = json.loads((raw / "report.json").read_text())
            expected = "NOT_CAUGHT" if name == "weak" else "CAUGHT"
            if report["classification"] != expected:
                raise RuntimeError("Unexpected demo result: " + result.stdout + result.stderr)
            target = out / name
            target.mkdir()
            for file in raw.rglob("*"):
                if file.is_file():
                    dest = target / file.relative_to(raw)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if file.suffix == ".json":
                        content = json.dumps(sanitize(json.loads(file.read_text()), replacements), indent=2) + "\n"
                    else:
                        content = sanitize(file.read_text(), replacements)
                    dest.write_text(content, encoding="utf-8")
            cli = sanitize(result.stdout, replacements)
            (target / "cli.txt").write_text(cli, encoding="utf-8")
            (target / "cli-stderr.txt").write_text(sanitize(result.stderr, replacements), encoding="utf-8")
            (target / "command.json").write_text(json.dumps(sanitize(command, replacements), indent=2) + "\n")
            print(cli, end="", flush=True)
            clean = json.loads((target / "report.json").read_text())
            summary["comparisons"].append({"name": name, "amount": amount, "classification": clean["classification"],
                "helper_exit_code": result.returncode, "report": f"{name}/report.json",
                "report_sha256": hashlib.sha256((target / "report.json").read_bytes()).hexdigest()})
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New directory for sanitized evidence")
    parser.add_argument("--checker", type=Path, default=CHECKER, help="Bundled helper to exercise (e.g. installed skill)")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    try:
        capture(args.out.resolve(), args.checker.resolve(), args.runs)
    except (ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
