#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "assurance" / "requirements-to-tests.json"
WORKFLOWS = ROOT / ".github" / "workflows"
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
USES = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
TOP_LEVEL_PR_TRIGGER = re.compile(r"(?m)^  pull_request(?:_target)?:")
TRUSTED_PUSH_HEADER = "on:\n  push:\n  workflow_dispatch:\n"
SELF_HOSTED_RUNNER = "runs-on: [self-hosted, windows, x64, amep]"


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def verify_requirements() -> tuple[int, list[str]]:
    failures: list[str] = []
    data = json.loads(MATRIX.read_text(encoding="utf-8"))
    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        return 0, ["requirements matrix must contain a non-empty requirements list"]

    seen_ids: set[str] = set()
    cache: dict[Path, set[str]] = {}
    for entry in requirements:
        if not isinstance(entry, dict):
            failures.append("requirements entries must be objects")
            continue
        requirement_id = str(entry.get("id", "")).strip()
        statement = str(entry.get("statement", "")).strip()
        claim_boundary = str(entry.get("claim_boundary", "")).strip()
        tests = entry.get("tests")

        if not requirement_id:
            failures.append("requirement missing id")
        elif requirement_id in seen_ids:
            failures.append(f"duplicate requirement id: {requirement_id}")
        else:
            seen_ids.add(requirement_id)
        if not statement:
            failures.append(f"{requirement_id or '<unknown>'}: missing statement")
        if not claim_boundary:
            failures.append(f"{requirement_id or '<unknown>'}: missing claim_boundary")
        if not isinstance(tests, list) or not tests:
            failures.append(f"{requirement_id or '<unknown>'}: no executable tests declared")
            continue

        for target in tests:
            if not isinstance(target, str) or "::" not in target:
                failures.append(f"{requirement_id}: invalid test target {target!r}")
                continue
            relative, function = target.split("::", 1)
            path = ROOT / relative
            if not path.is_file():
                failures.append(f"{requirement_id}: missing test file {relative}")
                continue
            if path not in cache:
                cache[path] = _test_functions(path)
            if function not in cache[path]:
                failures.append(
                    f"{requirement_id}: missing test function {relative}::{function}"
                )

    return len(requirements), failures


def verify_workflow_pins() -> tuple[int, list[str]]:
    failures: list[str] = []
    uses_count = 0
    workflow_paths = sorted(WORKFLOWS.glob("*.yml")) + sorted(
        WORKFLOWS.glob("*.yaml")
    )
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        for action in USES.findall(text):
            if action.startswith("./"):
                continue
            uses_count += 1
            if "@" not in action:
                failures.append(f"{path.relative_to(ROOT)}: unversioned action {action}")
                continue
            _, ref = action.rsplit("@", 1)
            if not FULL_SHA.fullmatch(ref):
                failures.append(
                    f"{path.relative_to(ROOT)}: action is not pinned to a full commit SHA: {action}"
                )
    return uses_count, failures


def verify_environment_capture() -> list[str]:
    failures: list[str] = []
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    if "pip freeze --all" not in ci:
        failures.append("ci.yml does not capture the fully resolved Python environment")
    if ".ci-environment.txt" not in ci:
        failures.append("ci.yml does not persist the resolved environment evidence")
    return failures


def verify_self_hosted_runner_boundary() -> list[str]:
    failures: list[str] = []
    workflow_paths = sorted(WORKFLOWS.glob("*.yml")) + sorted(
        WORKFLOWS.glob("*.yaml")
    )
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        if "self-hosted" in text and TOP_LEVEL_PR_TRIGGER.search(text):
            failures.append(
                f"{path.relative_to(ROOT)}: self-hosted workflow must not run on "
                "pull_request or pull_request_target"
            )

    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    if TRUSTED_PUSH_HEADER not in ci:
        failures.append(
            "ci.yml must validate trusted repository branches on push and must not "
            "scope self-hosted CI to main only"
        )
    if SELF_HOSTED_RUNNER not in ci:
        failures.append(
            "ci.yml no longer targets the designated AMEP Windows self-hosted runner"
        )
    return failures


def main() -> None:
    failures: list[str] = []
    requirement_count, requirement_failures = verify_requirements()
    uses_count, workflow_failures = verify_workflow_pins()
    failures.extend(requirement_failures)
    failures.extend(workflow_failures)
    failures.extend(verify_environment_capture())
    failures.extend(verify_self_hosted_runner_boundary())

    result = {
        "status": "PASS" if not failures else "FAIL",
        "requirements_checked": requirement_count,
        "external_actions_checked": uses_count,
        "matrix": str(MATRIX.relative_to(ROOT)),
        "failures": failures,
        "scope": (
            "Executable software-assurance traceability and CI change-control checks only; "
            "not certification or operational maritime evidence."
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ASSURANCE CONTRACT VERIFICATION FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
