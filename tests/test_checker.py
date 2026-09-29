import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
from conftest import ROOT, checker


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "shipping.py").write_text((ROOT / "demo/shipping.py").read_text())
    (repo / "test_shipping.py").write_text((ROOT / "demo/test_shipping.py").read_text())
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    return repo


def check(project, tmp_path, name="boundary", extra=(), patch=None):
    output = tmp_path / f"out-{len(list(tmp_path.glob('out-*')))}"
    patch_path = tmp_path / "fix.patch"
    patch_path.write_text(patch if patch is not None else (ROOT / "demo/fix.patch").read_text())
    args = ["--repo", str(project), "--patch", str(patch_path), "--allow", "shipping.py",
            "--protect", "test_shipping.py", "--test", f"test_shipping.py::test_{name}",
            "--expect-assert", f"test_shipping.py:{5 if name == 'weak' else 9}",
            "--bug-description", "100 must qualify for free shipping.", "--out", str(output), *extra]
    code = checker.main(args)
    return code, json.loads((output / "report.json").read_text()), output


@pytest.mark.parametrize("name,result,code", [("weak", "NOT_CAUGHT", 1), ("boundary", "CAUGHT", 0)])
def test_demo_outcomes_and_evidence(project, tmp_path, name, result, code):
    exit_code, report, out = check(project, tmp_path, name)
    assert exit_code == code
    assert report["classification"] == result
    assert len(report["runs"]) == 2
    assert report["snapshots"]["changed_files"] == ["shipping.py"]
    assert report["snapshots"]["fixed"]["test_shipping.py"] == report["snapshots"]["reversed"]["test_shipping.py"]
    for pair in report["runs"]:
        for run in pair.values():
            assert (out / run["stdout"]).exists()
            assert (out / run["stderr"]).exists()
            assert run["evidence"]["collected"] == [f"test_shipping.py::test_{name}"]
            assert not Path(run["cwd"]).exists()
    if name == "boundary":
        call = report["runs"][0]["reversed"]["evidence"]["events"][1]
        assert call["exception"] == "AssertionError"
        assert {"path": "test_shipping.py", "line": 9, "source": "assert free_shipping(100) is True"} in call["assertions"]


@pytest.mark.parametrize("body,result", [
    ("assert free_shipping(50) is True", "BASELINE_FAILED"),
    ("raise RuntimeError('free shipping 100 assertion caught')", "INCONCLUSIVE"),
    ("import missing_prove_fix_dependency", "INCONCLUSIVE"),
    ("pytest.skip('skip')", "INCONCLUSIVE"),
    ("time.sleep(10)", "INCONCLUSIVE"),
])
def test_unfavorable_and_infrastructure(project, tmp_path, body, result):
    content = (project / "test_shipping.py").read_text().replace("assert free_shipping(100) is True", body)
    content = content.replace("from shipping import free_shipping", "from shipping import free_shipping\nimport pytest, time")
    (project / "test_shipping.py").write_text(content)
    # Declare the valid weak assert for infrastructure cases; errors must not match it.
    extra = ["--runs", "1", "--timeout", "0.3" if body.startswith("time") else "10"]
    node_line = 10
    code, report, _ = check(project, tmp_path, extra=[*extra, "--expect-assert", f"test_shipping.py:{node_line}"] if body.startswith("assert") else [*extra, "--expect-assert", "test_shipping.py:6"])
    # The weak assert is a valid declared location, but an unrelated exception is never CAUGHT.
    assert report["classification"] == result
    assert code == checker.EXIT[result]


