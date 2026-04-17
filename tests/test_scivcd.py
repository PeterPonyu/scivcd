"""Unit tests for VCD check modules (US-206).

Covers three check modules: publication, policy (severity mapping), and
baseline (diff against a pinned snapshot). Each test constructs a minimal
matplotlib figure and asserts on the check output shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import matplotlib
matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

_REPO = Path(__file__).resolve().parent.parent



# ---------------------------------------------------------------------------
# Severity mapping (US-202)
# ---------------------------------------------------------------------------

def test_severity_maps_truncation_to_critical():
    from scivcd.vcd_policy import severity_level_for
    issue = {"type": "text_truncation", "severity": "warning"}
    assert severity_level_for(issue) == "CRITICAL"


def test_severity_maps_cross_axes_overlap_to_critical():
    from scivcd.vcd_policy import severity_level_for
    issue = {"type": "cross_axes_text_overlap", "severity": "warning"}
    assert severity_level_for(issue) == "CRITICAL"


def test_severity_maps_legend_masking_to_minor():
    from scivcd.vcd_policy import severity_level_for
    issue = {"type": "legend_artist_masking", "severity": "warning"}
    assert severity_level_for(issue) == "MINOR"


def test_severity_count_aggregates_levels():
    from scivcd.vcd_policy import annotate_severity_levels, count_by_severity_level
    issues = [
        {"type": "text_truncation", "severity": "warning"},
        {"type": "text_overlap", "severity": "warning"},
        {"type": "legend_artist_masking", "severity": "warning"},
        {"type": "bold_usage", "severity": "info"},
    ]
    annotate_severity_levels(issues)
    counts = count_by_severity_level(issues)
    assert counts == {"CRITICAL": 1, "MAJOR": 1, "MINOR": 1, "INFO": 1}


# ---------------------------------------------------------------------------
# Publication-quality checks (US-204)
# ---------------------------------------------------------------------------

def test_check_minimum_font_size_flags_small_label():
    from scivcd.vcd_checks_publication import check_minimum_font_size
    # 14-inch figure rendered at 7-inch width -> scale 0.5;
    # a 10pt label renders at 5pt, below the 7pt threshold.
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.plot([0, 1], [0, 1])
    ax.set_title("Tiny", fontsize=10)
    issues = check_minimum_font_size(fig, min_pt=7.0)
    plt.close(fig)
    assert any(i["type"] == "minimum_font_size" for i in issues)


def test_check_minimum_font_size_passes_large_label():
    from scivcd.vcd_checks_publication import check_minimum_font_size
    # 7-inch figure at 7-inch include width -> scale 1.0; 12pt passes.
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot([0, 1], [0, 1])
    ax.set_title("Large Enough", fontsize=12)
    issues = check_minimum_font_size(fig, min_pt=7.0)
    plt.close(fig)
    assert not any(i["type"] == "minimum_font_size" for i in issues)


def test_check_effective_dpi_flags_low_dpi():
    from scivcd.vcd_checks_publication import check_effective_dpi
    # 14-inch figure at 300 dpi rendered at 7-inch width -> effective DPI = 600
    fig = plt.figure(figsize=(14, 8), dpi=300)
    ok = check_effective_dpi(fig, min_effective_dpi=800)
    plt.close(fig)
    assert any(i["type"] == "effective_dpi_low" for i in ok)


def test_check_effective_dpi_passes_high_dpi():
    from scivcd.vcd_checks_publication import check_effective_dpi
    fig = plt.figure(figsize=(14, 8), dpi=300)
    ok = check_effective_dpi(fig, min_effective_dpi=300)
    plt.close(fig)
    assert ok == []


def test_check_colorblind_safety_flags_red_orange():
    from scivcd.vcd_checks_publication import check_colorblind_safety
    # Muted red vs orange — the canonical deuteranopia confusion pair.
    issues = check_colorblind_safety(
        fig=plt.figure(),
        palette=[(0.8, 0.3, 0.3), (0.8, 0.5, 0.3)],
        min_delta_e=15.0,
    )
    plt.close("all")
    assert any(i["type"] == "colorblind_confusable" for i in issues)


def test_check_colorblind_safety_passes_orange_blue():
    from scivcd.vcd_checks_publication import check_colorblind_safety
    # Orange / blue are CVD-safe.
    issues = check_colorblind_safety(
        fig=plt.figure(),
        palette=[(1.0, 0.5, 0.0), (0.0, 0.45, 0.8)],
        min_delta_e=10.0,
    )
    plt.close("all")
    assert not any(i["type"] == "colorblind_confusable" for i in issues)


# ---------------------------------------------------------------------------
# Baseline diff (US-203)
# ---------------------------------------------------------------------------

def test_baseline_diff_empty_when_matched():
    from scivcd.vcd_baseline import snapshot_from_vcd_report, diff_against_baseline
    vcd = {
        "fig01.pdf": {
            "severity_counts": {"CRITICAL": 0, "MAJOR": 1, "MINOR": 0, "INFO": 0},
            "findings": [
                {"type": "text_overlap", "severity_level": "MAJOR", "detail": "a vs b"},
            ],
        }
    }
    snap = snapshot_from_vcd_report(vcd)
    report = diff_against_baseline(snap, snap)
    assert report.has_new_critical is False
    assert report.totals_added == {"CRITICAL": 0, "MAJOR": 0, "MINOR": 0, "INFO": 0}


def test_baseline_diff_flags_new_critical():
    from scivcd.vcd_baseline import diff_against_baseline
    baseline = {"figures": {"fig01.pdf": {"severity_counts": {}, "finding_keys": []}}}
    current = {
        "figures": {
            "fig01.pdf": {
                "severity_counts": {"CRITICAL": 1},
                "finding_keys": [["text_truncation", "CRITICAL", "xtick 150 truncated"]],
            }
        }
    }
    report = diff_against_baseline(current, baseline)
    assert report.has_new_critical is True
    assert report.totals_added["CRITICAL"] == 1


def test_baseline_diff_reports_removed_findings():
    from scivcd.vcd_baseline import diff_against_baseline
    baseline = {
        "figures": {
            "fig01.pdf": {
                "severity_counts": {"MAJOR": 1},
                "finding_keys": [["text_overlap", "MAJOR", "A vs B"]],
            }
        }
    }
    current = {"figures": {"fig01.pdf": {"severity_counts": {}, "finding_keys": []}}}
    report = diff_against_baseline(current, baseline)
    assert report.totals_removed["MAJOR"] == 1
    assert report.has_new_critical is False


# ---------------------------------------------------------------------------
# Complexity routing (US-301)
# ---------------------------------------------------------------------------

def test_complexity_simple_single_axes():
    from scivcd.vcd_complexity import classify_figure, Complexity
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    assert classify_figure(fig) == Complexity.SIMPLE
    plt.close(fig)


def test_complexity_compound_row():
    from scivcd.vcd_complexity import classify_figure, Complexity
    fig, axs = plt.subplots(1, 3)
    for a in axs:
        a.plot([0, 1], [0, 1])
    assert classify_figure(fig) == Complexity.COMPOUND
    plt.close(fig)


def test_complexity_composed_grid():
    from scivcd.vcd_complexity import classify_figure, Complexity
    fig, axs = plt.subplots(3, 3)
    for row in axs:
        for a in row:
            a.plot([0, 1], [0, 1])
    assert classify_figure(fig) == Complexity.COMPOSED
    plt.close(fig)


def test_complexity_composed_on_fig_legend():
    from scivcd.vcd_complexity import classify_figure, Complexity
    fig, ax = plt.subplots()
    ln, = ax.plot([0, 1], [0, 1], label="x")
    fig.legend([ln], ["X"])
    assert classify_figure(fig) == Complexity.COMPOSED
    plt.close(fig)


def test_profile_auto_routes_fewer_checks_on_simple():
    from scivcd import detect_all_conflicts
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    auto = detect_all_conflicts(fig, verbose=False, profile="auto")
    full = detect_all_conflicts(fig, verbose=False, profile="full")
    # Simple figures may hit publication checks in both, but auto should be
    # at worst equal to full — never larger.
    assert len(auto) <= len(full)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Font autofix (US-302)
# ---------------------------------------------------------------------------

def test_autofix_scales_up_on_roomy_figure():
    from scivcd.vcd_autofix import maximize_font_size
    fig, axs = plt.subplots(1, 3, figsize=(18, 6))
    fig.subplots_adjust(wspace=0.6)
    for i, a in enumerate(axs):
        a.plot([0, 1, 2], [0, 1, 0])
        a.set_title(f"P{i}", fontsize=8)
    res = maximize_font_size(fig, step=1.05, max_iter=8)
    plt.close(fig)
    assert res.scale_factor >= 1.0
    assert res.iterations >= 1


def test_autofix_returns_font_scaling_result_shape():
    from scivcd.vcd_autofix import maximize_font_size, FontScalingResult
    fig, ax = plt.subplots()
    ax.set_title("t", fontsize=10)
    res = maximize_font_size(fig)
    plt.close(fig)
    assert isinstance(res, FontScalingResult)
    assert res.scale_factor >= 1.0
    assert res.max_legible_avg_pt >= res.current_avg_pt


# ---------------------------------------------------------------------------
# Layout tightening (US-303)
# ---------------------------------------------------------------------------

def test_tighten_shrinks_over_padded_figure():
    from scivcd.vcd_tighten import tighten_layout, TightenResult
    fig, axs = plt.subplots(2, 2, figsize=(10, 8))
    fig.subplots_adjust(hspace=0.6, wspace=0.6, left=0.18, right=0.82, top=0.82, bottom=0.18)
    for row in axs:
        for a in row:
            a.plot([0, 1], [0, 1])
    before_hspace = fig.subplotpars.hspace
    res = tighten_layout(fig, step=0.04, max_iter=12)
    plt.close(fig)
    assert isinstance(res, TightenResult)
    assert res.after_params["hspace"] <= before_hspace


def test_tighten_saves_whitespace_pct_is_finite():
    from scivcd.vcd_tighten import tighten_layout
    fig, axs = plt.subplots(1, 2, figsize=(8, 4))
    fig.subplots_adjust(wspace=0.4, left=0.15, right=0.85)
    for a in axs:
        a.plot([0, 1], [0, 1])
    res = tighten_layout(fig, step=0.03)
    plt.close(fig)
    assert res.saved_whitespace_pct >= 0.0
    assert res.saved_whitespace_pct < 100.0


# ---------------------------------------------------------------------------
# Content-aware checks (US-305 fold-back)
# ---------------------------------------------------------------------------

def test_label_string_ellipsis_flags_pre_truncated_labels():
    from scivcd.vcd_checks_content import check_label_string_ellipsis
    fig, ax = plt.subplots()
    ax.bar(range(3), [1, 2, 3])
    ax.set_xticks(range(3))
    ax.set_xticklabels(["Inhibitory GABAer…", "Smooth musc…", "CD8+ T lym…"])
    fig.canvas.draw()
    issues = check_label_string_ellipsis(fig)
    plt.close(fig)
    assert any(i["type"] == "label_string_ellipsis" for i in issues)


def test_label_string_ellipsis_clean_labels_pass():
    from scivcd.vcd_checks_content import check_label_string_ellipsis
    fig, ax = plt.subplots()
    ax.bar(range(3), [1, 2, 3])
    ax.set_xticks(range(3))
    ax.set_xticklabels(["GABA", "Smooth", "CD8"])
    fig.canvas.draw()
    issues = check_label_string_ellipsis(fig)
    plt.close(fig)
    assert not any(i["type"] == "label_string_ellipsis" for i in issues)


def test_overlapping_series_flags_redundant_lines():
    from scivcd.vcd_checks_content import check_overlapping_series_values
    fig, ax = plt.subplots()
    import numpy as np
    x = np.arange(50)
    # One reference series spans 0..1 so the axis has non-zero range;
    # three coincident series all sit at the ceiling (0.99).
    ax.plot(x, x / 49.0, label="ref")
    y_ceiling = np.full_like(x, 0.99, dtype=float)
    for label in ("a", "b", "c"):
        ax.plot(x, y_ceiling, label=label)
    fig.canvas.draw()
    issues = check_overlapping_series_values(
        fig, min_series=3, coincidence_threshold=0.90, min_x_fraction=0.5
    )
    plt.close(fig)
    # The 3 ceiling series are coincident across the x-range.
    assert any(i["type"] == "overlapping_series_values" for i in issues)


def test_overlapping_series_distinct_lines_pass():
    from scivcd.vcd_checks_content import check_overlapping_series_values
    fig, ax = plt.subplots()
    import numpy as np
    x = np.linspace(0, 1, 50)
    ax.plot(x, x, label="a")
    ax.plot(x, 1 - x, label="b")
    ax.plot(x, np.sin(x * 6), label="c")
    fig.canvas.draw()
    issues = check_overlapping_series_values(fig)
    plt.close(fig)
    assert not any(i["type"] == "overlapping_series_values" for i in issues)


def test_duplicate_tick_labels_detected():
    from scivcd.vcd_checks_content import check_duplicate_tick_labels
    fig, ax = plt.subplots()
    ax.bar(range(6), [1, 2, 3, 1, 2, 3])
    ax.set_xticks(range(6))
    ax.set_xticklabels(["CLOP", "scVI", "Gaussian", "CLOP", "scVI", "Gaussian"])
    fig.canvas.draw()
    issues = check_duplicate_tick_labels(fig)
    plt.close(fig)
    assert any(i["type"] == "duplicate_tick_labels" for i in issues)


# ---------------------------------------------------------------------------
# Annotation-crowding check (scivcd follow-up 2026-04-17)
# ---------------------------------------------------------------------------

def test_annotation_crowding_flags_dense_cluster():
    from scivcd.vcd_checks_content import check_annotation_crowding
    fig, ax = plt.subplots()
    # Four annotations packed into a single axes-fraction bin (upper-right).
    for dx, label in zip([0.01, 0.02, 0.03, 0.04], ["outlier1", "outlier2", "outlier3", "outlier4"]):
        ax.annotate(label, xy=(0.88 + dx * 0.1, 0.88 + dx * 0.1), xycoords="axes fraction")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.canvas.draw()
    issues = check_annotation_crowding(fig)
    plt.close(fig)
    crowding = [i for i in issues if i["type"] == "annotation_crowding"]
    assert crowding, "expected at least one annotation_crowding finding"
    assert crowding[0]["n_annotations"] >= 3
    assert crowding[0]["severity_level"] == "MAJOR"


def test_annotation_crowding_passes_on_sparse_annotations():
    from scivcd.vcd_checks_content import check_annotation_crowding
    fig, ax = plt.subplots()
    # Four annotations spread across the four quadrants — no single bin holds >=3.
    for x, y, label in [(0.1, 0.1, "bl"), (0.9, 0.1, "br"), (0.1, 0.9, "tl"), (0.9, 0.9, "tr")]:
        ax.annotate(label, xy=(x, y), xycoords="axes fraction")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.canvas.draw()
    issues = check_annotation_crowding(fig)
    plt.close(fig)
    assert not any(i["type"] == "annotation_crowding" for i in issues)


def test_annotation_crowding_ignores_panel_labels_and_ticks():
    from scivcd.vcd_checks_content import check_annotation_crowding
    fig, ax = plt.subplots()
    # Single-character panel labels (a, b, c) clustered in the upper-left should
    # NOT trigger the rule — they are legitimate panel tags, not ad-hoc callouts.
    for label in ["a", "b", "c", "d"]:
        ax.text(0.02, 0.97, label, transform=ax.transAxes)
    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    fig.canvas.draw()
    issues = check_annotation_crowding(fig)
    plt.close(fig)
    assert not any(i["type"] == "annotation_crowding" for i in issues)


def test_annotation_crowding_handles_inverted_axes():
    """Inverted y-axis (e.g. heatmap with (N, -0.5)) must still produce
    valid axes-fraction coordinates so crowded labels are still detected."""
    from scivcd.vcd_checks_content import check_annotation_crowding
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(49.5, -0.5)  # inverted (imshow-style)
    # Four annotations packed near data-coordinate (1, 1) — upper-left in
    # display space given the inverted y.
    for dx, label in zip([0.0, 0.2, 0.4, 0.6], ["p1", "p2", "p3", "p4"]):
        ax.annotate(label, xy=(1.0 + dx, 1.0 + dx))
    fig.canvas.draw()
    issues = check_annotation_crowding(fig)
    plt.close(fig)
    assert any(i["type"] == "annotation_crowding" for i in issues), (
        "inverted axes must still flag dense clusters"
    )


def test_annotation_crowding_registered_in_severity_policy():
    from scivcd.vcd_policy import severity_level_for
    assert severity_level_for({"type": "annotation_crowding", "severity": "warning"}) == "MAJOR"


def test_annotation_crowding_in_compound_and_composed_profiles():
    from scivcd.vcd_complexity import PROFILES, Complexity
    assert "annotation_crowding" in PROFILES[Complexity.COMPOUND]
    assert "annotation_crowding" in PROFILES[Complexity.COMPOSED]
    assert "annotation_crowding" not in PROFILES[Complexity.SIMPLE]
