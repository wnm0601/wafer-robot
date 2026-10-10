import unittest
from unittest.mock import Mock,patch

from wafer_cart_keyboard_drive.manual_hardware import open_manual_serial
from wafer_cart_keyboard_drive.bench_gateway import BenchGateway
from wafer_cart_keyboard_drive.bench_mock import MockWire


class ManualSerialTest(unittest.TestCase):
    def test_operator_confirmation_before_open(self):
        factory=Mock()
        with self.assertRaises(ValueError):open_manual_serial('COM5',serial_factory=factory)
        factory.assert_not_called()

    def test_bad_port_before_open(self):
        factory=Mock()
        for port in ('COM0','COM5\n','/dev/ttyUSB0','auto',''):
            with self.assertRaises(ValueError):
                open_manual_serial(port,operator_confirmed=True,serial_factory=factory)
        factory.assert_not_called()

    def test_bounded_factory_no_motion_on_open(self):
        stream=Mock(timeout=.02,write_timeout=.1)
        factory=Mock(return_value=stream)
        with patch('wafer_cart_keyboard_drive.manual_hardware.time.sleep'):
            wire=open_manual_serial('com5',operator_confirmed=True,serial_factory=factory)
        factory.assert_called_once_with(port='COM5',baudrate=115200,timeout=.02,write_timeout=.1)
        stream.write.assert_not_called()
        wire.close();stream.close.assert_called_once()

    def test_real_gateway_rejects_simulation(self):
        gateway=BenchGateway(MockWire(),expected_mode='MANUAL_ONLY')
        try:
            with self.assertRaisesRegex(Exception,'matching firmware mode'):gateway.connect(limit_percent=1)
        finally:gateway.close()


if __name__=='__main__':unittest.main()
