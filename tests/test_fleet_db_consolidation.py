"""Regression guard for the Foundation piece (Session 17, 2026-07-21): DB_PATH used to
be independently redeclared — os.environ.get("FLEET_DB", "reports/fleet_runs.db") or a
os.path.join equivalent — in 6 different files, and silently drifted out of sync with
the real path CI actually wrote to. Every consumer must import DB_PATH from
tools.telemetry_logger (the single owner) instead of redeclaring its own default.

This checks source text rather than importing the modules directly: dashboard/app.py
runs Streamlit calls and a live DB read at import time, and tools/agentic_loop.py
constructs an anthropic.Anthropic() client at import time — neither is safe or
meaningful to import in a unit test just to check an import line.
"""
import pathlib

EXPECTED_IMPORTS = {
    "tools/baseline_monitor.py": "from tools.telemetry_logger import DB_PATH",
    # validate_telemetry.py combines this with its existing BASE_COLUMNS/RUNS_COLUMNS
    # import into one line — the substring below must match that exact line, not just
    # "import DB_PATH" (which never appears verbatim there).
    "tools/validate_telemetry.py":
        "from tools.telemetry_logger import BASE_COLUMNS, DB_PATH, RUNS_COLUMNS",
    "tools/agentic_loop.py": "from tools.telemetry_logger import DB_PATH as FLEET_DB",
    "tools/generate_test_report.py": "from tools.telemetry_logger import DB_PATH",
    "dashboard/app.py": "from tools.telemetry_logger import DB_PATH",
}


def test_downstream_modules_import_db_path_from_telemetry_logger():
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    for rel_path, expected_import in EXPECTED_IMPORTS.items():
        source = (repo_root / rel_path).read_text()
        assert expected_import in source, (
            f"{rel_path} should import DB_PATH from tools.telemetry_logger, "
            "not redeclare its own default"
        )
