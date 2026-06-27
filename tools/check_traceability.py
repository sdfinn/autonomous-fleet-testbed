# Copyright 2026 Mike. Licensed under MIT.
"""Stage 0 CI gate: every requirement ID must map to a test that exists."""
import argparse
import ast
import json
import logging
import sys
from pathlib import Path
from typing import NamedTuple

import yaml

log = logging.getLogger(__name__)


class Requirement(NamedTuple):
    id: str
    description: str
    tests: list


class Result(NamedTuple):
    covered: list
    missing: list
    skipped: list
    orphans: list


def setup_logging(debug: bool) -> None:
    """Configure logging: DEBUG to stderr when --debug, else WARNING only."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def load_traceability(path: Path) -> list:
    """Load requirements/traceability.yaml. Calls sys.exit(2) on any error."""
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        log.error("Cannot load %s: %s", path, exc)
        sys.exit(2)
    requirements = []
    for req in data.get("requirements", []):
        requirements.append(Requirement(
            id=req["id"],
            description=req.get("description", ""),
            tests=req.get("tests", []),
        ))
    log.debug("Loaded %d requirements from %s", len(requirements), path)
    return requirements


def load_profile(path: Path) -> set:
    """Load skip_requirements list from robot profile YAML. sys.exit(2) on error."""
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        log.error("Cannot load profile %s: %s", path, exc)
        sys.exit(2)
    skip = set(data.get("skip_requirements", []))
    log.debug("Profile %s: skipping %s", path.stem, skip or "nothing")
    return skip


def scan_tests(test_dir: Path) -> set:
    """Return all 'tests/module.py::func_name' IDs found in test_dir.

    IDs are relative to test_dir.parent so they match traceability.yaml entries
    (e.g. test_dir=tests/ → ID starts with 'tests/').
    """
    found = set()
    for test_file in sorted(test_dir.rglob("test_*.py")):
        log.debug("Scanning %s", test_file)
        try:
            tree = ast.parse(test_file.read_text())
        except SyntaxError as exc:
            log.warning("Skipping %s — syntax error: %s", test_file, exc)
            continue
        rel = test_file.relative_to(test_dir.parent)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                tid = f"{rel}::{node.name}"
                found.add(tid)
                log.debug("  found %s", tid)
    log.debug("Total test functions found: %d", len(found))
    return found


def find_orphans(existing: set, all_mapped: set) -> list:
    """Return sorted list of test IDs that exist but are not mapped to any requirement."""
    return sorted(existing - all_mapped)


def check_coverage(requirements: list, existing: set, skip_ids: set) -> Result:
    """Classify each requirement as covered, missing, or skipped.

    A requirement is covered when ALL its listed tests exist in existing.
    Skipped requirements (per robot profile) count neither covered nor missing.
    Orphans are tests that exist but are not referenced by any non-skipped requirement.
    """
    covered, missing, skipped = [], [], []
    all_mapped: set = set()

    for req in requirements:
        if req.id in skip_ids:
            skipped.append(req)
            log.debug("SKIP %s (robot profile)", req.id)
            continue
        req_test_set = set(req.tests)
        all_mapped.update(req_test_set)
        if req_test_set.issubset(existing):
            covered.append(req)
            log.debug("OK   %s", req.id)
        else:
            missing.append(req)
            log.debug("MISS %s — absent: %s", req.id, req_test_set - existing)

    orphans = find_orphans(existing, all_mapped)
    if orphans:
        log.debug("Orphan tests found: %s", orphans)
    return Result(covered=covered, missing=missing, skipped=skipped, orphans=orphans)


def _print_summary(result: Result) -> None:
    total = len(result.covered) + len(result.missing) + len(result.skipped)
    parts = [f"{len(result.covered)}/{total} requirements covered"]
    if result.skipped:
        parts.append(f"{len(result.skipped)} skipped by profile")
    if result.orphans:
        parts.append(f"{len(result.orphans)} orphan test(s)")
    print("  ".join(parts))


def format_rich(result: Result, profile_name) -> None:
    """Human-readable output with requirement text inline."""
    if profile_name:
        print(f"Profile: {profile_name}")
    print()
    for req in result.covered:
        print(f"  ✓  {req.id}  [{req.description}]")
        for test in req.tests:
            print(f"       {test}")
    for req in result.skipped:
        print(f"  –  {req.id}  [{req.description}]  (skipped by profile)")
    for req in result.missing:
        print(f"  ✗  {req.id}  [{req.description}]")
        for test in req.tests:
            print(f"       MISSING: {test}")
    if result.orphans:
        print()
        print("  Orphan tests (exist but not mapped to any requirement):")
        for t in result.orphans:
            print(f"    ⚠  {t}")
    print()
    _print_summary(result)


def format_quiet(result: Result) -> None:
    """Terse output — IDs and status only."""
    for req in result.covered:
        print(f"OK    {req.id}")
    for req in result.skipped:
        print(f"SKIP  {req.id}")
    for req in result.missing:
        print(f"FAIL  {req.id}")
    for t in result.orphans:
        print(f"WARN  ORPHAN {t}")
    _print_summary(result)


def format_json(result: Result, git_sha, profile_name) -> str:
    """Machine-readable JSON for stdout redirect and CI artifact upload."""
    import os
    sha = git_sha or os.environ.get("GITHUB_SHA", "unknown")

    def _req_dict(req: Requirement, status: str) -> dict:
        return {
            "id": req.id,
            "description": req.description,
            "status": status,
            "tests": req.tests,
        }

    return json.dumps({
        "git_sha": sha,
        "profile": profile_name,
        "summary": {
            "total": len(result.covered) + len(result.missing) + len(result.skipped),
            "covered": len(result.covered),
            "missing": len(result.missing),
            "skipped": len(result.skipped),
            "orphans": len(result.orphans),
        },
        "requirements": (
            [_req_dict(r, "covered") for r in result.covered]
            + [_req_dict(r, "missing") for r in result.missing]
            + [_req_dict(r, "skipped") for r in result.skipped]
        ),
        "orphans": result.orphans,
    }, indent=2)
