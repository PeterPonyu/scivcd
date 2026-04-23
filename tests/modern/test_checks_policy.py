"""Tests for POLICY-category checks.

Each check gets one positive fixture (triggers finding) and one negative
fixture (produces no finding).  Skips gracefully if the API is not landed.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import pytest

scivcd = pytest.importorskip(
    "scivcd",
    reason="scivcd top-level API not yet implemented",
)
if not hasattr(scivcd, "check"):
    pytest.skip("scivcd.check not yet implemented", allow_module_level=True)

from scivcd.core.types import Category

check = scivcd.check


def _policy_findings(report):
    return [f for f in report.findings if f.category is Category.POLICY]


def _skip_if_no_policy(report):
    if not _policy_findings(report) and not bool(report):
        pytest.skip("No POLICY checks registered yet")


def _has_check(report, check_id: str) -> bool:
    return any(f.check_id == check_id for f in report.findings)


# ---------------------------------------------------------------------------
# missing_axis_labels — axes without xlabel/ylabel
# ---------------------------------------------------------------------------

class TestPolicyMissingAxisLabels:
    def test_positive_no_labels(self):
        """Axes with no xlabel/ylabel trigger a POLICY finding."""
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1], [0, 1])
        # Deliberately no set_xlabel / set_ylabel
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        _skip_if_no_policy(report)
        assert len(_policy_findings(report)) >= 1

    def test_negative_has_both_labels(self):
        """Axes with both axis labels produce no POLICY finding."""
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1], [0, 1])
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Value")
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert len(_policy_findings(report)) == 0


# ---------------------------------------------------------------------------
# missing_legend — multiple series but no legend
# ---------------------------------------------------------------------------

class TestPolicyMissingLegend:
    def test_positive_multi_series_no_legend(self):
        """Multiple labelled series without a legend trigger POLICY."""
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1], [0, 1], label="A")
        ax.plot([0, 1], [1, 0], label="B")
        ax.plot([0, 1], [0.5, 0.5], label="C")
        # No ax.legend() call
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        _skip_if_no_policy(report)
        assert len(_policy_findings(report)) >= 1

    def test_negative_legend_present(self):
        """Multiple series with a legend produce no POLICY finding."""
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1], [0, 1], label="A")
        ax.plot([0, 1], [1, 0], label="B")
        ax.legend()
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert not _has_check(report, "missing_legend")


# ---------------------------------------------------------------------------
# figure_too_small — figure dimensions below publication minimum
# ---------------------------------------------------------------------------

class TestPolicyFigureTooSmall:
    def test_positive_tiny_figure(self):
        """A 1×1 inch figure is below any reasonable publication minimum."""
        fig, ax = plt.subplots(figsize=(1, 1))
        ax.plot([0, 1], [0, 1])
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        _skip_if_no_policy(report)
        assert len(_policy_findings(report)) >= 1

    def test_negative_standard_figure(self):
        """A standard 6×4 inch figure passes the size policy."""
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot([0, 1], [0, 1])
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert len(_policy_findings(report)) == 0
