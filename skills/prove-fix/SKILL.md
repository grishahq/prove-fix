---
name: prove-fix
description: Check whether one pytest regression test notices a narrowly selected implementation fix being reversed. Use after a Python bug fix when explicitly requested.
---

# prove-fix

Your test is green. Put the bug back.

Read [references.md](references.md) for the helper interface, supported patch format,
result rules, and copying exclusions. Resolve `scripts/check.py` relative to this
loaded SKILL.md, never relative to the current project or a development checkout.
Claude Code can also use `${CLAUDE_SKILL_DIR}/scripts/check.py`.

## Select and explain

Inspect the user's task, the current working-tree diff (including staged changes),
and relevant tests. Select one specific regression test and the smallest
implementation-only forward patch containing the intended fix. Keep the new test,
fixtures, dependencies, and configuration in both snapshots. Never substitute a
whole old checkout. Do not stage, commit, reset, checkout, stash, or clean the caller.

Explain which change will be reversed, what bug that reintroduces, the chosen
pytest node ID, and the actual test `assert` source line expected to detect it.
Include every new/untracked test or fixture needed using `--include FILE`.
Protect test, fixture, and configuration paths using `--protect PATH`.
If the patch cannot be isolated within the supported format, stop with the exact
reason and the smaller patch or environment prerequisite needed. Do not guess.

## Execute and review

Run the bundled helper only for trusted code whose execution the user authorized,
using an existing Python environment with pytest and required project dependencies.
The helper does not install anything. Respect the host's existing permissions;
invoking this skill grants no extra tools or execution rights. Temporary copies
are NOT a security sandbox. Review selected files for credentials and use
`--exclude` for sensitive files with names outside the documented exclusion rules.

Use the same test in both snapshots. A different test is a separate comparison;
label the switch clearly. Do not rewrite tests to produce a desired result.

Inspect `report.json`, the structured pytest events, and the captured logs. Before
reporting the target bug as detected, confirm the expected AssertionError is
actually caused by the reversed fix rather than a fixture or unrelated behavior.
The helper's location check cannot establish semantic attribution by itself.
If the attribution remains uncertain, report INCONCLUSIVE for agent review even
if the helper matched the caller's declared assertion.

Report observed fixed/reversed outcomes, classification, the assertion evidence,
your separate interpretation, and evidence paths. Include the limitations: finite
reruns cannot establish absence of flakiness, and neither result establishes
overall correctness. NOT_CAUGHT means this selected test passed in both versions
in these runs. CAUGHT supplies evidence for this particular regression only.