@pytest.mark.parametrize("kind", ["zero", "module-skip", "xfail", "xpass", "strict-xpass", "setup", "teardown"])
def test_collection_and_lifecycle(project, tmp_path, kind):
    file = project / "test_shipping.py"
    content = file.read_text()
    if kind == "zero":
        content = content.replace("test_boundary", "not_a_test")
    elif kind == "module-skip":
        content += "\nimport pytest\npytest.skip('module skipped', allow_module_level=True)\n"
    elif kind in {"xfail", "xpass", "strict-xpass"}:
        mark = "import pytest\n@pytest.mark.xfail(strict=" + str(kind == "strict-xpass") + ")\n"
        content = content.replace("def test_boundary():", mark + "def test_boundary():")
        if kind == "xfail":
            content = content.replace("assert free_shipping(100) is True", "assert free_shipping(100) is False")
    else:
        operation = "raise RuntimeError('setup')\n    yield" if kind == "setup" else "yield\n    raise RuntimeError('teardown')"
        content += "\nimport pytest\n@pytest.fixture(autouse=True)\ndef broken_fixture():\n    " + operation + "\n"
    file.write_text(content)
    line = next(i for i, text in enumerate(content.splitlines(), 1) if "assert free_shipping(100)" in text)
    _, report, _ = check(project, tmp_path, extra=["--runs", "1", "--expect-assert", f"test_shipping.py:{line}"])
    assert report["classification"] == "INCONCLUSIVE"


@pytest.mark.parametrize("patch", [
    "", "not a patch\n", "diff --git a/../shipping.py b/../shipping.py\n",
    "diff --git a//tmp/shipping.py b//tmp/shipping.py\n", "GIT binary patch\n",
    (ROOT / "demo/fix.patch").read_text().replace(">= 100", ">= 999"),
    (ROOT / "demo/fix.patch").read_text().replace("shipping.py", "test_shipping.py"),
    (ROOT / "demo/fix.patch").read_text().replace("@@ -1,3 +1,3 @@", "@@ -1,4 +1,3 @@"),
    (ROOT / "demo/fix.patch").read_text().replace("--- a/shipping.py", "new file mode 100644\n--- a/shipping.py"),
    (ROOT / "demo/fix.patch").read_text() + "\\ No newline at end of file\n",
])
def test_unsafe_or_nonapplicable_patches(project, tmp_path, patch):
    before = (project / "shipping.py").read_bytes()
    _, report, _ = check(project, tmp_path, patch=patch)
    assert report["classification"] == "INCONCLUSIVE"
    assert report["runs"] == []
    assert (project / "shipping.py").read_bytes() == before


@pytest.mark.parametrize("file", ["conftest.py", "setup.py", "tests/custom.py", "fixtures/data.py", "configuration.py"])
def test_protected_implementation_refused(project, tmp_path, file):
    target = project / file
    target.parent.mkdir(exist_ok=True)
    target.write_text((project / "shipping.py").read_text())
    git(project, "add", file)
    patch = (ROOT / "demo/fix.patch").read_text().replace("shipping.py", file)
    # Direct invocation isolates protection from allow-list mismatch.
    patch_path = tmp_path / "guard.patch"
    patch_path.write_text(patch)
    out = tmp_path / "guard-out"
    code = checker.main(["--repo", str(project), "--patch", str(patch_path), "--allow", file,
                         "--protect", file, "--test", "test_shipping.py::test_boundary", "--out", str(out)])
    assert code == 3
    assert not json.loads((out / "report.json").read_text())["runs"]


def test_preserves_staged_unstaged_new_files_index_head(project, tmp_path):
    (project / "shipping.py").write_text((project / "shipping.py").read_text() + "\n# Staged caller change\n")
    git(project, "add", "shipping.py")
    (project / "shipping.py").write_text((project / "shipping.py").read_text() + "# Unstaged caller change\n")
    git(project, "rm", "--cached", "test_shipping.py")
    (project / "notes.txt").write_text("Private untracked caller work\n")
    before_files = {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()}
    before_index = (project / ".git/index").read_bytes()
    before_head = git(project, "rev-parse", "HEAD")
    before_status = git(project, "status", "--porcelain")
    # git status may refresh stat data: capture the index after it.
    before_index = (project / ".git/index").read_bytes()
    code, report, _ = check(project, tmp_path, extra=["--include", "test_shipping.py"])
    assert code == 0
    assert {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()} == before_files
    assert (project / ".git/index").read_bytes() == before_index
    assert git(project, "rev-parse", "HEAD") == before_head
    assert git(project, "status", "--porcelain") == before_status
    assert report["caller_preservation"]["git_unchanged"]


