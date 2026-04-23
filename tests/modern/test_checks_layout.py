"""Tests for LAYOUT-category checks.

Each check gets one positive fixture (triggers a finding) and one negative
fixture (produces no finding).  Skips gracefully if the full check API is
not yet implemented.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import pytest

# ---------------------------------------------------------------------------
# Skip-guard: we need scivcd.check and the Category enum
# ---------------------------------------------------------------------------
scivcd = pytest.importorskip(
    "scivcd",
    reason="scivcd top-level API not yet implemented",
)
if not hasattr(scivcd, "check"):
    pytest.skip("scivcd.check not yet implemented", allow_module_level=True)

from scivcd.core.types import Category

check = scivcd.check


def _has_category(report, cat: Category) -> bool:
    return any(f.category is cat for f in report.findings)


def _has_check(report, check_id: str) -> bool:
    return any(f.check_id == check_id for f in report.findings)


# ---------------------------------------------------------------------------
# axis_overflow — axis content clips outside the figure bounding box
# ---------------------------------------------------------------------------

class TestLayoutAxisOverflow:
    def test_positive_overflow_detected(self):
        """Long tick labels that extend past the figure edge trigger the check."""
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.bar(range(5), [1] * 5)
        ax.set_xticks(range(5))
        ax.set_xticklabels(
            ["Very long label A", "Very long label B", "Very long label C",
             "Very long label D", "Very long label E"],
            rotation=0, fontsize=10,
        )
        fig.subplots_adjust(bottom=0.05)   # force clipping
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        # If the check is not registered the report will be empty; skip in that case.
        if not _has_category(report, Category.LAYOUT) and not bool(report):
            pytest.skip("No LAYOUT checks registered yet")
        assert _has_category(report, Category.LAYOUT)

    def test_negative_adequate_margins(self):
        """A figure with generous margins produces no LAYOUT finding."""
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot([0, 1, 2], [0, 1, 0])
        ax.set_xlabel("X", fontsize=10)
        fig.tight_layout()
        report = check(fig)
        plt.close(fig)
        # This is a negative control — we only assert IF the check fired at all.
        # If LAYOUT checks are not yet registered, this trivially passes.
        layout_findings = [f for f in report.findings if f.category is Category.LAYOUT]
        assert len(layout_findings) == 0


# ---------------------------------------------------------------------------
# overlapping_axes — two axes whose bounding boxes overlap
# ---------------------------------------------------------------------------

class TestLayoutOverlappingAxes:
    def test_positive_axes_overlap(self):
        """Manually positioned overlapping axes trigger an overlap finding."""
        fig = plt.figure(figsize=(5, 4))
        ax1 = fig.add_axes([0.1, 0.1, 0.7, 0.7])
        ax2 = fig.add_axes([0.4, 0.4, 0.5, 0.5])   # overlaps ax1
        ax1.plot([0, 1], [0, 1])
        ax2.plot([0, 1], [1, 0])
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        if not _has_category(report, Category.LAYOUT) and not bool(report):
            pytest.skip("No LAYOUT checks registered yet")
        assert _has_category(report, Category.LAYOUT)

    def test_negative_non_overlapping_axes(self):
        """Side-by-side axes (no overlap) produce no LAYOUT finding."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4))
        ax1.plot([0, 1], [0, 1])
        ax2.plot([0, 1], [1, 0])
        fig.tight_layout()
        report = check(fig)
        plt.close(fig)
        layout_findings = [f for f in report.findings if f.category is Category.LAYOUT]
        assert len(layout_findings) == 0


# ---------------------------------------------------------------------------
# colorbar_too_wide — colorbar width > 10% of its parent axes
# ---------------------------------------------------------------------------

class TestLayoutColorbarTooWide:
    def test_positive_wide_colorbar(self):
        """A colorbar with pad=0.3 fraction=0.3 is unusually wide."""
        fig, ax = plt.subplots(figsize=(5, 4))
        data = np.random.default_rng(0).random((8, 8))
        im = ax.imshow(data)
        fig.colorbar(im, ax=ax, fraction=0.3, pad=0.3)
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        if not _has_category(report, Category.LAYOUT) and not bool(report):
            pytest.skip("No LAYOUT checks registered yet")
        assert _has_category(report, Category.LAYOUT)

    def test_negative_standard_colorbar(self):
        """A standard colorbar (fraction=0.046) produces no LAYOUT finding."""
        fig, ax = plt.subplots(figsize=(5, 4))
        data = np.random.default_rng(1).random((8, 8))
        im = ax.imshow(data)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        report = check(fig)
        plt.close(fig)
        layout_findings = [f for f in report.findings if f.category is Category.LAYOUT]
        assert len(layout_findings) == 0


class TestLayoutSuptitleGap:
    def test_positive_suptitle_far_from_axes(self):
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot([0, 1], [0, 1])
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_position([0.15, 0.10, 0.75, 0.55])
        fig.suptitle("Floating title", y=0.98)
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert _has_check(report, "suptitle_too_far_from_axes")

    def test_negative_suptitle_close_to_axes(self):
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot([0, 1], [0, 1])
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_position([0.15, 0.10, 0.75, 0.78])
        fig.suptitle("Close title", y=0.92)
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert not _has_check(report, "suptitle_too_far_from_axes")


class TestLayoutPanelRowAlignment:
    def test_positive_row_misalignment(self):
        fig = plt.figure(figsize=(6, 3))
        ax1 = fig.add_axes([0.10, 0.20, 0.35, 0.60])
        ax2 = fig.add_axes([0.47, 0.28, 0.20, 0.50])
        ax3 = fig.add_axes([0.70, 0.20, 0.20, 0.60])
        ax1.plot([0, 1], [0, 1])
        ax2.plot([0, 1], [1, 0])
        ax3.plot([0, 1], [0.5, 0.5])
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert _has_check(report, "panel_row_misalignment")

    def test_negative_row_aligned(self):
        fig = plt.figure(figsize=(6, 3))
        ax1 = fig.add_axes([0.10, 0.20, 0.25, 0.60])
        ax2 = fig.add_axes([0.40, 0.20, 0.25, 0.60])
        ax3 = fig.add_axes([0.70, 0.20, 0.20, 0.60])
        ax1.plot([0, 1], [0, 1])
        ax2.plot([0, 1], [1, 0])
        ax3.plot([0, 1], [0.5, 0.5])
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert not _has_check(report, "panel_row_misalignment")


class TestLayoutLegendTickClearance:
    def test_positive_legend_too_close_to_xticks(self):
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot([0, 1], [0, 1], label="A")
        ax.plot([0, 1], [1, 0], label="B")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.02), frameon=False)
        fig.subplots_adjust(bottom=0.20)
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert _has_check(report, "legend_tick_clearance")

    def test_negative_legend_clear_of_ticks(self):
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot([0, 1], [0, 1], label="A")
        ax.plot([0, 1], [1, 0], label="B")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), frameon=False)
        fig.subplots_adjust(bottom=0.32)
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert not _has_check(report, "legend_tick_clearance")
