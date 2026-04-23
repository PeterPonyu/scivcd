"""Tests for scivcd exemption helpers — exempt(), ignore(), is_exempt().

Skips gracefully if those symbols are not yet present.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pytest

scivcd = pytest.importorskip(
    "scivcd",
    reason="scivcd top-level API not yet implemented",
)
for _sym in ("exempt", "ignore", "is_exempt"):
    if not hasattr(scivcd, _sym):
        pytest.skip(
            f"scivcd.{_sym} not yet implemented",
            allow_module_level=True,
        )

exempt = scivcd.exempt
ignore = scivcd.ignore
is_exempt = scivcd.is_exempt


# ---------------------------------------------------------------------------
# Context-manager form: `with exempt("check_id"): ...`
# ---------------------------------------------------------------------------

class TestExemptContextManager:
    def test_artist_tagged_inside_context(self):
        fig, ax = plt.subplots()
        with exempt("layout.axis_overflow"):
            t = ax.text(0.5, 0.5, "hello")
        assert is_exempt(t, "layout.axis_overflow")
        plt.close(fig)

    def test_artist_not_tagged_outside_context(self):
        fig, ax = plt.subplots()
        t = ax.text(0.5, 0.5, "world")
        assert not is_exempt(t, "layout.axis_overflow")
        plt.close(fig)

    def test_context_does_not_bleed_across_artists(self):
        fig, ax = plt.subplots()
        with exempt("layout.axis_overflow"):
            t_inside = ax.text(0.1, 0.1, "inside")
        t_outside = ax.text(0.9, 0.9, "outside")
        assert is_exempt(t_inside, "layout.axis_overflow")
        assert not is_exempt(t_outside, "layout.axis_overflow")
        plt.close(fig)

    def test_multiple_check_ids_in_same_context(self):
        fig, ax = plt.subplots()
        with exempt("check_a"), exempt("check_b"):
            t = ax.text(0.5, 0.5, "multi-exempt")
        assert is_exempt(t, "check_a")
        assert is_exempt(t, "check_b")
        plt.close(fig)

    def test_exempt_is_check_id_specific(self):
        fig, ax = plt.subplots()
        with exempt("check_x"):
            t = ax.text(0.5, 0.5, "only x")
        assert is_exempt(t, "check_x")
        assert not is_exempt(t, "check_y")
        plt.close(fig)


# ---------------------------------------------------------------------------
# Keyword form: ax.text(..., **ignore("check_id"))
# ---------------------------------------------------------------------------

class TestIgnoreKeywordHelper:
    def test_ignore_tags_artist_via_gid(self):
        fig, ax = plt.subplots()
        t = ax.text(0.5, 0.5, "via gid", **ignore("typography.min_font"))
        assert is_exempt(t, "typography.min_font")
        plt.close(fig)

    def test_ignore_returns_dict_with_gid_key(self):
        result = ignore("some_check")
        assert isinstance(result, dict)
        assert "gid" in result

    def test_ignore_multiple_ids(self):
        fig, ax = plt.subplots()
        t = ax.text(0.5, 0.5, "multi", **ignore("a", "b"))
        assert is_exempt(t, "a")
        assert is_exempt(t, "b")
        plt.close(fig)


# ---------------------------------------------------------------------------
# Direct attribute short-circuit: artist._scivcd_exempt = {...}
# ---------------------------------------------------------------------------

class TestDirectAttributeExemption:
    def test_direct_attribute_short_circuits_is_exempt(self):
        fig, ax = plt.subplots()
        t = ax.text(0.5, 0.5, "manual")
        t._scivcd_exempt = {"manual_check"}
        assert is_exempt(t, "manual_check")
        plt.close(fig)

    def test_direct_attribute_does_not_exempt_other_ids(self):
        fig, ax = plt.subplots()
        t = ax.text(0.5, 0.5, "manual2")
        t._scivcd_exempt = {"manual_check"}
        assert not is_exempt(t, "other_check")
        plt.close(fig)
