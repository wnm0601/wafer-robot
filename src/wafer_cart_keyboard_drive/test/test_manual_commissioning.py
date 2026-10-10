import unittest
from unittest.mock import patch

from wafer_cart_keyboard_drive.manual_commissioning import (
    ManualControlSession, compare_measurement, connect_physical_manual)
from wafer_cart_keyboard_drive.bench_gateway import BenchGateway
from wafer_cart_keyboard_drive.bench_mock import MockWire


class CommissioningTest(unittest.TestCase):
    def test_comparison_and_no_authority(self):
        result=compare_measurement(predicted=1.1,measured=1,unit='m',source='synthetic test')
        self.assertAlmostEqual(result['relative_error_percent'],10)
        self.assertFalse(result['calibration_verified'])
        self.assertFalse(result['motor_authorization'])

    def test_signed_angle(self):
        result=compare_measurement(predicted=-88,measured=-90,unit='deg',source='synthetic test')
        self.assertEqual(result['error_predicted_minus_measured'],2)

    def test_zero_reference(self):
        self.assertIsNone(compare_measurement(predicted=0,measured=0,unit='m',source='test')['relative_error_percent'])

    def test_bad_measurement(self):
        for value in (float('nan'),float('inf'),True,'1',-1):
            with self.assertRaises(ValueError):
                compare_measurement(predicted=1,measured=value,unit='m',source='test')
        with self.assertRaises(ValueError):
            compare_measurement(predicted=1,measured=1,unit='m',source='')

    def test_physical_lock_opens_nothing(self):
        with patch('builtins.open',side_effect=AssertionError('unexpected device open')):
            with self.assertRaisesRegex(RuntimeError,'COM'):
                connect_physical_manual('COM5')

    def test_shared_controls_mock_transport(self):
        wire=MockWire(mapping_verified=True,simulate_encoder=True)
        gateway=BenchGateway(wire)
        gateway.connect(limit_percent=10)
        wire.power_feedback(True)
        session=ManualControlSession(gateway,mapping_verified=True)
        try:
            session.drive.select_mode('vector')
            session.drive.set_keys({'w'})
            session.tick()
            self.assertFalse(gateway.armed)
            session.drive.set_keys(set())
            session.drive.prepare()
            session.drive.set_keys({'w'})
            session.tick()
            self.assertEqual(session.drive.last_command,('V',10,0,0))
            session.drive.set_keys(set(),focused=False)
            self.assertFalse(gateway.armed)
            self.assertFalse(session.drive.prepared)
        finally:session.close()


if __name__=='__main__':unittest.main()
