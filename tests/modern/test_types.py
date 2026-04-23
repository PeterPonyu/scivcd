"""Tests for scivcd.core.types — Severity, Category, Stage.

These types live in ``scivcd/core/types.py`` which is already present.
All tests import directly from the core subpackage so they run even when
the full scivcd top-level API is not yet implemented.
"""

from __future__ import annotations

import pytest

from scivcd.core.types import Category, Severity, Stage


# ---------------------------------------------------------------------------
# Severity.coerce — legacy string mapping
# ---------------------------------------------------------------------------

class TestSeverityCoerce:
    def test_major_maps_to_high(self):
        assert Severity.coerce("MAJOR") == Severity.HIGH

    def test_minor_maps_to_medium(self):
        assert Severity.coerce("MINOR") == Severity.MEDIUM

    def test_critical_maps_to_blocker(self):
        assert Severity.coerce("CRITICAL") == Severity.BLOCKER

    def test_high_round_trips(self):
        assert Severity.coerce("HIGH") == Severity.HIGH

    def test_low_round_trips(self):
        assert Severity.coerce("LOW") == Severity.LOW

    def test_info_round_trips(self):
        assert Severity.coerce("INFO") == Severity.INFO

    def test_blocker_round_trips(self):
        assert Severity.coerce("BLOCKER") == Severity.BLOCKER

    def test_case_insensitive(self):
        assert Severity.coerce("major") == Severity.HIGH
        assert Severity.coerce("Minor") == Severity.MEDIUM

    def test_enum_value_round_trips(self):
        assert Severity.coerce(Severity.HIGH) == Severity.HIGH

    def test_integer_coerce(self):
        assert Severity.coerce(0) == Severity.BLOCKER
        assert Severity.coerce(4) == Severity.INFO

    def test_unknown_string_raises(self):
        with pytest.raises(ValueError, match="Unknown Severity"):
            Severity.coerce("CATASTROPHIC")

    def test_unknown_integer_raises(self):
        with pytest.raises(ValueError):
            Severity.coerce(99)

    def test_severity_ordering_by_value(self):
        """BLOCKER (0) is more serious than INFO (4)."""
        assert Severity.BLOCKER.value < Severity.INFO.value
        assert Severity.HIGH.value < Severity.MEDIUM.value


# ---------------------------------------------------------------------------
# Category.coerce — round-trip
# ---------------------------------------------------------------------------

class TestCategoryCoerce:
    def test_policy_round_trips(self):
        assert Category.coerce("POLICY") == Category.POLICY

    def test_layout_round_trips(self):
        assert Category.coerce("LAYOUT") == Category.LAYOUT

    def test_typography_round_trips(self):
        assert Category.coerce("TYPOGRAPHY") == Category.TYPOGRAPHY

    def test_content_round_trips(self):
        assert Category.coerce("CONTENT") == Category.CONTENT

    def test_accessibility_round_trips(self):
        assert Category.coerce("ACCESSIBILITY") == Category.ACCESSIBILITY

    def test_case_insensitive(self):
        assert Category.coerce("layout") == Category.LAYOUT

    def test_enum_value_round_trips(self):
        assert Category.coerce(Category.CONTENT) == Category.CONTENT

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown Category"):
            Category.coerce("AESTHETICS")


# ---------------------------------------------------------------------------
# Stage.coerce
# ---------------------------------------------------------------------------

class TestStageCoerce:
    def test_tier1_by_name(self):
        assert Stage.coerce("TIER1") == Stage.TIER1

    def test_tier2_by_name(self):
        assert Stage.coerce("TIER2") == Stage.TIER2

    def test_tier1_by_int(self):
        assert Stage.coerce(1) == Stage.TIER1

    def test_tier2_by_int(self):
        assert Stage.coerce(2) == Stage.TIER2

    def test_enum_round_trips(self):
        assert Stage.coerce(Stage.TIER1) == Stage.TIER1

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError, match="Unknown Stage"):
            Stage.coerce("TIER3")

    def test_unknown_int_raises(self):
        with pytest.raises(ValueError):
            Stage.coerce(99)
