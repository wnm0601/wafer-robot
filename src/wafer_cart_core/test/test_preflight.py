import unittest
from wafer_cart_core.preflight import assess_mock_preflight


def fixture():
    return dict(configuration="temporary", driver_revision="Rev2.0", pwm_pins=[11, 44, 12, 45],
                dir_pins=[34, 36, 35, 37], encoder_a_pins=[3, 18, 19, 20], resting_voltage_v=27.0,
                polarity_checked=True, signal_ground_checked=True, wheel_mapping_checked=True,
                charger_disconnected=True, no_heat_or_damage=True, firmware_identity_checked=True,
                serial_reopened_with_motor_power=False, power_sense_enabled=False)


class PreflightTest(unittest.TestCase):
    def test_empty_never_passes(self):
        self.assertEqual(assess_mock_preflight({})["result"], "BLOCKED")

    def test_fixture_is_only_mock_pass(self):
        result = assess_mock_preflight(fixture())
        self.assertEqual(result["result"], "MOCK_PASS")
        self.assertFalse(result["physical_motor_authorized"])

    def test_reported_voltage_boundaries(self):
        for voltage in (29.4, 26.2, float("nan"), None):
            record = fixture()
            record["resting_voltage_v"] = voltage
            self.assertEqual(assess_mock_preflight(record)["result"], "BLOCKED")

    def test_legacy_driver_pins_and_serial_reset_block(self):
        for key, value in (("driver_revision", "Rev1"), ("pwm_pins", [5, 6, 7, 8]),
                           ("serial_reopened_with_motor_power", True), ("encoder_a_pins", [19, 18, 3, 20])):
            record = fixture()
            record[key] = value
            self.assertEqual(assess_mock_preflight(record)["result"], "BLOCKED")

    def test_final_requires_additional_verified_items(self):
        record = fixture()
        record["configuration"] = "final"
        self.assertEqual(assess_mock_preflight(record)["result"], "BLOCKED")
        for key in ("pcb_c_installed", "power_sense_enabled", "manual_rearm_tested",
                    "cutoff_timing_measured", "no_power_on_button_release"):
            record[key] = True
        self.assertEqual(assess_mock_preflight(record)["result"], "MOCK_PASS")
