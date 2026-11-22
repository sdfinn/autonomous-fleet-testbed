# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""tools/proc_sweep.py: a sweep kills this project's leftovers and nobody else's.

The unit tests build a small fake /proc; the last test starts real processes."""
import os
import signal
import subprocess
import sys
import time

import pytest

from tools import proc_sweep


def _fake_proc(root, pid, cmdline, env=None, ppid=1):
    folder = root / str(pid)
    folder.mkdir()
    (folder / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in cmdline.split(' ')) + b'\0')
    (folder / 'status').write_text('Name:\tx\nPPid:\t%d\n' % ppid)
    blob = b''.join(('%s=%s' % kv).encode() + b'\0' for kv in (env or {}).items())
    (folder / 'environ').write_bytes(blob)
    return pid


@pytest.fixture
def proc_root(tmp_path):
    (tmp_path / 'self').mkdir()               # non-numeric entries are skipped
    return tmp_path


def _pids(procs):
    return sorted(p.pid for p in procs)


def test_own_domain_defaults_to_zero():
    assert proc_sweep.own_domain({}) == '0'
    assert proc_sweep.own_domain({'ROS_DOMAIN_ID': ''}) == '0'
    assert proc_sweep.own_domain({'ROS_DOMAIN_ID': ' 42 '}) == '42'


def test_other_projects_processes_are_left_alone(proc_root):
    """The case this file exists for: same process name, different ROS domain."""
    ours = _fake_proc(proc_root, 100, 'component_container_isolated --ros-args',
                      {'ROS_DOMAIN_ID': '0'})
    unset = _fake_proc(proc_root, 101, '/opt/ros/jazzy/lib/robot_localization/ekf_node', {})
    theirs = _fake_proc(proc_root, 200, 'component_container_isolated --ros-args',
                        {'ROS_DOMAIN_ID': '42', 'HOME': '/home/mike'})
    _fake_proc(proc_root, 300, 'bash', {'ROS_DOMAIN_ID': '0'})      # matches no pattern

    killed = []
    found = proc_sweep.sweep(['component_container_isolated|ekf_node'], domain='0',
                             proc_root=str(proc_root), skip=(),
                             kill=lambda pid, sig: killed.append((pid, sig)))

    assert killed == [(ours, signal.SIGKILL), (unset, signal.SIGKILL)]
    assert _pids(found.ours) == [ours, unset]
    assert _pids(found.others) == [theirs]


def test_a_process_with_no_domain_belongs_to_domain_zero_only(proc_root):
    pid = _fake_proc(proc_root, 100, 'ekf_node', {'PATH': '/usr/bin'})
    assert _pids(proc_sweep.find(['ekf_node'], domain='0', proc_root=str(proc_root),
                                 skip=()).ours) == [pid]
    on_42 = proc_sweep.find(['ekf_node'], domain='42', proc_root=str(proc_root), skip=())
    assert on_42.ours == [] and _pids(on_42.others) == [pid]


def test_a_lookalike_variable_is_not_the_domain(proc_root):
    """MY_ROS_DOMAIN_ID=42 and ROS_DOMAIN_ID_OLD=42 must not read as domain 42."""
    pid = _fake_proc(proc_root, 100, 'ekf_node',
                     {'MY_ROS_DOMAIN_ID': '42', 'ROS_DOMAIN_ID_OLD': '42'})
    assert _pids(proc_sweep.find(['ekf_node'], domain='0', proc_root=str(proc_root),
                                 skip=()).ours) == [pid]


def test_unreadable_environment_is_left_alone(proc_root, monkeypatch):
    """Another user's process: its command line is public, its environment is not."""
    pid = _fake_proc(proc_root, 100, 'ekf_node')
    real_open = open

    def guarded_open(path, *args, **kwargs):
        if str(path).endswith('/environ'):
            raise PermissionError(13, 'Permission denied', str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', guarded_open)
    found = proc_sweep.find(['ekf_node'], domain='0', proc_root=str(proc_root), skip=())
    assert found.ours == [] and _pids(found.others) == [pid]
    assert 'not readable' in proc_sweep.describe(found.others[0])


def test_the_caller_and_its_parents_never_match(proc_root):
    """The shell that runs the sweep has the pattern in its own command line."""
    _fake_proc(proc_root, 10, 'bash -c python3 -m tools.proc_sweep ekf_node', ppid=1)
    _fake_proc(proc_root, 11, 'python3 -m tools.proc_sweep ekf_node', ppid=10)
    target = _fake_proc(proc_root, 12, 'ekf_node', ppid=1)
    skip = proc_sweep.self_and_ancestors(pid=11, proc_root=str(proc_root))
    assert skip == {11, 10, 1}
    found = proc_sweep.find(['ekf_node'], domain='0', proc_root=str(proc_root), skip=skip)
    assert _pids(found.ours) == [target]


def test_patterns_are_searched_like_pgrep_f(proc_root):
    server = _fake_proc(proc_root, 100, 'gz sim -s -r /x/worlds/bedroom_simple.sdf')
    _fake_proc(proc_root, 101, 'gz sim -g')
    found = proc_sweep.find(['gz sim -s', '[n]o_such_thing'], domain='0',
                            proc_root=str(proc_root), skip=())
    assert _pids(found.ours) == [server]


def test_a_process_that_has_exited_is_not_an_error(proc_root):
    pid = _fake_proc(proc_root, 100, 'ekf_node')

    def gone(_pid, _sig):
        raise ProcessLookupError

    found = proc_sweep.sweep(['ekf_node'], domain='0', proc_root=str(proc_root), skip=(),
                             kill=gone)
    assert _pids(found.ours) == [pid]


def test_list_mode_signals_nothing_and_reports_both_kinds(proc_root, monkeypatch, capsys):
    _fake_proc(proc_root, 100, 'ekf_node', {'ROS_DOMAIN_ID': '0'})
    _fake_proc(proc_root, 200, 'ekf_node', {'ROS_DOMAIN_ID': '42'})
    monkeypatch.setattr(proc_sweep.os, 'kill', lambda *a: pytest.fail('must not signal'))
    assert proc_sweep.main(['--list', '--domain', '0', 'ekf_node'],
                           proc_root=str(proc_root), skip=()) == 0
    out = capsys.readouterr().out
    assert 'found pid 100 (ROS_DOMAIN_ID=0)' in out
    assert 'left alone, not on domain 0: pid 200 (ROS_DOMAIN_ID=42)' in out


def test_sweep_from_the_command_line_reports_what_it_signalled(proc_root, monkeypatch, capsys):
    _fake_proc(proc_root, 100, 'gz sim -s -r world.sdf')
    sent = []
    monkeypatch.setattr(proc_sweep, 'sweep', lambda patterns, **kw: (
        sent.append(kw['sig']), proc_sweep.find(patterns, domain=kw['domain'],
                                                proc_root=kw['proc_root'], skip=kw['skip']))[1])
    assert proc_sweep.main(['--signal', 'term', 'gz sim'], proc_root=str(proc_root), skip=()) == 0
    assert sent == [signal.SIGTERM]
    assert 'sent SIGTERM to pid 100 (no ROS_DOMAIN_ID)' in capsys.readouterr().out
    assert proc_sweep.main(['[n]othing_like_this'], proc_root=str(proc_root), skip=()) == 0
    assert 'nothing matches' in capsys.readouterr().out


def test_unknown_signal_is_a_usage_error():
    with pytest.raises(SystemExit):
        proc_sweep.main(['--signal', 'NOPE', 'ekf_node'])


def test_real_processes_only_the_one_on_our_domain_dies():
    """Behavior, not configuration: two real processes with the same command line, one
    started on domain 0 and one on domain 42. A sweep for domain 0 kills only the first."""
    marker = 'proc_sweep_selftest_%d' % os.getpid()
    code = 'import time; time.sleep(60)  # ' + marker

    def start(domain):
        env = dict(os.environ, ROS_DOMAIN_ID=domain)
        return subprocess.Popen([sys.executable, '-c', code], env=env)

    ours, theirs = start('0'), start('42')
    try:
        time.sleep(0.3)                        # let both reach exec
        found = proc_sweep.sweep([marker], domain='0')
        assert [p.pid for p in found.ours] == [ours.pid]
        assert [p.pid for p in found.others] == [theirs.pid]
        assert ours.wait(timeout=5) == -signal.SIGKILL
        assert theirs.poll() is None           # still running
    finally:
        for proc in (ours, theirs):
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
