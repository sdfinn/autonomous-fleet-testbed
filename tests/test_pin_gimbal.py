# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pure-Python — the serial.Serial(...) I/O boundary is mocked throughout, same
treatment as tests/test_esp32_driver.py gives esp32_driver.py's identical boundary.
No rclpy import here, so this runs in stage-1-quality like test_esp32_protocol.py."""
import json
from unittest.mock import MagicMock, patch

import serial

from tools.pin_gimbal import main, send_gimbal_cmd


def _mock_serial_cm():
    """A MagicMock configured to behave as a `with serial.Serial(...) as ser:`
    context manager, matching send_gimbal_cmd's real usage."""
    mock_ser = MagicMock()
    mock_serial_cls = MagicMock(return_value=mock_ser)
    mock_ser.__enter__ = MagicMock(return_value=mock_ser)
    mock_ser.__exit__ = MagicMock(return_value=False)
    return mock_serial_cls, mock_ser


def test_send_gimbal_cmd_writes_expected_json_line():
    mock_serial_cls, mock_ser = _mock_serial_cm()
    with patch('tools.pin_gimbal.serial.Serial', mock_serial_cls):
        cmd = send_gimbal_cmd('/dev/ttyTHS1', 115200, 10.0, -5.0)
    assert cmd == {"T": 133, "X": 10.0, "Y": -5.0, "SPD": 0, "ACC": 0}
    mock_serial_cls.assert_called_once_with('/dev/ttyTHS1', 115200, timeout=1.0)
    (sent_bytes,) = mock_ser.write.call_args.args
    assert json.loads(sent_bytes.decode('utf-8')) == cmd
    assert sent_bytes.endswith(b'\n')


def test_main_default_pan_tilt_is_zero_and_forward_level():
    mock_serial_cls, mock_ser = _mock_serial_cm()
    with patch('tools.pin_gimbal.serial.Serial', mock_serial_cls):
        rc = main([])
    assert rc == 0
    (sent_bytes,) = mock_ser.write.call_args.args
    assert json.loads(sent_bytes.decode('utf-8')) == {
        "T": 133, "X": 0.0, "Y": 0.0, "SPD": 0, "ACC": 0}


def test_main_passes_through_pan_tilt_and_port_args():
    mock_serial_cls, mock_ser = _mock_serial_cm()
    with patch('tools.pin_gimbal.serial.Serial', mock_serial_cls):
        rc = main(['--pan', '15', '--tilt', '-3', '--port', '/dev/ttyUSB1',
                   '--baud', '921600'])
    assert rc == 0
    mock_serial_cls.assert_called_once_with('/dev/ttyUSB1', 921600, timeout=1.0)
    (sent_bytes,) = mock_ser.write.call_args.args
    assert json.loads(sent_bytes.decode('utf-8')) == {
        "T": 133, "X": 15.0, "Y": -3.0, "SPD": 0, "ACC": 0}


def test_main_prints_sent_command(capsys):
    mock_serial_cls, mock_ser = _mock_serial_cm()
    with patch('tools.pin_gimbal.serial.Serial', mock_serial_cls):
        main([])
    out = capsys.readouterr().out
    assert '"T": 133' in out or '"T":133' in out


def test_main_serial_error_returns_nonzero_and_prints_to_stderr(capsys):
    mock_serial_cls = MagicMock(side_effect=serial.SerialException('port busy'))
    with patch('tools.pin_gimbal.serial.Serial', mock_serial_cls):
        rc = main(['--port', '/dev/ttyTHS1'])
    assert rc == 1
    err = capsys.readouterr().err
    assert '/dev/ttyTHS1' in err
    assert 'port busy' in err
