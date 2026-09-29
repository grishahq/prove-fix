#!/usr/bin/env python3
"""Compare a working-tree snapshot with only an explicit implementation fix reversed."""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

VERSION = "0.1.0"
EXIT = {"CAUGHT": 0, "NOT_CAUGHT": 1, "BASELINE_FAILED": 2, "INCONCLUSIVE": 3}
EXCLUDED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
                 "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
                 ".nox", ".cache", "build", "dist", ".aws", ".ssh", ".azure", ".gcp",
                 ".codex", ".claude", ".agents", ".hypothesis", "__pypackages__"}
CONFIG_NAMES = {"conftest.py", "setup.py", "pyproject.toml", "pytest.ini", "tox.ini",
                "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock"}


class Refused(Exception):
    """An unsupported input or an invariant that could not be established."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise Refused(f"Unsupported path spelling: {value!r}; use simple repository-relative paths.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in value.split("/")):
        raise Refused(f"Unsafe relative path: {value!r}.")
    return value


def exclusion(path):
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    if any(p in EXCLUDED_DIRS or p.startswith(".venv") or p.endswith(".egg-info") for p in parts):
        return "Git/agent internals, environment, cache, or generated directory"
    if (name.startswith((".env", "credentials", "secrets")) or
            name in {".netrc", ".npmrc", ".pypirc", "id_rsa", "id_ed25519"} or
            name.endswith((".pem", ".key", ".p12", ".pfx", ".pyc", ".pyo"))):
        return "Secret/credential filename or bytecode"
    return None


def protected(path, guards):
    parts = PurePosixPath(path).parts
    name = parts[-1]
    return (any(path == p or path.startswith(p + "/") for p in guards) or
            any(p.lower() in {"test", "tests", "fixtures", "config", "configs", ".github"}
                for p in parts) or name in CONFIG_NAMES or
            name.startswith(("test_", "requirements")) or name.endswith("_test.py"))


def regular_file(root, path):
    for i in range(1, len(PurePosixPath(path).parts) + 1):
        part = root.joinpath(*PurePosixPath(path).parts[:i])
        if part.is_symlink():
            raise Refused(f"Symlinks are unsupported (including escaping links): {path}.")
    file = root / path
    if not file.is_file():
        raise Refused(f"Required regular file is missing: {path}.")
    if file.resolve().is_relative_to(root.resolve()) is False:
        raise Refused(f"File escapes repository: {path}.")
    return file


def git(repo, *args, allow_failure=False):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env)
    if result.returncode and not allow_failure:
        raise Refused("Git read failed: " + result.stderr.decode(errors="replace").strip())
    return result


def git_state(repo):
    head = git(repo, "rev-parse", "--verify", "HEAD", allow_failure=True)
    index = git(repo, "rev-parse", "--git-path", "index").stdout.decode().strip()
    index_path = Path(index) if Path(index).is_absolute() else repo / index
    return {"head": head.stdout.decode().strip() or None,
            "index_sha256": sha(index_path.read_bytes()) if index_path.exists() else None}


def inventory(repo, includes, excludes):
    top = git(repo, "rev-parse", "--show-toplevel").stdout.decode().strip()
    if Path(top).resolve() != repo:
        raise Refused("--repo must be the Git working-tree root.")
    records = git(repo, "ls-files", "--stage", "-z").stdout.split(b"\0")
    tracked = set()
    for record in records:
        if not record:
            continue
        meta, raw_path = record.split(b"\t", 1)
        mode, _, stage = meta.split()
        if stage != b"0":
            raise Refused("Resolve index conflicts before checking.")
        if mode == b"160000":
            raise Refused("Submodules are unsupported; use a standalone repository.")
        tracked.add(os.fsdecode(raw_path))
    for path in excludes:
        safe_path(path)
    def explicitly_excluded(path):
        return any(path == p or path.startswith(p + "/") for p in excludes)
    def virtual_environment(path):
        parents = PurePosixPath(path).parts[:-1]
        return any((repo.joinpath(*parents[:i]) / "pyvenv.cfg").is_file()
                   for i in range(1, len(parents) + 1))
    for path in includes:
        safe_path(path)
        if exclusion(path) or explicitly_excluded(path) or virtual_environment(path):
            raise Refused(f"Explicit inclusion is forbidden for excluded file: {path}.")
        regular_file(repo, path)
    selected, omitted = [], []
    for path in sorted(tracked | set(includes)):
        reason = (exclusion(path) or ("Explicit --exclude" if explicitly_excluded(path) else None)
                  or ("Virtual environment (pyvenv.cfg)" if virtual_environment(path) else None))
        if reason:
            omitted.append({"path": path, "reason": reason})
            continue
        safe_path(path)
        # A working-tree deletion stays absent in both copies.
        if not (repo / path).exists() and not (repo / path).is_symlink():
            omitted.append({"path": path, "reason": "Deleted in working tree"})
            continue
        regular_file(repo, path)
        selected.append(path)
    return selected, omitted


def manifest(root, files):
    return {path: {"sha256": sha(regular_file(root, path).read_bytes()),
                   "mode": stat.S_IMODE((root / path).stat().st_mode)} for path in files}


def copy_files(source, target, files):
    target.mkdir()
    for path in files:
        dst = target / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(regular_file(source, path), dst)
        dst.chmod(stat.S_IMODE((source / path).stat().st_mode))


def parse_patch(text):
    """Strict UTF-8/LF git-style unified diffs of existing files, without fuzzy offsets."""
    if "\r" in text or not text.endswith("\n"):
        raise Refused("Patch must be UTF-8 with LF lines and a final newline.")
    lines = text.splitlines(keepends=True)
    patches = {}
    i = 0
    while i < len(lines):
        match = re.fullmatch(r"diff --git a/([A-Za-z0-9_./-]+) b/([A-Za-z0-9_./-]+)\n", lines[i])
        if not match or match[1] != match[2]:
            raise Refused("Only git-style patches of existing same-path files are supported.")
        path = safe_path(match[1])
        if path in patches:
            raise Refused("Duplicate patch file section: " + path)
        i += 1
        if i < len(lines) and re.fullmatch(r"index [0-9a-f]+\.\.[0-9a-f]+(?: 100[0-7]{3})?\n", lines[i]):
            i += 1
        if lines[i:i + 2] != [f"--- a/{path}\n", f"+++ b/{path}\n"]:
            raise Refused("Unsupported patch metadata: no renames, modes, adds, deletes, or binary diffs.")
        i += 2
        hunks = []
        while i < len(lines) and lines[i].startswith("@@ "):
            h = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n", lines[i])
            if not h:
                raise Refused("Malformed unified hunk header.")
            old_start, old_count = int(h[1]), int(h[2] or 1)
            new_start, new_count = int(h[3]), int(h[4] or 1)
            # Empty ranges/additions/deletions are deliberately outside v0.1.
            if min(old_start, old_count, new_start, new_count) < 1:
                raise Refused("Empty hunk ranges are unsupported.")
            i += 1
            old, new = [], []
            while i < len(lines) and lines[i][:1] in {" ", "+", "-"}:
                prefix, content = lines[i][0], lines[i][1:]
                if prefix in {" ", "-"}:
                    old.append(content)
                if prefix in {" ", "+"}:
                    new.append(content)
                i += 1
            if len(old) != old_count or len(new) != new_count or old == new:
                raise Refused("Hunk counts disagree, or hunk makes no change.")
            hunks.append({"old_start": old_start, "new_start": new_start, "old": old, "new": new})
        if not hunks:
            raise Refused("Patch section has no supported hunks.")
        patches[path] = hunks
    if not patches:
        raise Refused("Empty patch.")
    return patches


def reverse_patch(root, patches):
    for path, hunks in patches.items():
        file = regular_file(root, path)
        try:
            text = file.read_bytes().decode("utf-8")
        except UnicodeError as exc:
            raise Refused("Implementation must be UTF-8 text.") from exc
        if "\r" in text or not text.endswith("\n"):
            raise Refused("Implementation must use LF and end with a newline.")
        lines = text.splitlines(keepends=True)
        rebuilt, cursor = [], 0
        offset = 0
        for h in hunks:
            start = h["new_start"] - 1
            if start < cursor or h["new_start"] != h["old_start"] + offset:
                raise Refused("Overlapping or inconsistent hunk coordinates: " + path)
            if lines[start:start + len(h["new"])] != h["new"]:
                raise Refused("Patch does not exactly match the fixed working-tree file: " + path)
            rebuilt.extend(lines[cursor:start])
            rebuilt.extend(h["old"])
            cursor = start + len(h["new"])
            offset += len(h["new"]) - len(h["old"])
        rebuilt.extend(lines[cursor:])
        file.write_text("".join(rebuilt), encoding="utf-8")


def assertion_spec(root, value, test_path):
    if value is None:
        return None
    try:
        path, raw_line = value.rsplit(":", 1)
        safe_path(path)
        line = int(raw_line)
        if path != test_path:
            raise ValueError
        source = regular_file(root, path).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assert) and node.lineno == line:
                return {"path": path, "line": line, "source": ast.get_source_segment(source, node)}
    except (ValueError, SyntaxError, UnicodeError):
        pass
    raise Refused("--expect-assert must name an actual assert start line in the selected test file.")


def kill_process(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_test(args, root, work, label, files, implementations):
    logs = args.out / label
    logs.mkdir()
    result = logs / "pytest.json"
    # A project-local installed skill lives in the caller tree. Run our trusted
    # instrumentation from an owned copy so it is not mistaken for caller code.
    runner = work / "pytest_runner.py"
    if not runner.exists():
        shutil.copyfile(Path(__file__).with_name("pytest_runner.py"), runner)
    command = [args.python, "-I", str(runner), "--result", str(result), "--original", str(args.repo),
               "--node", args.test]
    for path in implementations:
        command += ["--implementation", path]
    home = work / (label + "-home")
    home.mkdir()
    env = {"PATH": str(Path(args.python).parent) + os.pathsep + os.defpath,
           "HOME": str(home), "TMPDIR": str(home), "LANG": "C.UTF-8",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    before = manifest(root, files)
    started = time.monotonic()
    observed = {"command": command, "cwd": str(root), "stdout": f"{label}/stdout.txt",
                "stderr": f"{label}/stderr.txt", "structured": f"{label}/pytest.json",
                "timed_out": False}
    with (logs / "stdout.txt").open("wb") as stdout, (logs / "stderr.txt").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=stdout, stderr=stderr,
                                   start_new_session=True)
        try:
            observed["exit_code"] = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            kill_process(process)
            observed["exit_code"] = process.returncode
            observed["timed_out"] = True
        except BaseException:
            kill_process(process)
            raise
        finally:
            # Reap background descendants even if the pytest parent has already exited.
            kill_process(process)
    observed["duration_seconds"] = round(time.monotonic() - started, 4)
    observed["evidence"] = None
    if result.exists():
        try:
            observed["evidence"] = json.loads(result.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    try:
        observed["input_files_unchanged"] = manifest(root, files) == before
    except Refused:
        observed["input_files_unchanged"] = False
    return observed


def outcome(run, node, implementations):
    if run["timed_out"]:
        return "invalid", "Test timeout."
    data = run.get("evidence")
    if not data or data.get("schema") != 1:
        return "invalid", "Missing structured pytest evidence (check prerequisites and logs)."
    if (not run["input_files_unchanged"] or data["import_violations"] or
            data["loaded_implementation"] != sorted(implementations)):
        return "invalid", "Inputs changed, caller code imported, or selected implementation was not imported."
    if data["collected"] != [node] or data["collection_errors"] or data["internal_errors"]:
        return "invalid", "Exactly one selected test must collect without collection/internal errors."
    events = data["events"]
    if len(events) != 3 or [e["phase"] for e in events] != ["setup", "call", "teardown"]:
        return "invalid", "Incomplete test lifecycle."
    if any(e.get("xfail") or e["outcome"] == "skipped" for e in events):
        return "invalid", "Skip/xfail/xpass does not establish a passing regression test."
    if events[0]["outcome"] != "passed" or events[2]["outcome"] != "passed":
        return "invalid", "Setup/teardown failed."
    call = events[1]
    if call["outcome"] == "passed" and run["exit_code"] == data["exit_code"] == 0:
        return "pass", "Selected test passed."
    if (call["outcome"] == "failed" and call["exception"] == "AssertionError" and
            call["assertions"] and run["exit_code"] == data["exit_code"] == 1):
        return "assertion", "AssertionError in the selected test."
    return "invalid", "Failure is not a supported assertion result; inspect the captured logs."


def classify(runs, node, implementations, expected, description):
    observations, signatures = [], []
    for pair in runs:
        fixed, fwhy = outcome(pair["fixed"], node, implementations)
        reversed_, rwhy = outcome(pair["reversed"], node, implementations)
        if "invalid" in {fixed, reversed_}:
            return "INCONCLUSIVE", fwhy if fixed == "invalid" else rwhy
        if fixed == "assertion":
            result = "BASELINE_FAILED"
        elif reversed_ == "pass":
            result = "NOT_CAUGHT"
        else:
            call = pair["reversed"]["evidence"]["events"][1]
            if (not expected or not description or expected not in call["assertions"]
                    or expected != call["assertion_origin"]):
                return "INCONCLUSIVE", "Failure needs an expected assertion and bug attribution; inspect evidence."
            result = "CAUGHT"
        observations.append(result)
        signatures.append([(side, e["outcome"], e["exception"], e["assertions"], e["failure"])
                           for side in ("fixed", "reversed")
                           for e in pair[side]["evidence"]["events"]])
    if len(set(observations)) != 1 or any(s != signatures[0] for s in signatures[1:]):
        return "INCONCLUSIVE", "Reruns disagree; finite reruns cannot rule out flakiness."
    why = {"CAUGHT": "The reversed fix failed at the declared bug-related assertion in every run.",
           "NOT_CAUGHT": "The unchanged selected test passed with and without the fix in every run.",
           "BASELINE_FAILED": "The fixed snapshot failed an assertion; establish a passing baseline first."}
    return observations[0], why[observations[0]]


def compare(args, report):
    if os.name != "posix":
        raise Refused("v0.1 supports Linux/macOS; process cleanup requires POSIX process groups.")
    if not math.isfinite(args.timeout) or args.timeout <= 0 or not 1 <= args.runs <= 5:
        raise Refused("Use a finite positive timeout and 1..5 runs.")
    files, omitted = inventory(args.repo, args.include, args.exclude)
    test_path = safe_path(args.test.split("::")[0])
    if "::" not in args.test or test_path not in files or not test_path.endswith(".py"):
        raise Refused("Select one Python pytest node ID. New test files require --include FILE.")
    guards = [safe_path(p) for p in args.protect] + [test_path]
    for guard in guards:
        if not any(p == guard or p.startswith(guard + "/") for p in files):
            raise Refused("Protected path is absent from the snapshot: " + guard)
    patches = parse_patch(args.patch.read_bytes().decode("utf-8"))
    allowed = [safe_path(p) for p in args.allow]
    if set(patches) != set(allowed):
        raise Refused("--allow must list exactly the implementation files changed by the patch.")
    for path in patches:
        if path not in files or not path.endswith(".py") or protected(path, guards):
            raise Refused("Patch targets an absent, protected, or non-Python implementation file: " + path)
    expected = assertion_spec(args.repo, args.expect_assert, test_path)
    initial = manifest(args.repo, files)
    initial_git = git_state(args.repo)
    report.update({"version": VERSION, "test": args.test, "runs_requested": args.runs,
                   "timeout_seconds": args.timeout, "implementation_paths": sorted(patches),
                   "protected_paths": guards, "explicit_inclusions": args.include,
                   "explicit_exclusions": args.exclude,
                   "excluded_files": omitted, "patch": {"direction": "forward fix; reversed in second snapshot",
                   "sha256": sha(args.patch.read_bytes()), "text": args.patch.read_text(encoding="utf-8")},
                   "interpretation": {"expected_assertion": expected, "target_bug": args.bug_description,
                   "attribution": "Caller-supplied expectation. Helper checks AssertionError and source location; agent must inspect semantics."}})
    with tempfile.TemporaryDirectory(prefix="prove-fix-") as temp:
        work = Path(temp).resolve()
        fixed = work / "fixed-template"
        reverted = work / "reversed-template"
        copy_files(args.repo, fixed, files)
        if manifest(fixed, files) != initial or manifest(args.repo, files) != initial:
            raise Refused("Working tree changed during capture; retry when edits have stopped.")
        copy_files(fixed, reverted, files)
        reverse_patch(reverted, patches)
        fhash, rhash = manifest(fixed, files), manifest(reverted, files)
        changed = sorted(p for p in files if fhash[p] != rhash[p])
        if changed != sorted(patches) or any(fhash[p]["mode"] != rhash[p]["mode"] for p in files):
            raise Refused("Snapshot differences are not exactly the selected implementation changes.")
        report["snapshots"] = {"fixed": fhash, "reversed": rhash,
                               "changed_files": changed, "non_selected_identical": True}
        report["runs"] = []
        for number in range(1, args.runs + 1):
            pair = {}
            for side, template in (("fixed", fixed), ("reversed", reverted)):
                label = f"run-{number}-{side}"
                root = work / label
                copy_files(template, root, files)
                pair[side] = run_test(args, root, work, label, files, sorted(patches))
            report["runs"].append(pair)
        result, why = classify(report["runs"], args.test, sorted(patches), expected, args.bug_description)
        current_git = git_state(args.repo)
        report["caller_preservation"] = {"before": initial_git, "after": current_git,
                                        "files_unchanged": manifest(args.repo, files) == initial,
                                        "git_unchanged": current_git == initial_git}
        if not all(report["caller_preservation"][k] for k in ("files_unchanged", "git_unchanged")):
            result, why = "INCONCLUSIVE", "Caller changed during the check; retry without concurrent edits."
        report["classification"], report["explanation"] = result, why


def parser():
    p = argparse.ArgumentParser(description="Your test is green. Put the bug back.",
        epilog="Trusted repositories only. Temporary copies are NOT a security sandbox.")
    p.add_argument("--version", action="version", version="prove-fix " + VERSION)
    p.add_argument("--repo", type=Path, required=True, help="Git working-tree root")
    p.add_argument("--patch", type=Path, required=True, help="Forward implementation fix in git-style unified diff")
    p.add_argument("--allow", action="append", required=True, help="Exact allowed implementation .py file (repeatable)")
    p.add_argument("--protect", action="append", default=[], help="Test/fixture/config file or directory (repeatable)")
    p.add_argument("--include", action="append", default=[], help="Explicit new/untracked regular file (repeatable)")
    p.add_argument("--exclude", action="append", default=[], help="Additional sensitive file or directory to omit (repeatable)")
    p.add_argument("--test", required=True, help="One exact pytest node ID, e.g. tests/test_shipping.py::test_boundary")
    p.add_argument("--expect-assert", help="Expected bug assertion FILE:LINE; required for CAUGHT")
    p.add_argument("--bug-description", help="Why that assertion detects the target bug; caller/agent interpretation")
    p.add_argument("--python", default=sys.executable, help="Python with pytest already installed; never installs dependencies")
    p.add_argument("--timeout", type=float, default=30, help="Seconds per subprocess (default: 30)")
    p.add_argument("--runs", type=int, default=2, help="Independent reruns per side (default: 2, max: 5)")
    p.add_argument("--out", type=Path, required=True, help="New output directory outside the caller repository")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    args.repo = args.repo.resolve()
    args.patch = args.patch.resolve()
    args.out = args.out.resolve()
    args.python = os.path.abspath(args.python)
    if args.out.is_relative_to(args.repo) or args.out.exists():
        print("INCONCLUSIVE: --out must be a new directory outside the caller repository.", file=sys.stderr)
        return 3
    args.out.mkdir(parents=True)
    report = {"schema": 1, "classification": "INCONCLUSIVE", "runs": [],
              "helper_hashes": {name: sha(Path(__file__).with_name(name).read_bytes())
                                for name in ("check.py", "pytest_runner.py")},
              "helper_command": [sys.executable, str(Path(__file__).resolve()),
                                 *(argv if argv is not None else sys.argv[1:])],
              "safety_boundary": "Temporary copies are NOT a security sandbox for project code."}
    interrupted = False
    previous = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        compare(args, report)
    except KeyboardInterrupt:
        report["explanation"] = "Interrupted; owned subprocesses and temporary snapshots were cleaned up."
        interrupted = True
    except (Refused, OSError, UnicodeError, ValueError) as exc:
        report["explanation"] = str(exc)
    finally:
        signal.signal(signal.SIGTERM, previous)
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = report["classification"]
    print(f"prove-fix | {result}")
    for i, pair in enumerate(report["runs"], 1):
        facts = []
        for side in ("fixed", "reversed"):
            kind, _ = outcome(pair[side], args.test, report.get("implementation_paths", []))
            facts.append(f"{side}={'PASS' if kind == 'pass' else 'FAIL' if kind == 'assertion' else 'INCONCLUSIVE'}")
        print(f"  run {i}: " + " | ".join(facts))
    print("  " + report["explanation"])
    print("  Evidence: " + str(args.out / "report.json"))
    print("  These runs do not establish overall correctness or absence of flakiness.")
    return 130 if interrupted else EXIT[result]


if __name__ == "__main__":
    sys.exit(main())
