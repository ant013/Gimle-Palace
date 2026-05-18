"""Tests for EffectiveMode enum + describe_effective_mode classifier."""

from __future__ import annotations

import itertools
from dataclasses import replace

import pytest

from gimle_watchdog.config import (
    ALERT_FLAG_NAMES,
    AUTO_REPAIR_FLAG_NAME,
    ConfigError,
    EffectiveMode,
    describe_effective_mode,
)

from tests._factories import _make_config


def test_effective_mode_enum_has_five_members() -> None:
    assert {mode.value for mode in EffectiveMode} == {
        "observe-only",
        "alert-only",
        "recovery-only",
        "full-watchdog",
        "unsafe-auto-repair",
    }


def test_alert_flag_names_is_frozenset_of_strs() -> None:
    assert isinstance(ALERT_FLAG_NAMES, frozenset)
    assert ALERT_FLAG_NAMES == frozenset(
        {
            "handoff_alert_enabled",
            "handoff_cross_team_enabled",
            "handoff_ownerless_enabled",
            "handoff_infra_block_enabled",
            "handoff_stale_bundle_enabled",
        }
    )


def test_auto_repair_flag_name_constant() -> None:
    assert AUTO_REPAIR_FLAG_NAME == "handoff_auto_repair_enabled"


@pytest.mark.parametrize(
    ("recovery", "any_alert", "auto_repair", "expected"),
    [
        (False, False, False, EffectiveMode.OBSERVE_ONLY),
        (False, True, False, EffectiveMode.ALERT_ONLY),
        (True, False, False, EffectiveMode.RECOVERY_ONLY),
        (True, True, False, EffectiveMode.FULL_WATCHDOG),
        (False, False, True, EffectiveMode.UNSAFE_AUTO_REPAIR),
        (False, True, True, EffectiveMode.UNSAFE_AUTO_REPAIR),
        (True, False, True, EffectiveMode.UNSAFE_AUTO_REPAIR),
        (True, True, True, EffectiveMode.UNSAFE_AUTO_REPAIR),
    ],
)
def test_describe_effective_mode_partition(
    recovery: bool,
    any_alert: bool,
    auto_repair: bool,
    expected: EffectiveMode,
) -> None:
    cfg = _make_config(recovery_enabled=recovery, any_alert=any_alert, auto_repair=auto_repair)
    assert describe_effective_mode(cfg) == expected


def test_partition_is_complete() -> None:
    """Every (recovery, any_alert, auto_repair) triple maps to exactly one mode."""

    seen: list[EffectiveMode] = []
    for recovery, any_alert, auto_repair in itertools.product([False, True], repeat=3):
        cfg = _make_config(recovery_enabled=recovery, any_alert=any_alert, auto_repair=auto_repair)
        seen.append(describe_effective_mode(cfg))
    assert len(seen) == 8
    assert all(isinstance(mode, EffectiveMode) for mode in seen)


def test_describe_rejects_unknown_handoff_flag() -> None:
    """Unknown handoff_*_enabled field on HandoffConfig must raise ConfigError."""

    cfg = _make_config()
    bogus_handoff = replace(cfg.handoff)
    object.__setattr__(bogus_handoff, "handoff_experimental_enabled", True)
    bogus_cfg = replace(cfg, handoff=bogus_handoff)
    with pytest.raises(ConfigError, match="handoff_experimental_enabled"):
        describe_effective_mode(bogus_cfg)
