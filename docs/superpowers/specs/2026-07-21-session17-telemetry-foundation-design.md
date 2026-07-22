# Session 17 — Telemetry Foundation (design)

**Date:** 2026-07-21 · **Approved by:** Mike (conversation, 2026-07-21)
**Goal / success criterion:** one telemetry database, one source of truth, that both
Piece 4 (per-CI-run GitHub reports) and Piece 5 (interactive workstation drift
dashboard) can build on without either reading stale or incomplete data.

## Problem

`ci.yml` has pointed every CI job (stage-2/3/4/5) at
`FLEET_DB=/home/mike/fleet-ci-data/fleet_runs.db` (a path outside the repo, chosen
because the self-hosted runner's checkout is ephemeral) since Session 12 (`cf88a31`).
Every tool's own default — used whenever `FLEET_DB` is unset, which includes
`streamlit run dashboard/app.py` exactly as documented in the README Quickstart —
falls back to the in-repo `reports/fleet_runs.db`. These are two different SQLite
files. Nearly all real fleet history (every Gazebo/HIL run CI has ever recorded) has
been landing in the CI-side file; the dashboard and local report generation have only
ever seen whatever ad hoc local runs happened to hit the in-repo default. CLAUDE.md's
claim that `reports/fleet_runs.db` is "the single source all tools read/write" is only
true when `FLEET_DB` is unset — which CI never does.

The CI runner and the local dev environment are the same physical machine (self-hosted
runner registered on `mikeubuntu`), so this is not a multi-host sync problem — it's
two default paths on one box that disagree.

## Decisions

1. **One database, always.** Local dev, manual HIL days, and every CI job write to and
   read from the same persistent file. No promotion/sync step between a "local" and a
   "CI" store.
2. **SQLite stays.** Rejected moving to Postgres: the DB is ~28KB after 17+ sessions
   (a few telemetry rows per run, sequential appends), everything runs on one machine
   with one filesystem, and there is no concurrent multi-host write case. Postgres
   would add an operational service for zero functional gain at this scale. The one
   real concurrency wrinkle — dashboard holding a read connection while a CI job
   writes — is solved by WAL mode, not a different database engine.
3. **Historical local data is discarded, not merged.** The CI-side DB already holds
   nearly all real history. The local `reports/fleet_runs.db`'s rows are ad hoc by
   definition — Mike confirmed ad hoc runs don't need to be recoverable later, so no
   migration/merge script is built.
4. **Retention/cleanup of local disk artifacts (ROS logs, photos, failure bags) is
   explicitly out of scope here** — it's a known, separately-tracked gap (see
   CLAUDE.md's `~/.ros/log` retention gotcha), not solved by this piece. Only the
   *database* location problem is Foundation's job.
5. **Log/evidence discoverability on GitHub is Piece 4's job, not Foundation's.**
   Piece 3's logging mechanics (rosbag-on-failure, `pull_ros_logs.py`, failure
   taxonomy) are already built and stay untouched — Foundation doesn't add new
   logging. Making it obvious *on GitHub* where a run's logs/photos/bags landed is a
   Piece 4 report-surfacing requirement, carried forward into that piece's design.

## Design

### 1. Canonical location & single source of truth

- `tools/telemetry_logger.py` — which already owns the schema (column registry) —
  becomes the single owner of the path too:
  ```python
  DB_PATH = os.environ.get("FLEET_DB", os.path.expanduser("~/fleet-ci-data/fleet_runs.db"))
  ```
- The other five files that currently duplicate the same default literal
  (`baseline_monitor.py`, `validate_telemetry.py`, `agentic_loop.py`,
  `generate_test_report.py`, `dashboard/app.py`) import `DB_PATH` from
  `telemetry_logger` instead of redeclaring it.
- `os.path.expanduser("~/...")` resolves to the exact file CI has already been
  populating on this machine (`$HOME` = `/home/mike`) — so switching the default
  requires **no data migration**; every tool is immediately pointed at the real
  accumulated history the moment this ships. It's also not a personal path hardcoded
  into shipped source — a future clone on another machine gets that machine's own
  `~/fleet-ci-data/`.
- `FLEET_DB` env var override is preserved (tests and deliberate one-offs still need
  it).
- WAL mode (`PRAGMA journal_mode=WAL;`) is enabled **once**, directly against the real
  file, as part of cutover — it's stored in the SQLite file header and persists across
  every future connection/process, so no per-`connect()`-call changes are needed
  anywhere in the codebase.
- `ci.yml`'s now-redundant `FLEET_DB: /home/mike/fleet-ci-data/fleet_runs.db` lines
  (stage-2/3/4/5) are removed — one less place declaring the path.

### 2. Ad hoc opt-out

- New env var `FLEET_TELEMETRY` (default `"on"`). `telemetry_logger.log_run()` checks
  it first; if `"off"`, returns immediately without opening a connection or writing
  anything.
- Single choke point: every write path (`NavRunner`, `MissionRunner`,
  `mission2_day.py`'s judge) already goes through `log_run()`, so nothing else needs
  to change.
- No scratch DB, no `:memory:` special-casing — a true no-op, matching that ad hoc
  runs don't need to be reviewable afterward.

### 3. Cutover & documentation

- Centralize `DB_PATH` in `telemetry_logger.py`; update the 5 importing files.
- One-time `PRAGMA journal_mode=WAL;` against the real `~/fleet-ci-data/fleet_runs.db`.
- Add the `FLEET_TELEMETRY=off` check in `log_run()`.
- Remove the redundant `FLEET_DB:` lines from `ci.yml`.
- Delete the stale local `reports/fleet_runs.db` and the already-dead
  `reports/history/` directory, so nothing points at either by accident.
- Update CLAUDE.md: correct the inaccurate "single source" claim, document the real
  canonical path + its derivation, the `FLEET_TELEMETRY=off` flag, and the WAL-mode
  note. Check README for any `FLEET_DB`/dashboard instructions needing the same fix.

## Testing / verification

- Full local `pytest` run after the change (existing tests already override `FLEET_DB`
  via env var / `tmp_path` fixtures for isolation — unaffected by the default change).
- One real local invocation each of `dashboard/app.py`, `generate_test_report.py`, and
  `baseline_monitor.py` against the consolidated DB, confirming CI-originated rows
  (`hil_jetson`, Gazebo sim runs) are now actually visible — the concrete proof this
  fixed the problem rather than just moved it.

## Out of scope (explicitly, for this piece)

- Local disk retention/cleanup for ROS logs, photos, failure bags (separate known gap).
- Piece 4: per-CI-run report generation, GitHub landing, artifact retention policy,
  log/evidence discoverability on GitHub.
- Piece 5: interactive drift dashboard, AI-loop big-picture involvement.
