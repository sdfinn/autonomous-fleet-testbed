# Architectural Review — 2026-06-27

Reviewed by: Claude Opus 4.8 after Session 06 completion, before Session 07 begins.

**Scope:** All files in `tools/`, `tests/`, `dashboard/`, `config/`, `requirements/`, `.github/workflows/`.

---

## What's In Good Shape

- `check_traceability.py` — clean design, well-tested (34 tests), good exit-code contract
- `baseline_monitor.py` — solid sigma-threshold logic, correct PASS-only baseline window
- `test_baseline.py` — good coverage of drift detection edge cases
- CI pipeline structure — stage ordering and `continue-on-error` placement are correct
- `drift_config.yaml` schema — the right data-driven design, just not wired up yet

---

## P0 — Fix Before Session 07 (Broken Today)

### 1. `validate_telemetry.py` — TypeError on import (pandera 0.32 API change)
`DataFrameModel.to_schema(coerce=True)` crashes at module load — pandera 0.32 removed the `coerce`
keyword from `to_schema()`. The frozen venv has pandera 0.32, pandas 3.0, numpy 2.5, which are
all newer than the Isaac Sim migration code was written against.
**Fix:** Remove `coerce=True` from the `to_schema()` call and validate coercion at the call
site instead, or pass `coerce=True` to the validator rather than the schema builder.

### 2. `ai_test_generator.py` — Error path returns wrong type
`generate_scenarios()` returns `[]` on JSON parse failure, but the caller unpacks it as `(scenarios, usage)`.
This raises `ValueError: not enough values to unpack` and crashes the pipeline.
**Fix:** Return `([], None)` on all failure paths.

### 3. `ai_test_generator.py` — Queries Isaac Sim schema columns
`query_recent_runs()` selects `speed_avg`, `battery_percent_start`, `battery_percent_end`, `obstacle_count` —
none of which exist in the current fleet schema. Claude receives all-NULL context.
**Fix:** Update query to current schema columns: `nav_success_rate`, `mean_position_error`, `collision_rate`, `odom_hz_mean`, `lidar_hz_mean`, `camera_hz_mean`.

### 4. `traceability.yaml` — Function names don't match actual test functions
Stage 0 will permanently report these requirements as "missing" even when Session 09 tests are written:

| Requirement | traceability.yaml expects | Actual function |
|---|---|---|
| BR-04 | `test_odom_hz` | `test_odom_message_schema` |
| SC-04 | `test_lidar_hz` | `test_scan_message_schema` |
| SC-05 | `test_camera_hz` | `test_camera_image_schema` |
| BR-07 | `test_nav_success_rate_drift` | `test_drift_detected_above_threshold` |

**Fix:** Either rename the test functions to match traceability.yaml, or update traceability.yaml to match the actual function names. Recommend renaming the test functions — more descriptive names.

---

## P1 — Fix Before Session 09 (Will Break First Real Test Run)

### 5. `test_ros2_contracts.py` — PointCloud2 vs LaserScan type mismatch
The scan test expects `sensor_msgs/PointCloud2` (Isaac Sim artifact). Gazebo Harmonic's standard
lidar sensor publishes `sensor_msgs/LaserScan`. Also: module docstring says "Isaac Sim must be
running" — leftover migration debris.
**Fix:** Change scan test to subscribe to `LaserScan`, update assertions accordingly.

### 6. `telemetry_logger.py` — `ai_scenarios` table never created
`TelemetryLogger.mark_scenario_complete()` and `ai_test_generator.store_scenarios()` both write
to `ai_scenarios`, but `init_db()` never creates it. First AI generator run crashes.
**Fix:** Add `CREATE TABLE IF NOT EXISTS ai_scenarios` to `init_db()`.

### 7. Two competing DB path env vars
- `telemetry_logger.py` reads `FLEET_DB` → `reports/fleet_runs.db`
- `validate_telemetry.py` reads `ROBOT_DB_PATH` → `robot_test_results.db`
- `ai_test_generator.py` hardcodes `"robot_test_results.db"` (no env var)

Validation silently validates the wrong (empty/nonexistent) database.
**Fix:** Standardize all tools on `FLEET_DB` → `reports/fleet_runs.db`.

### 8. `drift_config.yaml` is not read by `baseline_monitor.py`
The design principle is "thresholds are data, not code." `SIGMA_THRESHOLD = 2.0` is hardcoded
in Python. The YAML's sigma levels, per-metric directions, threshold_fail values, and
`post_merge_sensitivity` block are all ignored.
**Fix:** Add a `load_drift_config()` function and wire it into `check_run()`. This is the core
of the "data-driven" claim.

---

## P2 — Design Debt (Address Before R2)

| # | Issue | Location |
|---|---|---|
| 9 | SQLite connections never use context managers — leak on exceptions | All DB tools |
| 10 | Dashboard Tab 5 opens raw connection outside `@st.cache_data` | `dashboard/app.py:237` |
| 11 | Robot type filter hardcoded as `["All", "jetson_ugv_pt"]` | `dashboard/app.py:45` |
| 12 | No `git_sha` column in telemetry DB — can't trace drift to a commit | `telemetry_logger.py` |
| 13 | `load_traceability()` KeyError on malformed YAML outside try block | `check_traceability.py:48` |
| 14 | `generate_test_report.py` crashes with empty database | `generate_test_report.py:43` |

---

## P3 — Scalability Notes (R2+ Planning)

- **SQLite → PostgreSQL:** Single-writer lock will cause "database is locked" errors when R2 adds concurrent robot writers. Architectural migration point, not an immediate fix.
- **AI context is schema-coupled:** `ai_test_generator.py` hardcodes column names for Claude context. As the schema evolves, AI context degrades silently. Consider a config-driven "context columns" list.
- **Orphan noise:** `tests/test_check_traceability.py` has 34 functions that will appear as orphan warnings in Stage 0 output until mapped or excluded. Not a bug, but noisy.

---

## One Design Principle to Enforce Now

`baseline_monitor.py` and `drift_config.yaml` currently duplicate the metric list. The YAML
has `direction`, `threshold_fail`, and `requirement` fields per metric; Python has its own
`METRICS` dict and `HARD_THRESHOLD_METRICS` set. These will diverge. When `baseline_monitor.py`
reads from `drift_config.yaml` (P1 fix #8), delete the Python dicts and make the YAML the
single source of truth.
