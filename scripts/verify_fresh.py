#!/usr/bin/env python3
"""Verify README runtime/install/demo commands from a disposable committed clone."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "https://github.com/grishahq/prove-fix.git"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--remote", action="store_true", help="Clone the published remote rather than the local committed repo")
    p.add_argument("--out", type=Path, required=True, help="New directory for sanitized validation records")
    args = p.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise ValueError("Output already exists; choose a new directory.")
    out.mkdir(parents=True)
    steps = []
    with tempfile.TemporaryDirectory(prefix="prove-fix-fresh-") as temp:
        work = Path(temp).resolve()
        clone = work / "prove-fix"
        source = REMOTE if args.remote else str(ROOT)
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", source, str(clone)], check=True)
        revision = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"], text=True).strip()
        commands = [
            ["python3", "-m", "venv", ".venv"],
            [".venv/bin/python", "-m", "pip", "install", "-r", "requirements-dev.txt"],
            [".venv/bin/python", "scripts/demo.py", "--out", "artifacts/demo"],
            [".venv/bin/python", "-m", "pytest", "-q"],
        ]
        for agent in ("claude", "codex"):
            commands += [["python3", "scripts/install.py", "--agent", agent, "--project", ".", "--dry-run"],
                         ["python3", "scripts/install.py", "--agent", agent, "--project", "."],
                         ["python3", "scripts/install.py", "--agent", agent, "--user", "--home", str(work / "test-home"), "--dry-run"],
                         ["python3", "scripts/install.py", "--agent", agent, "--user", "--home", str(work / "test-home")]]
        for i, command in enumerate(commands):
            start = time.monotonic()
            result = subprocess.run(command, cwd=clone, text=True, capture_output=True)
            clean = lambda s: s.replace(str(work), "<fresh-work>").replace(str(ROOT), "<source-repo>")
            stdout, stderr = f"step-{i + 1}.stdout.txt", f"step-{i + 1}.stderr.txt"
            (out / stdout).write_text(clean(result.stdout))
            (out / stderr).write_text(clean(result.stderr))
            steps.append({"command": [clean(part) for part in command], "cwd": "<fresh-work>/prove-fix",
                          "exit_code": result.returncode, "duration_seconds": round(time.monotonic() - start, 3),
                          "stdout": stdout, "stderr": stderr})
            print(" ".join(command) + f" -> exit {result.returncode}", flush=True)
            if result.returncode:
                (out / "report.json").write_text(json.dumps({"revision": revision, "steps": steps, "passed": False}, indent=2))
                print(result.stdout + result.stderr)
                return 1
        report = {"source": REMOTE if args.remote else "<local committed repo>", "revision": revision,
                  "steps": steps, "passed": True,
                  "scope": "README runtime/demo/tests and both install scopes in temporary directories; global settings untouched."}
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
