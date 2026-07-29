"""Single declared source for which scenarios belong to which CI report stage
(Session 17 Piece 6). Backed by config/pipeline_matrix.yaml — see that file's
header for the consumers and why the mission2_day.py execution sequence itself
stays hardcoded Python while only the scenario name list is declared here.
"""

import pathlib

import yaml

DEFAULT_PATH = pathlib.Path(__file__).resolve().parent.parent / "config" / "pipeline_matrix.yaml"


class UnknownStageError(ValueError):
    """Raised when a stage name isn't declared in the pipeline matrix config."""


def load_stage(stage, path=DEFAULT_PATH):
    """Return (runner_type, scenarios) declared for `stage` ('sim' or 'hil')."""
    with open(path) as f:
        matrix = yaml.safe_load(f)
    if stage not in matrix:
        raise UnknownStageError(f"unknown pipeline stage {stage!r}; known: {sorted(matrix)}")
    entry = matrix[stage]
    return entry["runner_type"], list(entry["scenarios"])


def list_stages(path=DEFAULT_PATH):
    """All declared stage names (e.g. ['hil', 'real', 'sim']), sorted."""
    with open(path) as f:
        matrix = yaml.safe_load(f)
    return sorted(matrix)
