# Helper reference

Requires Python 3.11+, Git, Linux/macOS, and pytest 8.3–9.x already installed in the
selected interpreter. Core copying, patching, reporting, and subprocess management
use the standard library. Supports one exact in-process Python pytest node ID
(including a single parametrized case). Third-party pytest plugin autoload is off.
Explicit project plugins still run as trusted project code. No shell commands,
framework adapters, subprocess-only implementation checks, or dependency installation.

```bash
python /absolute/path/to/prove-fix/scripts/check.py \
  --repo /absolute/path/to/project \
  --patch /absolute/path/to/implementation-fix.patch \
  --allow shipping.py \
  --protect tests --protect fixtures \
  --include tests/test_shipping.py \
  --test tests/test_shipping.py::test_boundary \
  --expect-assert tests/test_shipping.py:9 \
  --bug-description 'The order total 100 must qualify for free shipping.' \
  --timeout 30 --runs 2 --out /tmp/prove-fix-evidence
```

The example paths must exist in the selected project; do not protect absent paths.
`--out` must be new and outside the caller repo. `--python` selects an absolute
interpreter path (default: the interpreter running the helper). Use an already
prepared environment; an editable install must not point back to the caller's code.

`--patch` is the forward bug fix (buggy → fixed); the helper reverses it. Require
ordinary `diff --git a/file b/file`, `---`, `+++`, and unified hunks. Existing `.py`
files only, UTF-8/LF with final newlines, simple relative paths, exact line positions
and content. Context-only/no-op hunks, empty ranges, adds/deletes, renames, mode
changes, binary patches, quoted/space-containing paths, submodules, conflicts, and
all symlinks are refused. `--allow FILE` repeats and must equal the patch file set.
Explicit guards plus conventional test/fixture/config names cannot be reversed.
Unconventionally named fixtures/config Python files must be explicitly protected;
the agent must inspect the diff for implementation-only scope.

## Snapshot rules

Copy tracked files at their current working-tree contents, including staged and
unstaged edits. Deleted working-tree files remain absent. Copy new/untracked files
only when explicitly included as individual `--include FILE` paths. The selected
new test needs inclusion even if Git normally ignores it. No staging or committing.

Exclude `.git`, `.hg`, `.svn`, agent config dirs, `.venv`, `venv`, `env`,
`node_modules`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`,
`.nox`, `.cache`, `.hypothesis`, `__pypackages__`, `build`, `dist`, `*.egg-info`,
all `.venv*` directories and directories marked by `pyvenv.cfg`, `.aws`, `.ssh`, `.azure`, `.gcp`;
filenames beginning `.env`, `credentials`, or `secrets`; `.netrc`, `.npmrc`,
`.pypirc`, `id_rsa`, `id_ed25519`; and `.pem`, `.key`, `.p12`, `.pfx`, `.pyc`, `.pyo`.
These rules also exclude tracked files and cannot be overridden by `--include`.
Use repeatable `--exclude FILE_OR_DIR` for additional sensitive or irrelevant files.
Name rules cannot detect a secret embedded in arbitrary source: review the inputs.
Do not include real credentials to satisfy a project prerequisite. Refuse that run.

Snapshots have independent regular files and matching modes. Hash every selected
file; verify only allowed implementation files differ before execution. Every
rerun uses fresh independent copies. Abort on copied-input mutation or an import
from the caller checkout. Require all selected implementation files to be imported
from the snapshot. Use isolated Python startup, a minimal child environment, a
private temporary HOME, no inherited PYTHONPATH/PYTEST_ADDOPTS/credential variables,
and no pytest cache/bytecode writes. This does not sandbox arbitrary code: project
code still has the OS permissions of the invoking process. Tests needing custom
environment variables or external services are outside this minimal interface.

## Evidence and results

`report.json` separates observations (`runs`, `snapshots`, hashes, exit codes,
durations, captured log paths) from caller-supplied `interpretation`. It records
the exact patch and commands. Logs are relative to the output directory. Structured
`pytest.json` includes collection, setup/call/teardown outcomes, exceptions,
assertion paths/lines/source and originating assertion, traceback, pytest version, and import validation.
Source locations in evidence are one-based. Command `cwd` values point to temporary
snapshots that are cleaned up; fixture plus patch plus hashes reproduce them.

| Classification | Helper exit | Requirement |
| --- | --- | --- |
| CAUGHT | 0 | Fixed passes; reversed fails with AssertionError at the declared test assert in all reruns; target bug description supplied. Agent must review attribution. |
| NOT_CAUGHT | 1 | The selected test actually runs and passes in both snapshots in all reruns. |
| BASELINE_FAILED | 2 | A consistent supported assertion failure in the fixed baseline. |
| INCONCLUSIVE | 3 | Prerequisites, patch, collection, skip/xfail/xpass, setup/teardown, import/runtime errors, timeout, unexpected assertion, input mutation, or inconsistent reruns. |

SIGINT/SIGTERM clean up owned process groups and temporary files, preserve any
completed evidence, and return 130 with INCONCLUSIVE. SIGKILL/OS failure cannot be
handled. Invalid CLI syntax returns argparse's 2 before a report is created. An
existing/inside-repo output directory is refused with 3 without writing into it.
Nonzero test exit alone never establishes CAUGHT. `--expect-assert` is an AST-checked
assert start location, not a stderr keyword. A report without that expectation
can observe NOT_CAUGHT, but an assertion failure remains INCONCLUSIVE for review.
