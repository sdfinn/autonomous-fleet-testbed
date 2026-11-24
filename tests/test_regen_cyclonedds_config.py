# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""scripts/regen_cyclonedds_config.sh: where the robot's messaging goes.

Runs the real script (bash only, no ROS: stage-1 safe)."""
import os
import pathlib
import subprocess
import xml.dom.minidom

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / 'scripts' / 'regen_cyclonedds_config.sh'


def _run(tmp_path, scope=None):
    env = dict(os.environ, CYCLONEDDS_CONFIG_PATH=str(tmp_path / 'cdds.xml'))
    env.pop('CYCLONEDDS_SCOPE', None)
    if scope is not None:
        env['CYCLONEDDS_SCOPE'] = scope
    proc = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True,
                          timeout=30)
    return proc, tmp_path / 'cdds.xml'


def test_local_scope_uses_loopback_only_and_can_find_every_process(tmp_path):
    """2026-11-20 and 2026-11-23: a new WiFi address mid-mission and the robot's own
    processes could no longer hear each other. 'local' lists no network interface.
    Loopback has no multicast, so discovery probes participant slots one by one; the
    default list of 10 is shorter than the robot's process count, and a process beyond
    it is silently never found."""
    proc, path = _run(tmp_path, 'local')
    assert proc.returncode == 0, proc.stderr
    doc = xml.dom.minidom.parse(str(path))
    names = [n.getAttribute('name') for n in doc.getElementsByTagName('NetworkInterface')]
    assert names == ['lo']
    assert doc.getElementsByTagName('AllowMulticast')[0].firstChild.data.strip() == 'false'
    slots = int(doc.getElementsByTagName('MaxAutoParticipantIndex')[0].firstChild.data)
    assert slots >= 60
    assert doc.getElementsByTagName('Peer')[0].getAttribute('address') == 'localhost'
    # the large-picture fix is kept in this mode too
    assert doc.getElementsByTagName('SocketReceiveBufferSize')[0].getAttribute('min') == '10MB'
    assert 'this machine only' in proc.stdout


def test_an_unknown_scope_is_refused_and_writes_nothing(tmp_path):
    proc, path = _run(tmp_path, 'loopbak')
    assert proc.returncode == 1 and "must be 'network' or 'local'" in proc.stderr
    assert not path.exists()


def test_the_default_scope_is_the_network_and_never_lists_loopback(tmp_path):
    proc, path = _run(tmp_path)
    if proc.returncode != 0 and 'no physical' in proc.stderr:
        pytest.skip('this machine has no physical network interface that is up')
    assert proc.returncode == 0, proc.stderr
    doc = xml.dom.minidom.parse(str(path))
    names = [n.getAttribute('name') for n in doc.getElementsByTagName('NetworkInterface')]
    assert names and 'lo' not in names
    assert not doc.getElementsByTagName('AllowMulticast')


def test_only_the_real_robot_is_put_on_loopback():
    """CI's Jetson stage runs Gazebo on the workstation and the mission on the Jetson:
    those two machines must talk over Ethernet. Loopback there would cut them apart."""
    assert 'CYCLONEDDS_SCOPE' in (REPO / 'scripts' / 'robot_boot.sh').read_text()
    for name in ('scripts/hil_stage.sh', 'tools/mission2_day.py', '.github/workflows/ci.yml'):
        assert 'CYCLONEDDS_SCOPE' not in (REPO / name).read_text(), name
