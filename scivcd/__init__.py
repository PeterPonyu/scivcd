"""Visual Conflict Detector (VCD) — modular package.

Usage::

    from vcd import detect_all_conflicts, summarize_issues

    issues = detect_all_conflicts(fig, label="my_panel", verbose=True)
"""

from __future__ import annotations

from .vcd_core import (
    _ArtistInfo,
    _collect_artists,
    _fig_bbox,
    _safe_bbox,
    _overlap_area,
    _is_colorbar_axes,
)
from .vcd_checks_text import (
    _check_text_overlaps,
    _check_text_vs_artist_overlap,
    _check_cross_panel_spillover,
    _check_panel_label_overlap,
)
from .vcd_checks_artists import (
    _check_truncation,
    _check_artist_content_overlap,
    _check_axes_overflow,
    _check_scatter_clip_risk,
)
from .vcd_checks_legend import (
    _check_legend_spillover,
    _check_legend_vs_other_panel_content,
    _check_legend_vs_own_content,
    _check_fig_legend_vs_subplot_content,
    _check_legend_internal,
    _check_legend_crowding_autofix,
    _check_legend_vs_legend,
    _check_legend_vs_other_artists,
)
from .vcd_checks_colorbar import (
    _check_colorbar_internal,
    _check_colorbar_data_overlap,
)
from .vcd_checks_structure import (
    _check_significance_brackets,
    _per_axes_summary,
)
from .vcd_checks_layout import (
    _check_fontsize_adequacy,
    _check_tick_spine_overlap,
    _check_font_policy,
    _check_label_density,
    _check_cross_axes_text_overlap,
    _check_panel_label_placement,
)
from .vcd_checks_perceptual import (
    _check_contrast,
    _check_colorblind_safety,
    _check_errorbar_visibility,
    _check_precision_excess,
)
from .vcd_checks_semantic import (
    _check_overplotting,
    _check_log_scale_sanity,
    _check_scale_consistency,
    _check_floating_significance,
    _check_panel_complexity,
)
from .vcd_checks_publication import (
    check_minimum_font_size as _check_minimum_font_size,
    check_colorblind_safety as _check_colorblind_safety_pub,
    check_effective_dpi as _check_effective_dpi,
)
from .vcd_checks_content import (
    check_label_string_ellipsis as _check_label_string_ellipsis,
    check_overlapping_series_values as _check_overlapping_series_values,
    check_duplicate_tick_labels as _check_duplicate_tick_labels,
    check_annotation_crowding as _check_annotation_crowding,
)
from .vcd_config import (
    MIN_PT,
    COMPOSED_SCALE,
    DENSE_LABEL_MIN_PT,
    ALLOWED_FONT_FAMILIES,
    MAX_TITLE_LABEL_SIZE_DIFF,
    LABEL_DENSITY_THRESHOLD,
    MIN_TEXT_CONTRAST,
    MIN_LINE_CONTRAST,
    MIN_CVD_DISTANCE,
    CVD_MAX_CATEGORIES,
    ERRORBAR_TARGET_DPI,
    ERRORBAR_MIN_CAP_PX,
    MAX_DECIMAL_PLACES,
    OVERPLOT_ALPHA_THRESHOLD,
    OVERPLOT_OPAQUE_THRESHOLD,
    SCALE_RANGE_SPREAD_FACTOR,
    SIGNIFICANCE_PROXIMITY_PX,
    MAX_LEGEND_SERIES,
    MAX_NUMERIC_BAR_LABELS,
    MAX_ANNOTATIONS_COMPLEXITY,
    COMPLEXITY_SCORE_THRESHOLD,
    CROSS_AXES_TEXT_OVERLAP_TOL_PX,
    CROSS_AXES_TEXT_OVERLAP_MIN_PX2,
    PANEL_LABEL_PLACEMENT_MARGIN_PX,
)


def _issue_sort_key(issue: dict) -> tuple[int, str, str]:
    severity_rank = {
        "warning": 0,
        "info": 1,
    }
    severity = str(issue.get("severity", "info")).lower()
    return (
        severity_rank.get(severity, 2),
        str(issue.get("type", "")),
        str(issue.get("detail", "")),
    )


def sort_issues(issues: list[dict]) -> list[dict]:
    """Return issues in a stable severity/type/detail order."""
    return sorted(issues, key=_issue_sort_key)


