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
