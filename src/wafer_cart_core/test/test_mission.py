import unittest

from wafer_cart_core.mission import MissionController, MissionError, MissionState


class MissionControllerTest(unittest.TestCase):
    def ready_controller(self) -> MissionController:
        controller = MissionController()
        controller.operator_ready()
        return controller

    def outbound_controller(self) -> MissionController:
        controller = self.ready_controller()
        controller.select_destination(2)
        controller.report_load_complete(cycle_id="cycle-001", loaded_count=5)
        controller.start_now()
        return controller

    def test_restart_always_returns_to_safe_stop(self) -> None:
        controller = self.outbound_controller()
        controller.restart()
        self.assertEqual(controller.state, MissionState.SAFE_STOP)
        self.assertIsNone(controller.destination)
        self.assertEqual(controller.loaded_count, 0)

    def test_load_complete_without_destination_waits(self) -> None:
        controller = self.ready_controller()
        controller.report_load_complete(cycle_id="cycle-001", loaded_count=5)
        self.assertEqual(controller.state, MissionState.LOAD_READY)
        controller.select_destination(3)
        self.assertEqual(controller.state, MissionState.DEPARTURE_COUNTDOWN)
        self.assertEqual(controller.countdown_remaining, 5.0)

    def test_count_below_target_is_rejected(self) -> None:
        controller = self.ready_controller()
        with self.assertRaises(MissionError):
            controller.report_load_complete(cycle_id="cycle-001", loaded_count=4)

    def test_human_clear_for_four_seconds_resumes_drive(self) -> None:
        controller = self.outbound_controller()
        controller.person_detected()
        self.assertEqual(controller.state, MissionState.HUMAN_STOP)
        controller.tick(3.9, person_visible=False)
        self.assertEqual(controller.state, MissionState.HUMAN_STOP)
        controller.tick(0.1, person_visible=False)
        self.assertEqual(controller.state, MissionState.OUTBOUND)

    def test_person_reappearance_restarts_clear_timer(self) -> None:
        controller = self.outbound_controller()
        controller.person_detected()
        controller.tick(3.0, person_visible=False)
        controller.tick(0.1, person_visible=True)
        controller.tick(3.9, person_visible=False)
        self.assertEqual(controller.state, MissionState.HUMAN_STOP)

    def test_line_loss_requires_manual_recovery_before_auto_resume(self) -> None:
        controller = self.outbound_controller()
        controller.line_lost()
        self.assertEqual(controller.state, MissionState.LINE_LOST_STOP)
        controller.begin_manual_line_recovery()
        self.assertEqual(controller.state, MissionState.MANUAL_LINE_RECOVERY)
        controller.line_reacquired(stable=False)
        self.assertEqual(controller.state, MissionState.MANUAL_LINE_RECOVERY)
        controller.line_reacquired(stable=True)
        self.assertEqual(controller.state, MissionState.OUTBOUND)

    def test_manual_mode_can_replace_line_recovery(self) -> None:
        controller = self.outbound_controller()
        controller.line_lost()
        controller.begin_manual_line_recovery()
        controller.enter_manual()
        self.assertEqual(controller.state, MissionState.MANUAL)

    def test_unload_return_and_home_cycle(self) -> None:
        controller = self.outbound_controller()
        controller.destination_arrived()
        controller.unload_complete()
        controller.tick(10.0)
        self.assertEqual(controller.state, MissionState.TURNAROUND_CONFIRM)
        controller.confirm_turnaround()
        controller.turnaround_complete(line_aligned=True)
        self.assertEqual(controller.state, MissionState.RETURNING)
        controller.home_arrived()
        self.assertEqual(controller.state, MissionState.WAITING_FOR_LOAD)
        self.assertIsNone(controller.destination)

    def test_failed_turnaround_falls_back_to_manual(self) -> None:
        controller = self.outbound_controller()
        controller.destination_arrived()
        controller.unload_complete()
        controller.start_now()
        controller.confirm_turnaround()
        controller.turnaround_complete(line_aligned=False)
        self.assertEqual(controller.state, MissionState.MANUAL)

    def test_destination_is_locked_while_driving(self) -> None:
        controller = self.outbound_controller()
        self.assertTrue(controller.settings_locked)
        with self.assertRaises(MissionError):
            controller.select_destination(1)

    def test_operator_stop_requires_explicit_resume(self) -> None:
        controller = self.outbound_controller()
        controller.operator_stop()
        self.assertEqual(controller.state, MissionState.OPERATOR_STOP)
        controller.tick(60.0)
        self.assertEqual(controller.state, MissionState.OPERATOR_STOP)
        controller.operator_resume()
        self.assertEqual(controller.state, MissionState.OUTBOUND)

    def test_auto_drive_button_resumes_operator_stop(self) -> None:
        controller = self.outbound_controller()
        controller.operator_stop()
        controller.press_auto_drive()
        self.assertEqual(controller.state, MissionState.OUTBOUND)

    def test_auto_drive_button_starts_during_departure_countdown(self) -> None:
        controller = self.ready_controller()
        controller.select_destination(1)
        controller.report_load_complete(cycle_id="cycle-002", loaded_count=5)
        controller.press_auto_drive()
        self.assertEqual(controller.state, MissionState.OUTBOUND)

    def test_operator_stop_can_pause_manual_line_recovery(self) -> None:
        controller = self.outbound_controller()
        controller.line_lost()
        controller.begin_manual_line_recovery()
        controller.operator_stop()
        self.assertEqual(controller.state, MissionState.OPERATOR_STOP)
        controller.operator_resume()
        self.assertEqual(controller.state, MissionState.MANUAL_LINE_RECOVERY)

    def test_emergency_stop_latches_until_reset(self) -> None:
        controller = self.outbound_controller()
        controller.emergency_stop()
        self.assertEqual(controller.state, MissionState.E_STOP)
        with self.assertRaises(MissionError):
            controller.enter_manual()
        controller.reset_estop()
        self.assertEqual(controller.state, MissionState.SAFE_STOP)


if __name__ == "__main__":
    unittest.main()