def detect_all_conflicts(
    fig,
    label: str = "",
    verbose: bool = True,
    text_overlap_tol_px: float = 2.5,
    border_tol_px: float = 2.0,
    artist_overlap_min_px2: float = 200.0,
    text_artist_overlap_min_px2: float = 150.0,
    profile: str = "full",
):
    """Run all visual conflict detection passes on a matplotlib figure.

    Four-layer detection:
      Layer 1 (subplot-level):   passes 12-13, per-axes summary
      Layer 2 (figure-level):    passes 1-11, 14-22, 32-33
      Layer 3 (perceptual):      passes 23-26
      Layer 4 (semantic):        passes 27-31

    Parameters
    ----------
    fig : matplotlib.figure.Figure
    label : str
        Descriptive label for log messages.
    verbose : bool
        Print diagnostic summary to stdout.
    text_overlap_tol_px : float
        Shrink text bboxes by this many pixels before overlap test.
    border_tol_px : float
        Tolerance for border truncation checks.
    artist_overlap_min_px2 : float
        Minimum overlap area (px^2) to report graphical artist overlap.
    text_artist_overlap_min_px2 : float
        Minimum overlap area (px^2) to report text-vs-artist overlap.

    Returns
    -------
    list[dict]
        Each dict has ``type``, ``severity``, ``detail``, ``elements``.
    """
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
    except Exception:
        return []

    fig_bb = _fig_bbox(fig)
    infos = _collect_artists(fig, renderer)

    # US-301: pick the active pass set based on the requested profile
    from .vcd_complexity import select_passes
    active = set(select_passes(profile, fig=fig))
    def _run(name: str) -> bool:
        return (profile == "full") or (name in active)

    issues = []
    # ── Layer 2: figure-level passes (1-11) ──
    if _run("text_overlaps"):
        issues.extend(_check_text_overlaps(infos, text_overlap_tol_px))
    if _run("truncation"):
        issues.extend(_check_truncation(infos, fig_bb, border_tol_px, fig=fig, renderer=renderer))
    if _run("artist_content_overlap"):
        issues.extend(_check_artist_content_overlap(infos, artist_overlap_min_px2))
    issues.extend(_check_text_vs_artist_overlap(
        infos, text_overlap_tol_px, text_artist_overlap_min_px2))
    issues.extend(_check_axes_overflow(infos, fig))
    issues.extend(_check_scatter_clip_risk(fig))
    # Passes 8-10
    issues.extend(_check_cross_panel_spillover(fig, renderer))
    issues.extend(_check_panel_label_overlap(fig, renderer, infos))
    issues.extend(_check_legend_spillover(fig, renderer))
    # Pass 11
    issues.extend(_check_legend_vs_other_panel_content(fig, renderer, infos))
    issues.extend(_check_legend_vs_legend(fig, renderer))
    issues.extend(_check_legend_vs_other_artists(fig, renderer, infos))
    # ── Layer 1: subplot-level passes (12-15) ──
    issues.extend(_check_legend_vs_own_content(fig, renderer, infos))
    issues.extend(_check_fig_legend_vs_subplot_content(fig, renderer, infos))
    issues.extend(_check_colorbar_internal(fig, renderer))
    issues.extend(_check_legend_internal(fig, renderer))
    # Pass 16: significance brackets
    issues.extend(_check_significance_brackets(fig, renderer, border_tol_px))
    # Pass 17: colorbar-vs-data overlap
    issues.extend(_check_colorbar_data_overlap(fig, renderer))
    # Pass 18: legend crowding auto-fix
    issues.extend(_check_legend_crowding_autofix(fig, renderer))
    # Pass 19: font-size adequacy
    issues.extend(_check_fontsize_adequacy(
        fig, renderer, infos,
        min_pt=MIN_PT, composed_scale=COMPOSED_SCALE,
        dense_label_min_pt=DENSE_LABEL_MIN_PT))
    # Pass 20: tick/spine overlap (NEW)
    issues.extend(_check_tick_spine_overlap(fig, renderer))
    # Pass 21: font policy (NEW)
    issues.extend(_check_font_policy(
        fig, renderer, infos,
        allowed_families=ALLOWED_FONT_FAMILIES,
        max_title_label_diff=MAX_TITLE_LABEL_SIZE_DIFF))
    # Pass 22: label density excess
    issues.extend(_check_label_density(
        fig, renderer, infos,
        density_threshold=LABEL_DENSITY_THRESHOLD))

    # ── Layer 3: perceptual passes (23-26) ──
    # Pass 23: contrast check
    issues.extend(_check_contrast(
        fig, renderer, infos,
        min_text_contrast=MIN_TEXT_CONTRAST,
        min_line_contrast=MIN_LINE_CONTRAST))
    # Pass 24: colorblind safety
    issues.extend(_check_colorblind_safety(
        fig, renderer,
        min_cvd_distance=MIN_CVD_DISTANCE,
        max_categories=CVD_MAX_CATEGORIES))
    # Pass 25: error-bar visibility
    issues.extend(_check_errorbar_visibility(
        fig, renderer,
        target_dpi=ERRORBAR_TARGET_DPI,
        min_cap_px=ERRORBAR_MIN_CAP_PX))
    # Pass 26: precision excess
    issues.extend(_check_precision_excess(
        fig, renderer, infos,
        max_decimals=MAX_DECIMAL_PLACES))

    # ── Layer 4: semantic passes (27-30) ──
    # Pass 27: overplotting
    issues.extend(_check_overplotting(
        fig, renderer,
        alpha_point_threshold=OVERPLOT_ALPHA_THRESHOLD,
        opaque_point_threshold=OVERPLOT_OPAQUE_THRESHOLD))
    # Pass 28: log-scale sanity
    issues.extend(_check_log_scale_sanity(fig, renderer))
    # Pass 29: scale consistency
    issues.extend(_check_scale_consistency(fig, renderer))
    # Pass 30: floating significance markers
    issues.extend(_check_floating_significance(
        fig, renderer,
        proximity_px=SIGNIFICANCE_PROXIMITY_PX))
    # Pass 31: panel complexity excess
    issues.extend(_check_panel_complexity(
        fig, renderer,
        max_legend_series=MAX_LEGEND_SERIES,
        max_numeric_labels=MAX_NUMERIC_BAR_LABELS,
        max_annotations=MAX_ANNOTATIONS_COMPLEXITY,
        score_threshold=COMPLEXITY_SCORE_THRESHOLD))

    # ── Layer 2 continued: new layout passes (32-33) ──
    # Pass 32: cross-axes text overlap (xlabel vs title between rows)
    issues.extend(_check_cross_axes_text_overlap(
        fig, renderer,
        tol_px=CROSS_AXES_TEXT_OVERLAP_TOL_PX,
        min_overlap_px2=CROSS_AXES_TEXT_OVERLAP_MIN_PX2))
    # Pass 33: panel label placement (inside vs outside axes)
    issues.extend(_check_panel_label_placement(
        fig, renderer,
        margin_px=PANEL_LABEL_PLACEMENT_MARGIN_PX))

    # ── Layer 5: publication-quality policy checks (34-36, US-204) ──
    # Pass 34: minimum rendered font size at \includegraphics width
    try:
        issues.extend(_check_minimum_font_size(fig))
    except Exception:
        pass
    # Pass 35: colorblind safety via Machado 2009 CVD matrices
    try:
        issues.extend(_check_colorblind_safety_pub(fig))
    except Exception:
        pass
    # Pass 36: effective DPI at rendered width
    try:
        issues.extend(_check_effective_dpi(fig))
    except Exception:
        pass

    # ── Layer 6: content-aware checks (37-39, US-305 fold-back) ──
    # Pass 37: label string ellipsis — producer pre-truncated label content
    try:
        issues.extend(_check_label_string_ellipsis(fig))
    except Exception:
        pass
    # Pass 38: overlapping series values — 3+ lines collapsed on same y
    try:
        issues.extend(_check_overlapping_series_values(fig))
    except Exception:
        pass
    # Pass 39: duplicate tick labels
    try:
        issues.extend(_check_duplicate_tick_labels(fig))
    except Exception:
        pass
    # Pass 40: annotation crowding (post-2026-04-17 scivcd follow-up rule)
    if _run("annotation_crowding"):
        try:
            issues.extend(_check_annotation_crowding(fig))
        except Exception:
            pass

    issues = sort_issues(issues)

    # US-202: annotate each issue with a 4-level severity (CRITICAL/MAJOR/MINOR/INFO)
    from .vcd_policy import annotate_severity_levels
    annotate_severity_levels(issues)

    # Two-layer per-axes summary
    per_ax = _per_axes_summary(fig, renderer, infos)

    if verbose:
        print_conflict_summary(issues, per_ax, label=label)

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# CLI output helpers — separated from detection core
# ═══════════════════════════════════════════════════════════════════════════════

