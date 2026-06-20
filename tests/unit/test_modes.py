from finops_core.modes import (
    MODES,
    can_apply_actions,
    can_generate_artifacts,
    is_write_tool,
    normalize_mode,
    tool_blocked,
)


def test_is_write_tool():
    assert is_write_tool("apply_guarded_action")
    assert is_write_tool("delete_ebs_snapshot")
    assert is_write_tool("create_budget")
    assert not is_write_tool("get_cost_by_service")
    assert not is_write_tool("drill_down")


def test_tool_blocked_by_mode():
    # write-shaped tool blocked unless guarded_write
    assert tool_blocked("apply_x", "advisory") is True
    assert tool_blocked("apply_x", "artifacts") is True
    assert tool_blocked("apply_x", "guarded_write") is False
    # read tools never blocked
    assert tool_blocked("get_cost_by_service", "advisory") is False


def test_modes_order():
    assert MODES == ["advisory", "artifacts", "guarded_write"]


def test_advisory_blocks_everything():
    assert can_generate_artifacts("advisory") is False
    assert can_apply_actions("advisory") is False


def test_artifacts_allows_artifacts_only():
    assert can_generate_artifacts("artifacts") is True
    assert can_apply_actions("artifacts") is False


def test_guarded_write_allows_both():
    assert can_generate_artifacts("guarded_write") is True
    assert can_apply_actions("guarded_write") is True


def test_normalize_mode_defaults_to_advisory():
    assert normalize_mode("bogus") == "advisory"
    assert normalize_mode(None) == "advisory"
    assert normalize_mode("guarded_write") == "guarded_write"
