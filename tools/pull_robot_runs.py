# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Bring the real robot's run rows from the Jetson's telemetry database to this one.

    python -m tools.pull_robot_runs [--host jetson.local] [--dry-run]

Why (2026-11-23): on a real mission the robot grades itself and writes one row per
mission part into ITS OWN database (~/fleet-ci-data/fleet_runs.db on the Jetson).
Nothing ever brought those rows here, where the dashboard, drift detection and
tools/sim_vs_real_comparison.py read: on that day the Jetson held 57 real-robot rows and
the workstation none, so Release 1's last step had nothing to compare.

What it does: reads the Jetson's rows with runner_type 'real_robot' over SSH (read
only), and inserts the ones this database does not have yet. A row is "the same row"
when scenario, timestamp and runner_type match, so running it twice adds nothing.
Columns the two databases do not share are left out. The Jetson's database is not changed.
"""
import argparse
import json
import sqlite3
import subprocess
import sys

from tools.telemetry_logger import DB_PATH, init_db

RUNNER_TYPE = 'real_robot'
KEY = ('scenario', 'timestamp', 'runner_type')
REMOTE_DB = '~/fleet-ci-data/fleet_runs.db'

# Runs on the Jetson: every real-robot row as one JSON list on stdout.
_REMOTE_DUMP = r'''
import json, os, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % os.path.expanduser("{db}"), uri=True)
c.row_factory = sqlite3.Row
print(json.dumps([dict(r) for r in c.execute(
    "select * from runs where runner_type = ? order by timestamp", ("{runner}",))]))
'''


def fetch_remote_rows(host, remote_db=REMOTE_DB, runner_type=RUNNER_TYPE, timeout_s=60):
    """The Jetson's real-robot rows as a list of dicts. Raises RuntimeError with the
    remote error text when the read fails."""
    script = _REMOTE_DUMP.format(db=remote_db, runner=runner_type)
    proc = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host, 'python3', '-'],
        input=script, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        raise RuntimeError(f'could not read {remote_db} on {host}: {proc.stderr.strip()[-300:]}')
    return json.loads(proc.stdout)


def merge_rows(conn, rows):
    """Insert the rows this database does not have yet. Returns (added, already_here,
    columns_left_out). Only columns both sides have are copied; `id` never is."""
    local_cols = {r[1] for r in conn.execute('pragma table_info(runs)')}
    added = already = 0
    left_out = set()
    for row in rows:
        if conn.execute(
                'select 1 from runs where scenario is ? and timestamp is ? and runner_type is ?',
                tuple(row.get(k) for k in KEY)).fetchone():
            already += 1
            continue
        cols = [c for c in row if c != 'id' and c in local_cols]
        left_out |= {c for c in row if c != 'id' and c not in local_cols}
        conn.execute('insert into runs (%s) values (%s)' % (
            ', '.join(cols), ', '.join('?' for _ in cols)), [row[c] for c in cols])
        added += 1
    conn.commit()
    return added, already, sorted(left_out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--host', default='jetson.local')
    parser.add_argument('--db', default=DB_PATH, help='this machine\'s database')
    parser.add_argument('--dry-run', action='store_true', help='read and count, insert nothing')
    args = parser.parse_args(argv)
    try:
        rows = fetch_remote_rows(args.host)
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f'pull_robot_runs: {exc}', file=sys.stderr)
        return 1
    print(f'{len(rows)} real-robot row(s) on {args.host}')
    if args.dry_run:
        return 0
    init_db(args.db)
    conn = sqlite3.connect(args.db)
    try:
        added, already, left_out = merge_rows(conn, rows)
    finally:
        conn.close()
    print(f'added {added}, already here {already}'
          + (f'; columns only the Jetson has: {left_out}' if left_out else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
