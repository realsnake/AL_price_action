import run_breakout_exit_study as exit_study


def test_exit_study_uses_pullback_count_policy_set_and_labels():
    policies = exit_study.policies_for_strategy("brooks_pullback_count")

    assert "pullback_count_session_close" in policies
    assert "pullback_count_target_2r" in policies
    assert "breakout_session_close" not in policies
    assert (
        exit_study.policy_label("pullback_count_target_2r_break_even_after_0_75r")
        == "0.75R 后保本 + 固定 2R 止盈"
    )
