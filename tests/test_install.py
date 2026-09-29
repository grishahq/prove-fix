import json
from pathlib import Path
import subprocess
import sys

import pytest
from conftest import ROOT, load

installer = load("installer", ROOT / "scripts/install.py")


@pytest.mark.parametrize("agent", ["claude", "codex"])
@pytest.mark.parametrize("scope", ["project", "user"])
def test_standalone_installation_from_different_project(tmp_path, agent, scope):
    root = tmp_path / scope
    args = [sys.executable, str(ROOT / "scripts/install.py"), "--agent", agent]
    args += ["--project", str(root)] if scope == "project" else ["--user", "--home", str(root)]
    subprocess.run([*args, "--dry-run"], check=True)
    assert not root.exists()
    subprocess.run(args, check=True)
    dest = root / (".claude" if agent == "claude" else ".agents") / "skills/prove-fix"
    helper = dest / "scripts/check.py"
    assert helper.read_bytes() == (ROOT / "skills/prove-fix/scripts/check.py").read_bytes()
    if agent == "claude":
        assert "disable-model-invocation: true" in (dest / "SKILL.md").read_text()
    else:
        assert "allow_implicit_invocation: false" in (dest / "agents/openai.yaml").read_text()
        assert "disable-model-invocation" not in (dest / "SKILL.md").read_text()
    other = tmp_path / "other-project"
    other.mkdir()
    out = tmp_path / "demo"
    subprocess.run([sys.executable, str(ROOT / "scripts/demo.py"), "--checker", str(helper),
                    "--out", str(out), "--runs", "1"], cwd=other, check=True, capture_output=True)
    summary = json.loads((out / "summary.json").read_text())
    assert [c["classification"] for c in summary["comparisons"]] == ["NOT_CAUGHT", "CAUGHT"]
    before = helper.read_bytes()
    assert subprocess.run(args, capture_output=True).returncode == 1
    assert helper.read_bytes() == before


def test_install_symlink_destination_is_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / ".agents").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlink"):
        installer.install("codex", root)