def print_conflict_summary(
    issues: list[dict],
    per_ax: dict[str, list[dict]] | None = None,
    *,
    label: str = "",
    max_items: int = 25,
) -> None:
    """Print a human-readable conflict summary to stdout.

    This is the sole CLI-printing entry point.  The detection core
    (``detect_all_conflicts``) calls it only when *verbose=True*,
    but it is also available stand-alone (e.g. for notebooks or CI).

    Parameters
    ----------
    issues : list[dict]
        Output of ``detect_all_conflicts``.
    per_ax : dict | None
        Per-axes summary dict (from ``_per_axes_summary``).
    label : str
        Descriptive tag for the output.
    max_items : int
        Maximum individual issues to print before truncating.
    """
    tag = f" [{label}]" if label else ""
    n_warn = sum(1 for x in issues if x["severity"] == "warning")
    n_info = sum(1 for x in issues if x["severity"] == "info")

    counts: dict[str, int] = {}
    for iss in issues:
        counts[iss["type"]] = counts.get(iss["type"], 0) + 1

    # Layer 1: subplot-level warnings
    subplot_warns: dict[str, list[dict]] = {}
    if per_ax:
        for t, iss in per_ax.items():
            warns = [i for i in iss if i.get("severity") == "warning"]
            if warns:
                subplot_warns[t] = warns

    if subplot_warns:
        print(f"  -- Layer 1 (subplot-level){tag} --")
        for title, ax_iss in subplot_warns.items():
            for i in ax_iss:
                print(f"    [warn] {i['detail']}")

    # Layer 2+: figure-level issues
    if n_warn > 0 or subplot_warns:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  -- Layer 2 (figure-level){tag} --")
        print(f"  CONFLICT: {n_warn} warnings, {n_info} info [{parts}]")
        for iss in issues[:max_items]:
            marker = "[warn]" if iss["severity"] == "warning" else "[info]"
            print(f"    {marker} [{iss['type']}] {iss['detail']}")
        if len(issues) > max_items:
            print(f"    ... and {len(issues) - max_items} more")
    elif n_info > 0:
        print(f"  INFO{tag}: 0 warnings, {n_info} info")
    elif label:
        print(f"  OK{tag}: no conflicts detected (all layers clean)")

    return issues


