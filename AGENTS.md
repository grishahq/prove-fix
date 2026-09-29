# Repository development

- Keep this an inspectable Python 3.11+ v0.1. All repository prose, messages, and comments are English.
- Maintain one checking implementation in `skills/prove-fix/scripts/`; installers copy it with metadata adapters only.
- Preserve the invariant: identical test/fixture/config/dependency inputs; reverse only the explicit allowed implementation patch.
- Caller Git operations in the checker must be read-only. Never stage, commit, reset, checkout, stash, or clean its repository.
- Structured pytest assertion evidence is required for CAUGHT. Setup/import/skip/timeout or uncertain attribution is INCONCLUSIVE.
- Temporary copies are not a security sandbox. Do not add dependency installation, credential copying, permission bypasses, hooks, telemetry, or services.
- Run `.venv/bin/python -m pytest -q` and `.venv/bin/python scripts/demo.py --out artifacts/new-demo-directory` after checker changes.
- Generated demo statuses must come from saved executions. Regenerate evidence before rendering video; see `media/README.md`.
- Keep media dependencies separate. No font binaries, private agent logs, environments, or large intermediates in Git.
- Update `docs/validation.md` honestly. Packaging tests and live agent-session tests are different. Never claim an unobserved CI result.
