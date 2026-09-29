# Validation record

Work was performed in the clone of `https://github.com/grishahq/prove-fix.git`.
The remote was empty when inspected on 2026-09-29. No pre-existing repository work
was overwritten. No real global skill installation or agent settings were changed.

## Commands and observations

The development environment used Python 3.11.14 and pytest 9.1.1. Exact local commands:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/demo.py --out media/evidence/demo
.venv/bin/python scripts/demo.py --out artifacts/demo-repeat
uv venv --python 3.11 .venv-media
uv pip install --python .venv-media/bin/python -r requirements-media.txt
.venv-media/bin/python scripts/render_video.py
```

The demo observed NOT_CAUGHT (PASS/PASS at 150) and CAUGHT (PASS/expected assertion
failure at 100) with two independent reruns per side. A separate capture repeated
both comparisons. Finite repeats do not prove absence of flakiness. JSON includes
actual durations, commands, file/test hashes, patch, exit codes and log paths.

Automated tests cover those outcomes, baseline assertion failure, import/runtime
errors, zero matching tests, collection/module skip, skip/xfail/xpass, setup and
teardown errors, timeout, unsafe/non-applicable/protected patches, symlinks,
copy-input mutation, import from the caller, unrelated nested AssertionError,
inconsistent reruns, staged/unstaged/new test preservation, index/HEAD preservation,
SIGTERM cleanup, exact multiple-hunk reversal, exclusions, and standalone installation.
Both project-local and user-level installs are tested in temporary roots, including
execution from another project and from the project containing its own installed
skill. Installer dry runs make no changes and overwrites are refused.

## Official installation documentation

Checked on 2026-09-29:

- [Codex skills](https://developers.openai.com/codex/skills/): `.agents/skills` in
  projects, `~/.agents/skills` for the user, explicit `$skill` invocation, and
  `policy.allow_implicit_invocation: false` in `agents/openai.yaml`.
- [Claude Code skills](https://code.claude.com/docs/en/skills): project/user
  `.claude/skills`, `/name`, and `disable-model-invocation: true` frontmatter.

Packaging/install tests establish bundled-helper execution, not agent behavior.
Live CLI attempts are described separately below. Authentication status alone is
not evidence of a completed session.

## Live authenticated CLI attempts

Opt-in reproduction (uses existing authorized CLI authentication, no CI/API-key dependency):

```bash
.venv/bin/python scripts/agent_smoke.py --agent codex --out artifacts/agent-codex
.venv/bin/python scripts/agent_smoke.py --agent claude --out artifacts/agent-claude
.venv/bin/python scripts/agent_smoke.py --agent claude --out artifacts/agent-claude-fixed
```

Each creates an owned educational Git project, installs one project-local skill,
and explicitly invokes `$prove-fix` or `/prove-fix`. It captures the actual helper
report and final agent response, with a minimal sanitized session record. Private
full CLI diagnostics stay in ignored `artifacts/agent-private/`. No permission
bypass flags or global modifications are used. Claude's command grants only
read/search, read-only Git inspection, and the exact bundled-helper command.

Codex CLI 0.154.0 was authenticated, but the service rejected its configured model:
`The 'gpt-6-sol' model is not supported when using Codex with a ChatGPT account.`
It exited 1 before running the helper. **Codex end-to-end execution is not verified.**
Its two install scopes and standalone bundled-helper execution are verified.

Claude Code 2.1.284 performed a real `/prove-fix` invocation. The first attempt
revealed that an installed runner within the caller tree was incorrectly flagged
as a caller-code import. The checker now copies its own instrumentation into its
owned temporary directory. A subsequent real invocation returned CAUGHT, reviewed
the expected assertion and logs, distinguished interpretation from observations,
and reported finite-rerun/correctness limits. The skill didn't edit the fixture.
This is one educational smoke test, not a guarantee of agent behavior across
repositories. See sanitized saved sessions under `media/evidence/agents/`.

## Media and launch checks

The rendered MP4 is 20.000 seconds, 1920×1080, 30 fps, H.264/yuv420p with moov before
mdat (fast-start). The actual file, poster, SRT and render-validation JSON exist.
Extracted beginning/transition/ending frames were visually inspected: no clipping,
blank frames or incorrect statuses. Video is labeled as an edited real-CLI replay.

The X file is 261 characters including its trailing newline and literal URL.
The LinkedIn file is 178 whitespace-delimited words. Automated checks enforce the
limits and local README/skill/media links, as well as retained report/video hashes.
Neither social posts nor a public release have been published by this task.

The GitHub Actions workflow is configured to run tests/demo on Python 3.11 with
pytest 8.3.5 and Python 3.13 with pytest 9.x. Local success alone does not establish
remote CI status. Final test totals and fresh-checkout observations follow.


## Final local verification

- Python 3.11.14 / pytest 9.1.1: **53 passed** (25.28 seconds).
- Python 3.11.14 / pytest 8.3.5: **53 passed** (26.45 seconds).
- Fresh temporary clone of commit `9d13a62`: all 12 README runtime/demo/install
  commands returned 0, including **53 tests passed** (30.10 seconds) in the newly
  created environment. Its `python3` was Python 3.14.3. User install commands used
  an alternate temporary home; real global directories were untouched.
- The final independent demo repeat again observed NOT_CAUGHT and CAUGHT, two runs
  per side. Final live Claude report and demo record the same helper source hashes.
- The skill frontmatter validator passed. X length: 261 characters including final
  newline; LinkedIn length: 178 words. All checked relative links resolve.

Reproduce the fresh check with:

```bash
.venv/bin/python scripts/verify_fresh.py --out artifacts/fresh-local-new
```

This clones the committed local repository, then executes the README commands in
that fresh checkout. `--remote` selects the literal GitHub URL after a successful
push. [Saved local clone commands and outputs](evidence/fresh-local/report.json).
A fresh clone removes files/indices/settings created during validation when its
owned temporary directory is cleaned up.


## Published clone and remote CI

The initial implementation commit `9d13a62` was successfully pushed to `main` using
already-authorized SSH access. HTTPS without a credential helper failed; using the
existing OAuth credential then failed because it lacked the `workflow` scope.
No token scopes, global Git identity, agent settings, or permissions were changed.
The authorized SSH push included the workflow and never used force-push.

```bash
git -c core.sshCommand='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes' push git@github.com:grishahq/prove-fix.git main:main
.venv/bin/python scripts/verify_fresh.py --remote --out artifacts/fresh-remote
```

The fresh **GitHub** clone also passed all 12 README runtime/demo/install commands,
including **53 tests**. [Exact published-clone commands and outputs](evidence/fresh-remote/report.json).

[GitHub Actions run for `9d13a62`](https://github.com/grishahq/prove-fix/actions/runs/36530903573)
completed successfully. Python 3.11 / pytest 8.3.5: **53 passed** in 19.64 seconds;
Python 3.13 / pytest 9.x: **53 passed** in 23.57 seconds. Both fresh CI demos observed
NOT_CAUGHT and CAUGHT with two independent reruns per side. These are observed
remote results, separate from local verification. A subsequent documentation/media
validation commit preserves the same checker and demo source.
