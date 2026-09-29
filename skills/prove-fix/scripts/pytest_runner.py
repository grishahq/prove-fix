"""Private pytest subprocess entry point. No dependency on the development repo."""
import argparse
import ast
import json
import os
from pathlib import Path
import sys


def relative(path, root):
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return None


class Evidence:
    def __init__(self, root, original, implementations):
        self.root = root
        self.original = original
        self.implementations = implementations
        self.data = {"schema": 1, "collected": [], "collection_errors": [],
                     "events": [], "internal_errors": [], "import_violations": [],
                     "loaded_implementation": []}

    def pytest_collection_finish(self, session):
        self.data["collected"] = [item.nodeid for item in session.items]

    def pytest_collectreport(self, report):
        if report.failed:
            self.data["collection_errors"].append(str(report.longrepr))
        elif report.skipped:
            self.data["collection_errors"].append("Collection skipped: " + report.nodeid)

    def pytest_internalerror(self, excrepr, excinfo):
        self.data["internal_errors"].append(str(excrepr))

    def pytest_runtest_makereport(self, item, call):
        event = {"nodeid": item.nodeid, "phase": call.when,
                 "outcome": "passed", "exception": None, "assertions": [],
                 "assertion_origin": None, "failure": None}
        if call.excinfo:
            event["exception"] = call.excinfo.type.__name__
            event["outcome"] = "failed"
            event["failure"] = str(call.excinfo.value)
            if call.excinfo.type is AssertionError:
                for entry in call.excinfo.traceback:
                    path = relative(entry.path, self.root)
                    if path is None:
                        continue
                    line = entry.lineno + 1
                    try:
                        source = (self.root / path).read_text(encoding="utf-8")
                        for node in ast.walk(ast.parse(source)):
                            if isinstance(node, ast.Assert) and node.lineno <= line <= node.end_lineno:
                                assertion = {"path": path, "line": node.lineno,
                                    "source": ast.get_source_segment(source, node)}
                                event["assertions"].append(assertion)
                                if entry is call.excinfo.traceback[-1]:
                                    event["assertion_origin"] = assertion
                    except (OSError, SyntaxError, UnicodeError):
                        pass
        self.data["events"].append(event)

    def pytest_runtest_logreport(self, report):
        # Actual pytest outcomes include skip/xfail/xpass, unlike call.excinfo alone.
        event = next(e for e in reversed(self.data["events"])
                     if e["nodeid"] == report.nodeid and e["phase"] == report.when)
        event["outcome"] = report.outcome
        event["xfail"] = hasattr(report, "wasxfail")
        if report.failed:
            event["traceback"] = str(report.longrepr)

    def finish(self):
        loaded = set()
        for name, module in list(sys.modules.items()):
            origin = getattr(module, "__file__", None)
            if not isinstance(origin, str):
                continue
            local = relative(origin, self.root)
            if local in self.implementations:
                loaded.add(local)
            if relative(origin, self.original) is not None:
                self.data["import_violations"].append({"module": name,
                    "reason": "Imported from caller checkout", "origin": origin})
        self.data["loaded_implementation"] = sorted(loaded)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--original", required=True)
    parser.add_argument("--implementation", action="append", required=True)
    parser.add_argument("--node", required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    # -I ignores inherited PYTHONPATH. The snapshot is the first import location.
    sys.path.insert(0, str(root))
    import pytest
    evidence = Evidence(root, Path(args.original).resolve(), args.implementation)
    code = pytest.main([args.node, "-q", "--tb=short", "--color=no",
                        "-p", "no:cacheprovider"], plugins=[evidence])
    evidence.finish()
    evidence.data["pytest_version"] = pytest.__version__
    evidence.data["exit_code"] = int(code)
    Path(args.result).write_text(json.dumps(evidence.data, indent=2) + "\n", encoding="utf-8")
    return int(code)


if __name__ == "__main__":
    sys.exit(main())
