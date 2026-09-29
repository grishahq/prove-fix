Your test is green. Put the bug back.

I built prove-fix to check a specific question after a bug fix: does the regression test notice when that fix is removed?

The educational demo uses free shipping starting at an order total of 100. The bug is `amount > 100`; the fix is `amount >= 100`. A test at 150 passes both ways. A separate boundary test at 100 passes with the fix and fails without it at the intended assertion.

prove-fix runs the same selected test in two independent snapshots, reversing only the implementation patch in the second. Tests, fixtures, and configuration stay unchanged within each comparison. It captures structured pytest evidence and asks the agent to inspect why the assertion failed.

v0.1 is deliberately small: Python, pytest, an explicit patch, Linux/macOS, and installation adapters for Claude Code and Codex. Temporary copies are not a security sandbox.

Passing both ways means this test missed the regression in these runs. Catching it supplies evidence for that regression; neither result guarantees overall correctness.

Code and the edited, reproducible demo:
https://github.com/grishahq/prove-fix
