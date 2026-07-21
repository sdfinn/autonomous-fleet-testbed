# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/pull_ros_logs.py (S17 Piece 3): the "one documented command" to
retrieve a robot's ROS2 log directory. All subprocess calls are mocked — no real ssh/scp,
no dependency on an actual ~/.ros/log existing."""
import pathlib

import pytest

from tools.pull_ros_logs import _default_host, pull_latest, resolve_latest_session


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_resolve_latest_session_local_uses_readlink(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        return _FakeCompletedProcess(stdout='/home/mike/.ros/log/2026-07-21-abc\n')

    monkeypatch.setattr('tools.pull_ros_logs.subprocess.run', fake_run)
    result = resolve_latest_session(None)
    assert result == '/home/mike/.ros/log/2026-07-21-abc'
    assert captured['cmd'][0] == 'readlink'
    assert 'ssh' not in captured['cmd']


def test_resolve_latest_session_remote_uses_ssh(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        return _FakeCompletedProcess(stdout='/home/mike/.ros/log/2026-07-21-abc\n')

    monkeypatch.setattr('tools.pull_ros_logs.subprocess.run', fake_run)
    result = resolve_latest_session('mike@jetson.local')
    assert result == '/home/mike/.ros/log/2026-07-21-abc'
    assert captured['cmd'][0] == 'ssh'
    assert 'mike@jetson.local' in captured['cmd']


def test_resolve_latest_session_raises_on_ssh_failure(monkeypatch):
    monkeypatch.setattr(
        'tools.pull_ros_logs.subprocess.run',
        lambda cmd, **kwargs: _FakeCompletedProcess(returncode=255, stderr='Connection refused'))
    with pytest.raises(RuntimeError, match='Connection refused'):
        resolve_latest_session('mike@jetson.local')


def test_pull_latest_local_copies_via_cp(monkeypatch, tmp_path):
    monkeypatch.setattr('tools.pull_ros_logs.resolve_latest_session',
                        lambda host: '/home/mike/.ros/log/2026-07-21-abc')
    captured = {}

    def fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        return _FakeCompletedProcess()

    monkeypatch.setattr('tools.pull_ros_logs.subprocess.run', fake_run)
    result = pull_latest(None, dest_dir=tmp_path)
    assert result == tmp_path / '2026-07-21-abc'
    assert captured['cmd'][0] == 'cp'
    assert 'scp' not in captured['cmd']


def test_pull_latest_remote_uses_scp(monkeypatch, tmp_path):
    monkeypatch.setattr('tools.pull_ros_logs.resolve_latest_session',
                        lambda host: '/home/mike/.ros/log/2026-07-21-abc')
    captured = {}

    def fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        return _FakeCompletedProcess()

    monkeypatch.setattr('tools.pull_ros_logs.subprocess.run', fake_run)
    result = pull_latest('mike@jetson.local', dest_dir=tmp_path)
    assert result == tmp_path / '2026-07-21-abc'
    assert captured['cmd'][0] == 'scp'
    assert any('mike@jetson.local:' in part for part in captured['cmd'])


def test_default_host_uses_jetson_env_vars(monkeypatch):
    monkeypatch.setenv('JETSON_IP', '10.42.0.217')
    monkeypatch.setenv('JETSON_USER', 'mike')
    assert _default_host() == 'mike@10.42.0.217'


def test_default_host_none_when_jetson_ip_unset(monkeypatch):
    monkeypatch.delenv('JETSON_IP', raising=False)
    assert _default_host() is None