def test_new_test_requires_explicit_include(project, tmp_path):
    git(project, "rm", "--cached", "test_shipping.py")
    _, report, _ = check(project, tmp_path)
    assert "--include" in report["explanation"]
    assert not report["runs"]


def test_exclusions_secrets_caches_and_explicit_include_refusal(project, tmp_path):
    for file in (".env", "credentials.json", ".venv/lib.py", "__pycache__/fake.pyc", "private.data"):
        target = project / file
        target.parent.mkdir(exist_ok=True)
        target.write_text("secret that must not be copied")
        git(project, "add", "-f", file)
    code, report, _ = check(project, tmp_path, extra=["--exclude", "private.data"])
    assert code == 0
    assert set(report["snapshots"]["fixed"]) == {"shipping.py", "test_shipping.py"}
    _, report, _ = check(project, tmp_path, extra=["--include", ".env"])
    assert not report["runs"]


@pytest.mark.parametrize("escaping", [True, False])
def test_symlinks_refused(project, tmp_path, escaping):
    file = project / "shipping.py"
    content = file.read_bytes()
    file.unlink()
    target = tmp_path / "outside.py" if escaping else project / "inside.py"
    target.write_bytes(content)
    file.symlink_to(target)
    _, report, _ = check(project, tmp_path)
    assert "Symlinks" in report["explanation"]
    assert not report["runs"]
    assert target.read_bytes() == content


def test_inputs_mutated_by_test_are_inconclusive(project, tmp_path):
    file = project / "test_shipping.py"
    file.write_text(file.read_text() + "\nfrom pathlib import Path\nPath('shipping.py').write_text('modified')\n")
    _, report, _ = check(project, tmp_path, extra=["--runs", "1"])
    assert report["classification"] == "INCONCLUSIVE"
    assert "amount >= 100" in (project / "shipping.py").read_text()


def test_editable_or_config_import_from_caller_is_inconclusive(project, tmp_path):
    file = project / "test_shipping.py"
    file.write_text(file.read_text().replace("from shipping import free_shipping",
        f"import sys\nsys.path.insert(0, {str(project)!r})\nfrom shipping import free_shipping"))
    _, report, _ = check(project, tmp_path, extra=["--expect-assert", "test_shipping.py:11", "--runs", "1"])
    assert report["classification"] == "INCONCLUSIVE"
    assert report["runs"][0]["fixed"]["evidence"]["import_violations"]


def test_missing_expected_or_wrong_assertion_never_caught(project, tmp_path):
    _, report, _ = check(project, tmp_path, extra=["--expect-assert", "test_shipping.py:5", "--runs", "1"])
    assert report["classification"] == "INCONCLUSIVE"
    assert report["runs"][0]["reversed"]["exit_code"] == 1


def test_inconsistent_reruns(project, tmp_path):
    counter = tmp_path / "counter"
    content = (project / "test_shipping.py").read_text()
    content += f"\nfrom pathlib import Path\np = Path({str(counter)!r})\nn = int(p.read_text()) + 1 if p.exists() else 1\np.write_text(str(n))\n"
    content = content.replace("assert free_shipping(100) is True", "assert (free_shipping(100) or n == 4) is True")
    (project / "test_shipping.py").write_text(content)
    _, report, _ = check(project, tmp_path)
    assert report["classification"] == "INCONCLUSIVE"
    assert "Reruns disagree" in report["explanation"]


def test_missing_python_prerequisite(project, tmp_path):
    _, report, _ = check(project, tmp_path, extra=["--python", str(tmp_path / "missing-python")])
    assert report["classification"] == "INCONCLUSIVE"
    assert "missing-python" in report["explanation"]


def test_output_refusal_leaves_caller_untouched(project, tmp_path):
    out = project / "existing"
    out.mkdir()
    (out / "precious").write_text("keep")
    code = checker.main(["--repo", str(project), "--patch", str(ROOT / "demo/fix.patch"),
        "--allow", "shipping.py", "--test", "test_shipping.py::test_boundary", "--out", str(out)])
    assert code == 3
    assert (out / "precious").read_text() == "keep"


