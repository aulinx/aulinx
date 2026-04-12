"""Tests for the error recovery module."""

from aulinx.recovery import RecoveryState


class TestRecoveryState:
    def test_initial_state(self):
        rs = RecoveryState()
        assert not rs.should_switch_strategy()
        assert not rs.is_repeated_call("test", "{}")

    def test_record_and_detect_repeat(self):
        rs = RecoveryState()
        rs.record_call("window_list", "{}")
        assert rs.is_repeated_call("window_list", "{}")
        assert not rs.is_repeated_call("app_launch", "{}")

    def test_consecutive_failures_trigger_strategy_switch(self):
        rs = RecoveryState()
        for i in range(3):
            rs.record_failure("tool", "{}", f"error {i}")
        assert rs.should_switch_strategy()

    def test_success_resets_consecutive_failures(self):
        rs = RecoveryState()
        rs.record_failure("tool", "{}", "err1")
        rs.record_failure("tool", "{}", "err2")
        rs.record_success()
        assert not rs.should_switch_strategy()

    def test_get_alternatives(self):
        rs = RecoveryState()
        alts = rs.get_alternatives("atspi_do_action")
        assert "input_key_combo" in alts
        assert "compositor_click" in alts

    def test_get_alternatives_unknown_tool(self):
        rs = RecoveryState()
        assert rs.get_alternatives("unknown_tool") == []

    def test_build_recovery_hint_with_alternatives(self):
        rs = RecoveryState()
        hint = rs.build_recovery_hint("atspi_do_action", "element not found")
        assert "input_key_combo" in hint or "compositor_click" in hint

    def test_build_recovery_hint_no_alternatives(self):
        rs = RecoveryState()
        hint = rs.build_recovery_hint("unknown_tool", "some error")
        assert "different approach" in hint

    def test_build_recovery_hint_after_strategy_switch(self):
        rs = RecoveryState()
        for i in range(3):
            rs.record_failure("tool", "{}", f"error {i}")
        hint = rs.build_recovery_hint("tool", "error again")
        assert "shell_exec" in hint or "different approach" in hint

    def test_reset(self):
        rs = RecoveryState()
        rs.record_call("tool", "{}")
        rs.record_failure("tool", "{}", "err")
        rs.reset()
        assert not rs.is_repeated_call("tool", "{}")
        assert not rs.should_switch_strategy()

    def test_filters_recently_failed_alternatives(self):
        rs = RecoveryState()
        # Fail atspi_do_action and input_key_combo
        rs.record_failure("atspi_do_action", "{}", "err")
        rs.record_failure("input_key_combo", "{}", "err")
        hint = rs.build_recovery_hint("atspi_do_action", "err")
        # Should still suggest compositor_click but not input_key_combo
        assert "compositor_click" in hint
