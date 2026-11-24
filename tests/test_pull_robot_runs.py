# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""tools.pull_robot_runs: the robot's run rows reach the workstation's database."""
import sqlite3
import subprocess

import pytest

from tools import pull_robot_runs as pr
from tools.telemetry_logger import init_db


def _row(ts, scenario='mission2_yellow', **more):
    row = {'id': 7, 'scenario': scenario, 'timestamp': ts, 'steps': 0, 'final_x': 0.0,
           'final_y': 0.0, 'result': 'PASS', 'runner_type': 'real_robot', 'sim_engine': 'real'}
    row.update(more)
    return row


@pytest.fixture
def conn(tmp_path):
    path = str(tmp_path / 'fleet.db')
    init_db(path)
    c = sqlite3.connect(path)
    yield c
    c.close()


def test_new_rows_are_added_and_a_second_pull_adds_nothing(conn):
    rows = [_row('2026-11-23T22:41:49'), _row('2026-11-23T22:41:49', 'mission2_red')]
    assert pr.merge_rows(conn, rows)[:2] == (2, 0)
    assert pr.merge_rows(conn, rows)[:2] == (0, 2)             # the same rows again
    got = conn.execute(
        "select scenario, result, runner_type from runs order by scenario").fetchall()
    assert got == [('mission2_red', 'PASS', 'real_robot'),
                   ('mission2_yellow', 'PASS', 'real_robot')]


def test_the_robots_row_id_is_not_copied_and_local_rows_are_untouched(conn):
    conn.execute("insert into runs (scenario, timestamp, result, runner_type) "
                 "values ('bedroom_nav', '2026-11-01T00:00:00', 'PASS', 'local')")
    conn.commit()
    pr.merge_rows(conn, [_row('2026-11-23T22:41:49')])
    ids = [r[0] for r in conn.execute('select id from runs order by id')]
    assert ids == [1, 2]                                        # not the Jetson's 7
    assert conn.execute("select count(*) from runs where runner_type='local'").fetchone()[0] == 1


def test_a_column_only_the_robot_has_is_left_out_and_reported(conn):
    added, _already, left_out = pr.merge_rows(
        conn, [_row('2026-11-23T22:41:49', a_column_from_the_future=1)])
    assert added == 1 and left_out == ['a_column_from_the_future']


def test_a_failed_read_is_an_error_not_an_empty_result(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(
        a, 255, stdout='', stderr='ssh: connect to host jetson.local port 22: No route to host'))
    with pytest.raises(RuntimeError, match='No route to host'):
        pr.fetch_remote_rows('jetson.local')
    assert pr.main(['--host', 'jetson.local', '--dry-run']) == 1


def test_the_read_asks_only_for_real_robot_rows_and_opens_the_database_read_only(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen['cmd'], seen['script'] = cmd, kwargs['input']
        return subprocess.CompletedProcess(cmd, 0, stdout='[]', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert pr.fetch_remote_rows('jetson.local') == []
    assert seen['cmd'][-2:] == ['python3', '-'] and 'jetson.local' in seen['cmd']
    assert 'mode=ro' in seen['script'] and 'real_robot' in seen['script']