def test_sigterm_cleans_up_snapshots_and_child_group(project, tmp_path):
    owned = tmp_path / "owned"
    owned.mkdir()
    file = project / "test_shipping.py"
    file.write_text(file.read_text() + "\nimport time\ntime.sleep(60)\n")
    before = (project / "shipping.py").read_bytes()
    output = tmp_path / "interrupted"
    command = [sys.executable, str(ROOT / "skills/prove-fix/scripts/check.py"),
        "--repo", str(project), "--patch", str(ROOT / "demo/fix.patch"), "--allow", "shipping.py",
        "--test", "test_shipping.py::test_boundary", "--out", str(output), "--timeout", "90"]
    process = subprocess.Popen(command, env={**os.environ, "TMPDIR": str(owned)}, stdout=subprocess.PIPE)
    deadline = time.monotonic() + 10
    while not list(owned.glob("prove-fix-*/run-1-fixed-home")) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert process.poll() is None
    process.send_signal(signal.SIGTERM)
    process.communicate(timeout=10)
    assert process.returncode == 130
    assert json.loads((output / "report.json").read_text())["classification"] == "INCONCLUSIVE"
    assert not list(owned.iterdir())
    assert (project / "shipping.py").read_bytes() == before


def test_strict_multihunk_reversal(tmp_path):
    file = tmp_path / "code.py"
    file.write_text("a = 2\nb = 0\nc = 4\n")
    patch = "diff --git a/code.py b/code.py\n--- a/code.py\n+++ b/code.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n@@ -3 +3 @@\n-c = 3\n+c = 4\n"
    checker.reverse_patch(tmp_path, checker.parse_patch(patch))
    assert file.read_text() == "a = 1\nb = 0\nc = 3\n"


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_project_local_installed_helper_on_its_own_project(project, tmp_path, agent):
    from conftest import load
    installer = load("local_installer", ROOT / "scripts/install.py")
    skill = installer.install(agent, project)
    out = tmp_path / "local-install-result"
    command = [sys.executable, str(skill / "scripts/check.py"), "--repo", str(project),
        "--patch", str(ROOT / "demo/fix.patch"), "--allow", "shipping.py", "--protect", "test_shipping.py",
        "--test", "test_shipping.py::test_boundary", "--expect-assert", "test_shipping.py:9",
        "--bug-description", "100 must qualify", "--out", str(out)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((out / "report.json").read_text())
    assert report["classification"] == "CAUGHT"
    assert not report["runs"][0]["fixed"]["evidence"]["import_violations"]
    assert report["caller_preservation"]["git_unchanged"]


def test_nested_implementation_assertion_is_not_the_expected_test_assert(project, tmp_path):
    fixed = 'def free_shipping(amount):\n    return amount >= 100\n'
    (project / 'shipping.py').write_text(fixed)
    patch = ('diff --git a/shipping.py b/shipping.py\n--- a/shipping.py\n+++ b/shipping.py\n'
             '@@ -1,3 +1,2 @@\n def free_shipping(amount):\n'
             '-    assert amount != 100\n-    return amount > 100\n+    return amount >= 100\n')
    code, report, _ = check(project, tmp_path, patch=patch, extra=['--runs', '1'])
    assert code == 3
    call = report['runs'][0]['reversed']['evidence']['events'][1]
    assert {'path': 'test_shipping.py', 'line': 9, 'source': 'assert free_shipping(100) is True'} in call['assertions']
    assert call['assertion_origin']['path'] == 'shipping.py'
    assert report['classification'] == 'INCONCLUSIVE'


def test_unconventionally_named_virtual_environment_is_excluded(project, tmp_path):
    environment = project / 'custom-interpreter'
    environment.mkdir()
    (environment / 'pyvenv.cfg').write_text('home = /example\n')
    (environment / 'hidden.py').write_text('secret = 1\n')
    git(project, 'add', 'custom-interpreter')
    code, report, _ = check(project, tmp_path, extra=['--runs', '1'])
    assert code == 0
    assert set(report['snapshots']['fixed']) == {'shipping.py', 'test_shipping.py'}
    code, refused, _ = check(project, tmp_path, extra=['--include', 'custom-interpreter/hidden.py'])
    assert code == 3
    assert not refused['runs']
