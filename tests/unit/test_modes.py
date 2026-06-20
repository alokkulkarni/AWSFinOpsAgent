from finops_core.modes import MODES, can_apply_actions, can_generate_artifacts, normalize_mode


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
