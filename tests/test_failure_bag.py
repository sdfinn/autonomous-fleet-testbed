# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for nav_fleet/failure_bag.py (S17 Piece 3): the rolling failure-evidence
bag recorder. All subprocess calls are mocked — no live rosbag2 recorder involved."""
import signal

from nav_fleet.failure_bag import SNAPSHOT_SERVICE, SNAPSHOT_SERVICE_TYPE, snapshot, start, stop


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakePopen:
    def __init__(self):
        self.signals = []
        self.waited = False

    def send_signal(self, sig):
        self.signals.append(sig)

    def wait(self, timeout=None):
        self.waited = True


def test_start_launches_snapshot_mode_recorder(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured['cmd'] = cmd
        return _FakePopen()

    monkeypatch.setattr('nav_fleet.failure_bag.subprocess.Popen', fake_popen)
    proc, bag_path = start('mission1', bag_dir=tmp_path)
    assert '--snapshot-mode' in captured['cmd']
    assert '/robot_001/cmd_vel' in captured['cmd']
    assert '/robot_001/scan' in captured['cmd']
    assert '/robot_001/amcl_pose' in captured['cmd']
    assert bag_path.parent == tmp_path
    assert bag_path.name.startswith('mission1_')


def test_snapshot_returns_true_on_success(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        return _FakeCompletedProcess(stdout='response:\nrosbag2_interfaces.srv.Snapshot_Response(success=True)\n')

    monkeypatch.setattr('nav_fleet.failure_bag.subprocess.run', fake_run)
    assert snapshot() is True
    assert captured['cmd'] == ['ros2', 'service', 'call', SNAPSHOT_SERVICE,
                              SNAPSHOT_SERVICE_TYPE, '{}']


def test_snapshot_returns_false_on_failure(monkeypatch):
    monkeypatch.setattr(
        'nav_fleet.failure_bag.subprocess.run',
        lambda cmd, **kwargs: _FakeCompletedProcess(returncode=1, stdout='', stderr='no recorder'))
    assert snapshot() is False


def test_snapshot_returns_false_on_success_false_response(monkeypatch):
    monkeypatch.setattr(
        'nav_fleet.failure_bag.subprocess.run',
        lambda cmd, **kwargs: _FakeCompletedProcess(
            stdout='rosbag2_interfaces.srv.Snapshot_Response(success=False)\n'))
    assert snapshot() is False


def test_stop_sends_sigint_and_keeps_bag_when_told(tmp_path):
    bag_path = tmp_path / 'mission1_20260721'
    bag_path.mkdir()
    proc = _FakePopen()
    stop(proc, bag_path, keep=True)
    assert proc.signals == [signal.SIGINT]
    assert proc.waited is True
    assert bag_path.exists()


def test_stop_deletes_bag_when_not_kept(tmp_path):
    bag_path = tmp_path / 'mission1_20260721'
    bag_path.mkdir()
    (bag_path / 'metadata.yaml').write_text('placeholder')
    proc = _FakePopen()
    stop(proc, bag_path, keep=False)
    assert not bag_path.exists()


def test_stop_tolerates_bag_never_written(tmp_path):
    """keep=False and the bag dir was never created (snapshot() never fired) — no error."""
    bag_path = tmp_path / 'never_written'
    proc = _FakePopen()
    stop(proc, bag_path, keep=False)  # must not raise