def detect_conflicts_in_file(
    png_path: str,
    label: str = "",
    verbose: bool = True,
) -> list[dict]:
    """File-path audit is not implemented; live figure-time audit is authoritative."""
    if verbose:
        print(
            "  NOTE: file-path VCD audit is not implemented; "
            f"use detect_all_conflicts(fig) during generation for '{png_path}'."
        )
    return []


def summarize_issues(all_issues: dict[str, list[dict]]) -> None:
    """Print final audit summary across multiple figures."""
    total_warn = 0
    total_info = 0
    problem_figs = []
    for name, issues in all_issues.items():
        n_w = sum(1 for x in issues if x["severity"] == "warning")
        n_i = sum(1 for x in issues if x["severity"] == "info")
        total_warn += n_w
        total_info += n_i
        if n_w > 0:
            problem_figs.append(name)

    print(f"\n{'=' * 60}")
    print(f"CONFLICT AUDIT SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Figures checked: {len(all_issues)}")
    print(f"  Total warnings:  {total_warn}")
    print(f"  Total info:      {total_info}")
    if problem_figs:
        print(f"  Figures with warnings: {', '.join(problem_figs)}")
    else:
        print(f"  All figures clean -- no warnings detected")
    print(f"{'=' * 60}\n")


from .vcd_policy import (
    FigurePolicy,
    DEFAULT_POLICY,
    SEVERITY_CRITICAL,
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    SEVERITY_INFO,
    SEVERITY_LEVELS,
    severity_level_for,
    annotate_severity_levels,
    count_by_severity_level,
)
from .vcd_actions import Action, diagnose, group_by_category

__all__ = [
    "detect_all_conflicts",
    "detect_conflicts_in_file",
    "summarize_issues",
    "print_conflict_summary",
    "sort_issues",
    "FigurePolicy",
    "DEFAULT_POLICY",
    "SEVERITY_CRITICAL",
    "SEVERITY_MAJOR",
    "SEVERITY_MINOR",
    "SEVERITY_INFO",
    "SEVERITY_LEVELS",
    "severity_level_for",
    "annotate_severity_levels",
    "count_by_severity_level",
    "Action",
    "diagnose",
    "group_by_category",
]
