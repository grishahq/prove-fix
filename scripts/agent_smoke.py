#!/usr/bin/env python3
"""Opt-in authenticated CLI smoke test in an owned educational temporary project.

Never part of CI or the deterministic demo. Uses existing authentication; no tokens
are copied. Public output is a minimal sanitized transcript and helper report.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from demo import ROOT, sanitize
from install import install


def run(agent, out):
    if out.exists():
        raise ValueError("Use a new output directory.")
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="prove-fix-agent-") as temp:
        work = Path(temp).resolve()
        repo = work / "project"
        repo.mkdir()
        fixed = (ROOT / "demo/shipping.py").read_text()
        (repo / "shipping.py").write_text(fixed.replace(">= 100", "> 100"))
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "shipping.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Demo",
                        "-c", "user.email=demo@example.invalid", "commit", "-qm", "educational fixture"], check=True)
        (repo / "shipping.py").write_text(fixed)
        shutil.copyfile(ROOT / "demo/test_shipping.py", repo / "test_shipping.py")
        shutil.copyfile(ROOT / "demo/fix.patch", repo / "fix.patch")
        dest = install(agent, repo)
        evidence = work / "result"
        prompt = (f"{'/prove-fix' if agent == 'claude' else '$prove-fix'} Check the boundary regression test "
                  "in this explicitly educational shipping fixture. Free shipping starts at 100. "
                  "Inspect the current diff and the tests. Use the existing implementation-only forward fix.patch "
                  "without editing any fixture or test. The new test_shipping.py is untracked, so include it explicitly. "
                  f"Use the already prepared interpreter {sys.executable}. Write helper evidence to {evidence}. "
                  "Executing this trusted disposable fixture is authorized. Invoke the bundled helper, inspect its "
                  "structured failure and logs, and report observed outcomes and separate bug attribution with limitations. "
                  "Do not install dependencies, change settings, create commits, or access files outside this fixture "
                  "and its bundled skill/interpreter. Answer in English.")
        version = subprocess.run([agent if agent == "codex" else "claude", "--version"], capture_output=True, text=True).stdout.strip()
        if agent == "codex":
            command = ["codex", "exec", "--ephemeral", "--sandbox", "workspace-write", "--json", "--color", "never",
                       "--cd", str(repo), "--add-dir", str(work), prompt]
        else:
            command = ["claude", "-p", prompt, "--output-format", "json", "--no-session-persistence",
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "project",
                "--tools", "Read,Bash,Glob,Grep,Skill", "--allowedTools", "Read", "Glob", "Grep",
                "Bash(git diff *)", "Bash(git status *)", "Bash(git ls-files *)",
                f"Bash({sys.executable} {dest / 'scripts/check.py'} *)"]
        started = time.monotonic()
        env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        process = subprocess.Popen(command, cwd=repo, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=240)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise
        replacements = [(str(work), "<agent-work>"), (str(repo), "<fixture>"),
                        (str(ROOT), "<prove-fix>"), (sys.executable, "<python>")]
        replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
        # Keep raw local records under ignored artifacts for review; never publish them automatically.
        private = ROOT / "artifacts" / "agent-private"
        private.mkdir(parents=True, exist_ok=True)
        (private / f"{out.name}.stdout.txt").write_text(stdout)
        (private / f"{out.name}.stderr.txt").write_text(stderr)
        public = {"agent": agent, "version": version, "command": sanitize(command, replacements),
                  "duration_seconds": round(time.monotonic() - started, 3), "cli_exit_code": process.returncode,
                  "timed_out": timed_out, "helper_report": None, "final_response": None,
                  "verification": "Attempted real explicit CLI invocation; inspect outcome below."}
        if agent == "codex":
            tool_events = []
            for line in stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    public["final_response"] = sanitize(item.get("text"), replacements)
                if item.get("type") == "command_execution" and "check.py" in item.get("command", ""):
                    tool_events.append(sanitize(item, replacements))
                if event.get("type") == "error":
                    public["error"] = sanitize(event, replacements)
            public["helper_tool_events"] = tool_events
        else:
            try:
                response = json.loads(stdout)
                public["final_response"] = sanitize(response.get("result"), replacements)
                public["is_error"] = response.get("is_error")
                public["permission_denials"] = sanitize(response.get("permission_denials", []), replacements)
            except ValueError:
                public["parse_error"] = "CLI did not return its requested JSON result."
        if (evidence / "report.json").exists():
            report = json.loads((evidence / "report.json").read_text())
            public["helper_report"] = "helper/report.json"
            for file in evidence.rglob("*"):
                if not file.is_file():
                    continue
                target = out / "helper" / file.relative_to(evidence)
                target.parent.mkdir(parents=True, exist_ok=True)
                content = json.loads(file.read_text()) if file.suffix == ".json" else file.read_text()
                clean = sanitize(content, replacements)
                target.write_text(json.dumps(clean, indent=2) + "\n" if file.suffix == ".json" else clean)
            public["classification"] = report["classification"]
            public["verification"] = "Real explicit invocation executed the installed helper and produced captured evidence."
        else:
            public["classification"] = "NO_HELPER_EVIDENCE"
        (out / "session.json").write_text(json.dumps(public, indent=2) + "\n")
        print(f"{agent}: CLI exit {process.returncode}; {public['classification']}", flush=True)
        if public["final_response"]:
            print(public["final_response"], flush=True)
        return public


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agent", choices=["codex", "claude"], required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = run(args.agent, args.out.resolve())
    return 0 if result["cli_exit_code"] == 0 and result["classification"] == "CAUGHT" else 1


if __name__ == "__main__":
    sys.exit(main())
