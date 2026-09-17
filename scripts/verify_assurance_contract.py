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


def _uses_self_hosted_runner(text: str) -> bool:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("runs-on:"):
            continue
        indent = len(line) - len(stripped)
        rhs = stripped.split(":", 1)[1].strip()
        if "self-hosted" in rhs:
            return True
        if rhs:
            continue
        for following in lines[index + 1 :]:
            following_stripped = following.lstrip()
            following_indent = len(following) - len(following_stripped)
            if following_stripped and following_indent <= indent:
                break
            if "self-hosted" in following_stripped:
                return True
    return False


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
        if _uses_self_hosted_runner(text) and TOP_LEVEL_PR_TRIGGER.search(text):
            failures.append(
                f"{path.relative_to(ROOT)}: workflow targeting a self-hosted runner "
                "must not run on pull_request or pull_request_target"
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

    pr_validation = WORKFLOWS / "pr-validation.yml"
    if not pr_validation.is_file():
        failures.append("missing GitHub-hosted public PR validation workflow")
    else:
        text = pr_validation.read_text(encoding="utf-8")
        if not TOP_LEVEL_PR_TRIGGER.search(text):
            failures.append("pr-validation.yml must run for pull_request events")
        if _uses_self_hosted_runner(text):
            failures.append("pr-validation.yml must never target a self-hosted runner")
        if "runs-on: windows-latest" not in text:
            failures.append("pr-validation.yml must use GitHub-hosted Windows")
        if "name: Windows PR validation" not in text:
            failures.append("pr-validation.yml missing Windows PR validation check")
    return failures


def main() -> None:
    failures: list[str] = []
    requirement_count, requirement_failures = verify_requirements()
    uses_count, workflow_failures = verify_workflow_pins()
    runner_boundary_failures = verify_self_hosted_runner_boundary()
    failures.extend(requirement_failures)
    failures.extend(workflow_failures)
    failures.extend(verify_environment_capture())
    failures.extend(runner_boundary_failures)

    result = {
        "status": "PASS" if not failures else "FAIL",
        "requirements_checked": requirement_count,
        "external_actions_checked": uses_count,
        "self_hosted_runner_boundary": (
            "PASS" if not runner_boundary_failures else "FAIL"
        ),
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
