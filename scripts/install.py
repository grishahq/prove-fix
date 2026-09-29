#!/usr/bin/env python3
"""Copy one self-contained skill, adapting only agent-specific metadata."""
import argparse
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parents[1] / "skills" / "prove-fix"


def install(agent, root, dry_run=False):
    destination = root.absolute() / (".claude" if agent == "claude" else ".agents") / "skills" / "prove-fix"
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Refusing to overwrite {destination}. Move or remove that skill explicitly first.")
    if any(p.is_symlink() for p in (destination.parent, *destination.parents)):
        raise ValueError("Refusing installation through a symlinked destination parent.")
    if dry_run:
        print(f"Would install {agent}: {destination}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve exclusively; cleanup only the directory this invocation owns.
    destination.mkdir()
    try:
        for file in sorted(SOURCE.rglob("*")):
            if file.is_symlink():
                raise ValueError("Skill source contains a symlink.")
            if not file.is_file() or "__pycache__" in file.parts or file.suffix == ".pyc":
                continue
            target = destination / file.relative_to(SOURCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
        if agent == "claude":
            entry = destination / "SKILL.md"
            text = entry.read_text(encoding="utf-8")
            text = text.replace("\n---\n", "\ndisable-model-invocation: true\n---\n", 1)
            entry.write_text(text, encoding="utf-8")
    except BaseException:
        shutil.rmtree(destination)
        raise
    print(f"Installed {agent}: {destination}")
    print("Invoke /prove-fix in Claude Code or $prove-fix in Codex.")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=["claude", "codex"], required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project", type=Path, help="Project root for project-local installation")
    scope.add_argument("--user", action="store_true", help="Install for the current user")
    parser.add_argument("--home", type=Path, help="Alternate home for isolated installation tests (requires --user)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.home and not args.user:
        parser.error("--home requires --user")
    root = args.project if args.project is not None else (args.home or Path.home())
    try:
        install(args.agent, root, args.dry_run)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
