"""Tests for CONTENT-category checks.

Covers three named checks from the contract:
  - annotation_data_overlap
  - content_clipped_at_render
  - text_density_crowding

Each gets a positive fixture and a negative fixture.
Skips gracefully if the full check API is not yet landed.
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


def _content_findings(report):
    return [f for f in report.findings if f.category is Category.CONTENT]


def _skip_if_no_content(report):
    if not _content_findings(report) and not bool(report):
        pytest.skip("No CONTENT checks registered yet")


def _has_check(report, check_id: str) -> bool:
    return any(f.check_id == check_id for f in report.findings)


# ---------------------------------------------------------------------------
# annotation_data_overlap — text annotation sits on top of data markers
# ---------------------------------------------------------------------------

class TestAnnotationDataOverlap:
    def test_positive_annotation_on_data_point(self):
        """An annotation placed inside a bar patch triggers the check."""
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.bar([0], [1.0], width=0.8, color="#4C78A8")
        ax.text(0, 0.55, "exact overlap", ha="center", va="center", fontsize=10)
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        _skip_if_no_content(report)
        assert _has_check(report, "annotation_data_overlap")

    def test_negative_annotation_offset_from_data(self):
        """An annotation offset far from all data points produces no CONTENT finding."""
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.scatter([0.2, 0.5, 0.8], [0.2, 0.5, 0.8], s=50)
        ax.annotate(
            "offset label",
            xy=(0.5, 0.5),
            xytext=(0.8, 0.1),
            arrowprops=dict(arrowstyle="->"),
            fontsize=10,
        )
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert not _has_check(report, "annotation_data_overlap")


class TestAnnotationStyleRisk:
    def test_positive_small_colored_italic_boxed_annotation(self):
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot([0, 1], [0, 1])
        ax.text(
            0.5,
            0.5,
            "fragile note",
            transform=ax.transAxes,
            fontsize=7,
            color="tab:red",
            style="italic",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.8),
        )
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert _has_check(report, "annotation_style_risk")

    def test_negative_regular_neutral_annotation(self):
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot([0, 1], [0, 1])
        ax.text(
            0.5,
            0.5,
            "regular note",
            transform=ax.transAxes,
            fontsize=11,
            color="#222222",
            style="normal",
        )
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert not _has_check(report, "annotation_style_risk")


# ---------------------------------------------------------------------------
# content_clipped_at_render — content bounding-box extends outside axes
# ---------------------------------------------------------------------------

class TestContentClippedAtRender:
    def test_positive_text_extends_outside_axes(self):
        """A text object positioned at axes (1.1, 0.5) clips outside the axes."""
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot([0, 1], [0, 1])
        # Place text outside the axes bounding box (x=1.1 in axes coords)
        ax.text(
            1.1, 0.5, "This text is outside the axes",
            transform=ax.transAxes,
            ha="left", va="center", fontsize=10,
            clip_on=False,
        )
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        _skip_if_no_content(report)
        assert _has_check(report, "content_clipped_at_render")

    def test_negative_all_content_inside_axes(self):
        """All text within axes bounds produces no CONTENT finding."""
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.plot([0, 1], [0, 1])
        ax.text(0.5, 0.5, "Inside", transform=ax.transAxes,
                ha="center", va="center", fontsize=10)
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert not _has_check(report, "content_clipped_at_render")


# ---------------------------------------------------------------------------
# text_density_crowding — too many text objects per unit area
# ---------------------------------------------------------------------------

class TestTextDensityCrowding:
    def test_positive_dense_text_crowd(self):
        """Placing many text objects in a small figure triggers text density check."""
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        # 20 text objects densely packed in a 3×3 inch figure
        rng = np.random.default_rng(42)
        for i in range(20):
            ax.text(
                rng.uniform(0.0, 0.9),
                rng.uniform(0.0, 0.9),
                f"label_{i}",
                fontsize=9,
            )
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        _skip_if_no_content(report)
        assert _has_check(report, "text_density_crowding")

    def test_negative_sparse_labels(self):
        """A figure with only two text labels is not crowded."""
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot([0, 1, 2], [0, 1, 0])
        ax.set_xlabel("X axis")
        ax.set_ylabel("Y axis")
        fig.canvas.draw()
        report = check(fig)
        plt.close(fig)
        assert not _has_check(report, "text_density_crowding")
