"""Tests for scivcd's check registry — register, iter_checks, dedup.

These tests target the ``scivcd.register``, ``scivcd.iter_checks``, and
``scivcd.core.CheckSpec`` symbols.  If those haven't been implemented yet
the whole module skips gracefully.

Each test that registers checks uses unique IDs (prefixed by class name)
and tears down via ``unregister`` in a fixture so duplicate-id errors do
not bleed between tests.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Conditional import — skip cleanly when the registry layer doesn't exist
# ---------------------------------------------------------------------------
scivcd = pytest.importorskip(
    "scivcd",
    reason="scivcd top-level API not yet implemented",
)
for _sym in ("register", "iter_checks", "unregister"):
    if not hasattr(scivcd, _sym):
        pytest.skip(
            f"scivcd.{_sym} not yet implemented",
            allow_module_level=True,
        )

try:
    from scivcd.core import CheckSpec
except ImportError:
    pytest.skip("scivcd.core.CheckSpec not yet implemented", allow_module_level=True)

from scivcd.core.types import Category, Severity, Stage

register = scivcd.register
iter_checks = scivcd.iter_checks
unregister = scivcd.unregister


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _noop_fire(fig, config):
    """Minimal fire callable that satisfies CheckSpec's required field."""
    return []


def _make_spec(check_id: str, *, stage: Stage = Stage.TIER1,
               default_enabled: bool = True) -> CheckSpec:
    """Build a minimal CheckSpec for testing."""
    return CheckSpec(
        id=check_id,
        description=f"Synthetic check {check_id} for unit tests",
        severity=Severity.MEDIUM,
        category=Category.LAYOUT,
        stage=stage,
        fire=_noop_fire,
        default_enabled=default_enabled,
    )


@pytest.fixture(autouse=True)
def _cleanup_registry():
    """Unregister any IDs added in a test after it completes."""
    registered_before = {c.id for c in iter_checks(enabled_only=False)}
    yield
    registered_after = {c.id for c in iter_checks(enabled_only=False)}
    for cid in registered_after - registered_before:
        unregister(cid)


# ---------------------------------------------------------------------------
# Basic registration and lookup
# ---------------------------------------------------------------------------

class TestRegisterAndIter:
    def test_registered_id_appears_in_iter_checks(self):
        spec = _make_spec("test_reg_basic_001")
        register(spec)
        ids = {c.id for c in iter_checks(enabled_only=False)}
        assert "test_reg_basic_001" in ids

    def test_duplicate_id_raises(self):
        spec = _make_spec("test_reg_dup_001")
        register(spec)
        with pytest.raises((ValueError, KeyError)):
            register(_make_spec("test_reg_dup_001"))

    def test_iter_checks_returns_list(self):
        checks = list(iter_checks(enabled_only=False))
        assert isinstance(checks, list)

    def test_multiple_checks_all_present(self):
        ids_to_register = ["test_multi_a", "test_multi_b", "test_multi_c"]
        for cid in ids_to_register:
            register(_make_spec(cid))
        registered = {c.id for c in iter_checks(enabled_only=False)}
        for cid in ids_to_register:
            assert cid in registered


# ---------------------------------------------------------------------------
# Stage filtering
# ---------------------------------------------------------------------------

class TestIterChecksStageFilter:
    def test_tier1_filter_only_returns_tier1(self):
        register(_make_spec("test_stage_t1_001", stage=Stage.TIER1))
        register(_make_spec("test_stage_t2_001", stage=Stage.TIER2))
        tier1_ids = {c.id for c in iter_checks(stage=Stage.TIER1, enabled_only=False)}
        assert "test_stage_t1_001" in tier1_ids
        assert "test_stage_t2_001" not in tier1_ids

    def test_tier2_filter_only_returns_tier2(self):
        register(_make_spec("test_stage_t1_002", stage=Stage.TIER1))
        register(_make_spec("test_stage_t2_002", stage=Stage.TIER2))
        tier2_ids = {c.id for c in iter_checks(stage=Stage.TIER2, enabled_only=False)}
        assert "test_stage_t2_002" in tier2_ids
        assert "test_stage_t1_002" not in tier2_ids


# ---------------------------------------------------------------------------
# enabled_only filtering
# ---------------------------------------------------------------------------

class TestIterChecksEnabledOnly:
    def test_disabled_check_excluded_from_enabled_only(self):
        register(_make_spec("test_disabled_001", default_enabled=False))
        register(_make_spec("test_enabled_001", default_enabled=True))
        enabled_ids = {c.id for c in iter_checks(enabled_only=True)}
        assert "test_enabled_001" in enabled_ids
        assert "test_disabled_001" not in enabled_ids

    def test_all_checks_visible_with_enabled_only_false(self):
        register(_make_spec("test_disabled_002", default_enabled=False))
        all_ids = {c.id for c in iter_checks(enabled_only=False)}
        assert "test_disabled_002" in all_ids


# ---------------------------------------------------------------------------
# Config-driven disabled_checks propagation
# ---------------------------------------------------------------------------

class TestConfigDisabledChecks:
    def test_config_disabled_checks_excluded(self):
        """If ScivcdConfig.disabled_checks contains an ID, iter_checks
        with that config active must not yield that check."""
        if not hasattr(scivcd, "ScivcdConfig"):
            pytest.skip("ScivcdConfig not yet implemented")

        ScivcdConfig = scivcd.ScivcdConfig
        register(_make_spec("test_cfg_disabled_001", default_enabled=True))
        # disabled_checks is frozenset[str]
        cfg = ScivcdConfig(disabled_checks=frozenset({"test_cfg_disabled_001"}))
        ids_with_cfg = {c.id for c in iter_checks(config=cfg, enabled_only=True)}
        assert "test_cfg_disabled_001" not in ids_with_cfg
