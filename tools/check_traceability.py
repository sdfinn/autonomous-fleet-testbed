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
