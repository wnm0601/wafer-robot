"""Checklist-derived mock assessment; never authorizes a physical motor."""
import math


def assess_mock_preflight(record):
    blocks = []
    required = ("polarity_checked", "signal_ground_checked", "wheel_mapping_checked",
                "charger_disconnected", "no_heat_or_damage", "firmware_identity_checked")
    for key in required:
        if record.get(key) is not True:
            blocks.append(key)
    if record.get("driver_revision") != "Rev2.0":
        blocks.append("driver_revision")
    if record.get("pwm_pins") != [11, 44, 12, 45]:
        blocks.append("pwm_pins")
    if record.get("dir_pins") != [34, 36, 35, 37]:
        blocks.append("dir_pins")
    if record.get("encoder_a_pins") != [3, 18, 19, 20]:
        blocks.append("encoder_a_pins")
    voltage = record.get("resting_voltage_v")
    # Document-reported temporary threshold, NOT manufacturer-certified safety.
    if (type(voltage) not in (int, float) or not math.isfinite(voltage)
            or not 26.3 <= voltage <= 28.1):
        blocks.append("reported_start_voltage_range")
    if record.get("serial_reopened_with_motor_power") is not False:
        blocks.append("serial_reset_risk")
    configuration = record.get("configuration")
    if configuration not in ("temporary", "final"):
        blocks.append("configuration_unknown")
    elif configuration == "final":
        for key in ("pcb_c_installed", "power_sense_enabled", "manual_rearm_tested",
                    "cutoff_timing_measured", "no_power_on_button_release"):
            if record.get(key) is not True:
                blocks.append(key)
    elif record.get("power_sense_enabled") is not False:
        blocks.append("temporary_configuration_sense_mismatch")
    return dict(result="MOCK_PASS" if not blocks else "BLOCKED", blocks=blocks,
                physical_motor_authorized=False,
                note="점검표 기반 모의 판정이며 현물 안전 인증·운용 허가가 아닙니다.")
