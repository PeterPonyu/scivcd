"""VCD actions: warning-to-action translation layer.

Maps VCD issue dicts (from ``detect_all_conflicts``) to concrete
``Action`` objects that describe suggested configuration adjustments
for resolving each visual conflict.

Usage::

    from vcd.vcd_actions import diagnose, group_by_category

    issues = detect_all_conflicts(fig)
    actions = diagnose(issues)
    grouped = group_by_category(actions)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


# ═══════════════════════════════════════════════════════════════════════════════
# Action dataclass
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Action:
    """A suggested configuration adjustment to resolve a VCD issue.

    Parameters
    ----------
    action_type : str
        Machine-readable action identifier (e.g. ``"reduce_tick_labels"``,
        ``"move_legend"``, ``"increase_figsize"``).
    target : str
        The visual element targeted by this action (e.g. ``"xticks"``,
        ``"legend"``, ``"figure"``, ``"annotations"``).
    params : dict
        Action-specific parameters.  Contents depend on *action_type*.
    priority : int
        Urgency: 1 = high, 2 = medium, 3 = low.
    description : str
        Human-readable explanation of what the action does and why.
    """

    action_type: str
    target: str
    params: dict = field(default_factory=dict)
    priority: int = 2
    description: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Action generator helpers (one per issue family)
# ═══════════════════════════════════════════════════════════════════════════════

def _actions_text_overlap(issue: dict) -> list[Action]:
    """Generate actions for ``text_overlap`` issues."""
    elements = issue.get("elements", [])
    joined = " ".join(elements).lower()
    actions: list[Action] = []

    if "xtick" in joined:
        actions.append(Action(
            action_type="reduce_tick_labels",
            target="xticks",
            params={"strategy": "maxn", "max_labels": 6},
            priority=1,
            description=(
                "Reduce the number of x-axis tick labels to avoid overlap. "
                "Consider using MaxNLocator or manually selecting key ticks."
            ),
        ))
        actions.append(Action(
            action_type="rotate_labels",
            target="xticks",
            params={"rotation": 45, "ha": "right"},
            priority=2,
            description=(
                "Rotate x-axis tick labels to reduce horizontal footprint."
            ),
        ))
    elif "annotation" in joined:
        actions.append(Action(
            action_type="reduce_annotations",
            target="annotations",
            params={
                "strategy": "tiered",
                # Drop order: remove redundant/duplicate labels first, then
                # secondary labels, only remove primary labels as last resort.
                "drop_order": ["redundant", "secondary", "primary"],
                # Semantic integrity: keep at least this many chars per label
                # and never remove labels containing protected prefixes (↑/↓).
                "min_label_chars": 12,
                "preserve_sign_prefix": True,
            },
            priority=1,
            description=(
                "Reduce annotation density to prevent overlapping text. "
                "Remove redundant duplicates first, then secondary labels; "
                "preserve at least 12 chars and leading sign/arrow prefixes."
            ),
        ))
    elif "title" in joined or "suptitle" in joined:
        actions.append(Action(
            action_type="increase_hspace",
            target="figure",
            params={"delta": 0.05},
            priority=1,
            description=(
                "Increase vertical spacing (hspace) between subplots so "
                "titles do not collide with neighbouring panel content."
            ),
        ))
    else:
        actions.append(Action(
            action_type="increase_figsize",
            target="figure",
            params={"delta_width": 1.0, "delta_height": 1.0},
            priority=2,
            description=(
                "Enlarge the overall figure to give text elements more room."
            ),
        ))

    return actions


def _actions_text_truncation(issue: dict) -> list[Action]:
    """Generate actions for ``text_truncation`` issues.
    """
    detail = issue.get("detail", "").lower()
    actions: list[Action] = []

    if "bottom" in detail:
        actions.append(Action(
            action_type="increase_bottom_margin",
            target="figure",
            params={"subplots_adjust": {"bottom": 0.15}},
            priority=1,
            description=(
                "Increase bottom margin so that x-axis labels and tick "
                "labels are not clipped at the figure edge."
            ),
        ))
        actions.append(Action(
            action_type="increase_figsize_height",
            target="figure",
            params={"delta_height": 0.5},
            priority=2,
            description=(
                "Increase figure height to accommodate bottom-edge text."
            ),
        ))
    elif "right" in detail:
        actions.append(Action(
            action_type="increase_right_margin",
            target="figure",
            params={"subplots_adjust": {"right": 0.90}},
            priority=1,
            description=(
                "Increase right margin so right-side labels are not truncated."
            ),
        ))
        actions.append(Action(
            action_type="increase_figsize_width",
            target="figure",
            params={"delta_width": 0.5},
            priority=2,
            description=(
                "Increase figure width to accommodate right-edge text."
            ),
        ))
    elif "top" in detail:
        actions.append(Action(
            action_type="increase_top_margin",
            target="figure",
            params={"subplots_adjust": {"top": 0.92}},
            priority=1,
            description=(
                "Increase top margin to prevent title or suptitle truncation."
            ),
        ))
    else:
        # Fallback: could be left or ambiguous
        actions.append(Action(
            action_type="increase_margins",
            target="figure",
            params={"subplots_adjust": {"left": 0.12, "right": 0.90,
                                         "top": 0.92, "bottom": 0.15}},
            priority=2,
            description=(
                "Widen figure margins on all sides to prevent text truncation."
            ),
        ))

    return actions


def _actions_patch_truncation(issue: dict) -> list[Action]:
    """Generate actions for ``patch_truncation`` issues."""
    detail = issue.get("detail", "").lower()
    actions: list[Action] = []

    delta_w = 1.0 if ("left" in detail or "right" in detail) else 0.0
    delta_h = 1.0 if ("top" in detail or "bottom" in detail) else 0.0
    # Ensure at least one dimension grows
    if delta_w == 0.0 and delta_h == 0.0:
        delta_w, delta_h = 0.5, 0.5

    actions.append(Action(
        action_type="increase_figsize",
        target="figure",
        params={"delta_width": delta_w, "delta_height": delta_h},
        priority=2,
        description=(
            "Increase figure size in the truncated direction so graphical "
            "elements (bars, patches) are fully visible."
        ),
    ))
    return actions


def _actions_legend_data_occlusion(issue: dict) -> list[Action]:
    """Generate actions for ``legend_data_occlusion`` issues."""
    return [
        Action(
            action_type="move_legend",
            target="legend",
            params={
                "preferred_locs": [
                    "center left",
                    "center right",
                    "upper left",
                    "upper right",
                    "lower left",
                    "lower right",
                ],
                "allow_outside_axes": True,
                "frameon": False,
            },
            priority=1,
            description=(
                "Move the legend to a location that does not occlude data "
                "content.  Try each preferred location until occlusion is "
                "minimised."
            ),
        ),
        Action(
            action_type="shrink_legend_font",
            target="legend",
            params={"min_fontsize": 7},
            priority=2,
            description=(
                "Reduce legend font size to shrink its footprint and "
                "reduce occlusion of underlying data."
            ),
        ),
    ]


def _actions_legend_spillover(issue: dict) -> list[Action]:
    """Generate actions for ``legend_spillover`` issues."""
    return [
        Action(
            action_type="move_legend_inside",
            target="legend",
            params={"loc": "best", "frameon": False},
            priority=1,
            description=(
                "Move the legend inside the axes bounds to prevent it from "
                "spilling into neighbouring panels."
            ),
        ),
        Action(
            action_type="increase_figsize",
            target="figure",
            params={"delta_width": 1.0, "delta_height": 0.5},
            priority=2,
            description=(
                "Increase figure size to provide enough room for the legend "
                "without it spilling into adjacent panels."
            ),
        ),
    ]


def _actions_legend_truncation(issue: dict) -> list[Action]:
    """Generate actions for ``legend_truncation`` issues."""
    return [
        Action(
            action_type="move_legend_inside",
            target="legend",
            params={"loc": "best", "frameon": False},
            priority=1,
            description=(
                "Move the legend fully inside the figure/axes bounds to "
                "prevent clipping at the figure edge."
            ),
        ),
        Action(
            action_type="increase_figsize",
            target="figure",
            params={"delta_width": 0.5, "delta_height": 0.5},
            priority=2,
            description=(
                "Increase figure size so the legend fits without being "
                "truncated at the border."
            ),
        ),
    ]


def _actions_legend_text_crowding(issue: dict) -> list[Action]:
    """Generate actions for ``legend_text_crowding`` issues."""
    return [
        Action(
            action_type="shrink_legend_font",
            target="legend",
            params={"min_fontsize": 6},
            priority=1,
            description=(
                "Reduce legend font size so entries fit without crowding."
            ),
        ),
        Action(
            action_type="reduce_legend_entries",
            target="legend",
            params={"strategy": "top_n", "max_entries": 8},
            priority=2,
            description=(
                "Reduce the number of legend entries to the most important "
                "ones and rely on the caption for the rest."
            ),
        ),
    ]


def _actions_fontsize_too_small(issue: dict) -> list[Action]:
    """Generate actions for ``fontsize_too_small`` issues."""
    return [
        Action(
            action_type="increase_fontsize",
            target="text",
            params={"min_body_pt": 7.0, "increment_pt": 1.0},
            priority=1,
            description=(
                "Increase font size of undersized text elements.  Body text "
                "should be at least 7 pt for legibility at print scale."
            ),
        ),
    ]


def _actions_cross_panel_spillover(issue: dict) -> list[Action]:
    """Generate actions for ``cross_panel_spillover`` issues."""
    return [
        Action(
            action_type="increase_wspace",
            target="figure",
            params={"delta": 0.05},
            priority=1,
            description=(
                "Increase horizontal spacing (wspace) between subplots to "
                "prevent elements from one panel spilling into another."
            ),
        ),
        Action(
            action_type="increase_figsize_width",
            target="figure",
            params={"delta_width": 1.0},
            priority=2,
            description=(
                "Increase figure width to give panels more breathing room."
            ),
        ),
    ]


def _actions_cbar_tick_overlap(issue: dict) -> list[Action]:
    """Generate actions for ``cbar_tick_overlap`` issues."""
    return [
        Action(
            action_type="reduce_cbar_ticks",
            target="colorbar",
            params={"max_ticks": 5},
            priority=1,
            description=(
                "Reduce the number of colorbar tick labels to eliminate "
                "overlap.  Use MaxNLocator or a manual tick list."
            ),
        ),
    ]


def _actions_cbar_tick_truncation(issue: dict) -> list[Action]:
    """Generate actions for ``cbar_tick_truncation`` issues."""
    return [
        Action(
            action_type="increase_figsize",
            target="figure",
            params={"delta_width": 0.5, "delta_height": 0.0},
            priority=2,
            description=(
                "Increase figure size to prevent colorbar tick labels from "
                "being clipped at the figure edge."
            ),
        ),
        Action(
            action_type="adjust_cbar_pad",
            target="colorbar",
            params={"pad": 0.15},
            priority=1,
            description=(
                "Increase colorbar padding to move it inward and avoid "
                "tick label truncation at the figure border."
            ),
        ),
    ]


def _actions_artist_overlap(issue: dict) -> list[Action]:
    """Generate actions for ``artist_overlap`` issues."""
    return [
        Action(
            action_type="increase_wspace",
            target="figure",
            params={"delta": 0.05},
            priority=1,
            description=(
                "Increase horizontal spacing between panels to prevent "
                "graphical artists from overlapping across axes."
            ),
        ),
        Action(
            action_type="increase_figsize",
            target="figure",
            params={"delta_width": 1.0, "delta_height": 0.5},
            priority=2,
            description=(
                "Enlarge the figure to reduce cross-panel artist overlap."
            ),
        ),
    ]


def _actions_tick_spine_overlap(issue: dict) -> list[Action]:
    """Generate actions for ``tick_spine_overlap`` issues."""
    return [
        Action(
            action_type="increase_margins",
            target="figure",
            params={"tick_params": {"pad": 4}},
            priority=2,
            description=(
                "Increase tick padding or figure margins so tick labels "
                "do not collide with axis spines."
            ),
        ),
    ]


def _actions_font_family_violation(issue: dict) -> list[Action]:
    """Generate actions for ``font_family_violation`` issues."""
    return [
        Action(
            action_type="fix_font_family",
            target="text",
            params={"family": "Arial"},
            priority=1,
            description=(
                "Set all text elements to Arial to comply with the journal "
                "font-family policy."
            ),
        ),
    ]


def _actions_label_density_excess(issue: dict) -> list[Action]:
    """Generate actions for ``label_density_excess`` issues.

    This produces escalating actions:
    1. First try reducing tick labels and rotating them.
    2. If the density is very high (>90%), also suggest reducing
       subplots per row — a *structural* layout change.
    """
    actions: list[Action] = []
    axis_kind = issue.get("axis_kind", "xtick")
    axes_title = issue.get("axes_title", "")
    max_len = issue.get("max_label_length", 0)
    density = issue.get("density_ratio", 0.0)

    # Action 1: reduce tick label count
    actions.append(Action(
        action_type="reduce_tick_labels",
        target=axes_title or "default",
        params={"axis_name": axes_title, "axis_kind": axis_kind},
        priority=2,
        description=(
            f"Reduce number of {axis_kind} labels in '{axes_title}' "
            f"(density={density:.0%})."
        ),
    ))

    # Action 2: rotate x-labels if they are long
    if axis_kind == "xtick" and max_len > 8:
        actions.append(Action(
            action_type="rotate_labels",
            target=axes_title or "default",
            params={"axis_name": axes_title},
            priority=2,
            description=(
                f"Rotate x-tick labels in '{axes_title}' "
                f"(max_len={max_len} chars)."
            ),
        ))

    # Action 3: structural change — reduce subplots per row
    if density > 0.90:
        actions.append(Action(
            action_type="reduce_subplots_per_row",
            target="figure",
            params={
                "preferred_max_cols": 2,
                "axes_key": axes_title,
                "axis_kind": axis_kind,
            },
            priority=1,
            description=(
                f"Reduce subplots per row to give {axis_kind} labels "
                f"more width (density={density:.0%} > 90%)."
            ),
        ))

    return actions


# ── Perceptual pass actions (23-26) ──────────────────────────────────────

def _actions_low_contrast_text(issue: dict) -> list[Action]:
    """Generate actions for ``low_contrast_text`` issues."""
    return [
        Action(
            action_type="increase_text_contrast",
            target="text",
            params={"min_contrast_ratio": 3.0},
            priority=1,
            description=(
                "Darken or change text colour to meet minimum 3:1 "
                "contrast ratio against the background."
            ),
        ),
    ]


def _actions_colorblind_confusable(issue: dict) -> list[Action]:
    """Generate actions for ``colorblind_confusable`` issues."""
    return [
        Action(
            action_type="fix_cvd_palette",
            target="colours",
            params={"strategy": "use_cvd_safe_palette"},
            priority=2,
            description=(
                "Switch to a colourblind-safe palette (e.g. Okabe-Ito "
                "or viridis) so that categorical colours remain "
                "distinguishable under colour-vision deficiency."
            ),
        ),
    ]


def _actions_errorbar_invisible(issue: dict) -> list[Action]:
    """Generate actions for ``errorbar_invisible`` issues."""
    return [
        Action(
            action_type="increase_errorbar_weight",
            target="errorbars",
            params={"min_linewidth": 1.0, "min_capsize": 3},
            priority=2,
            description=(
                "Increase error-bar line width or cap size so they "
                "are visible at publication DPI (300)."
            ),
        ),
    ]


def _actions_precision_excess(issue: dict) -> list[Action]:
    """Generate actions for ``precision_excess`` issues."""
    return [
        Action(
            action_type="reduce_label_precision",
            target="text",
            params={
                "max_decimals": 4,
                # Semantic integrity: never shorten a label below this many
                # characters, and never remove leading sign characters (↑/↓/+/-).
                "min_label_chars": 12,
                "preserve_sign_prefix": True,
            },
            priority=3,
            description=(
                "Reduce numeric precision in labels/annotations to "
                "≤4 decimal places for readability.  Never shorten a label "
                "below 12 characters or remove leading sign/arrow prefixes."
            ),
        ),
    ]


# ── Semantic pass actions (27-30) ────────────────────────────────────────

def _actions_overplotted_scatter(issue: dict) -> list[Action]:
    """Generate actions for ``overplotted_scatter`` issues."""
    return [
        Action(
            action_type="use_density_viz",
            target="scatter",
            params={"strategy": "hexbin_or_kde"},
            priority=2,
            description=(
                "Replace dense scatter with a density visualisation "
                "(hexbin, KDE contour, or 2-D histogram) for readability."
            ),
        ),
        Action(
            action_type="reduce_alpha",
            target="scatter",
            params={"alpha": 0.3},
            priority=3,
            description=(
                "Reduce scatter point alpha to mitigate overplotting."
            ),
        ),
    ]


def _actions_log_scale_unlabelled(issue: dict) -> list[Action]:
    """Generate actions for ``log_scale_unlabelled`` issues."""
    return [
        Action(
            action_type="add_log_label_hint",
            target="axis_label",
            params={"suffix": " (log scale)"},
            priority=3,
            description=(
                "Annotate the axis label to indicate log scaling, "
                "e.g. append ' (log scale)' or use 'log₁₀(…)' notation."
            ),
        ),
    ]


def _actions_log_scale_nonpositive(issue: dict) -> list[Action]:
    """Generate actions for ``log_scale_nonpositive`` issues."""
    return [
        Action(
            action_type="fix_log_data_range",
            target="axis",
            params={"strategy": "clamp_or_symlog"},
            priority=1,
            description=(
                "Fix log-scale axis with non-positive data: clamp the "
                "minimum to a small positive value, or switch to symlog."
            ),
        ),
    ]


def _actions_scale_inconsistency(issue: dict) -> list[Action]:
    """Generate actions for ``scale_inconsistency`` issues."""
    return [
        Action(
            action_type="unify_axis_range",
            target="axes",
            params={"strategy": "shared_limits"},
            priority=3,
            description=(
                "Unify axis ranges across panels sharing the same label "
                "so the reader does not need to re-calibrate."
            ),
        ),
    ]


def _actions_floating_significance(issue: dict) -> list[Action]:
    """Generate actions for ``floating_significance`` issues."""
    return [
        Action(
            action_type="remove_floating_marker",
            target="annotations",
            params={"strategy": "remove_or_reposition"},
            priority=1,
            description=(
                "Remove or reposition orphaned significance marker "
                "that is too far from any data element."
            ),
        ),
    ]


def _actions_panel_complexity_excess(issue: dict) -> list[Action]:
    """Generate actions for ``panel_complexity_excess`` issues.

    Three tiers, applied in order of safety:

    1. Drop secondary numeric bar/annotation labels (always safe — trend is
       preserved).
    2. Reduce legend entries to top-N if the legend is driving complexity.
    3. Suggest splitting the panel into a supplementary figure when the
       complexity score is very high.
    """
    score = issue.get("score", 0.0)
    reasons = issue.get("reasons", [])
    n_legend = issue.get("n_legend", 0)
    actions: list[Action] = []

    # Tier 1: drop secondary numeric value labels
    actions.append(Action(
        action_type="drop_secondary_bar_labels",
        target="annotations",
        params={
            "strategy": "keep_top_bottom_n",
            "n": 3,
            "semantic_note": (
                "Keep only the 3 highest and 3 lowest value labels for "
                "reference; remove the rest to reduce visual density."
            ),
        },
        priority=2,
        description=(
            "Remove per-bar/per-point numeric labels, keeping only the "
            "top and bottom 3 for reference.  Reduces visual noise without "
            "losing the comparative trend."
        ),
    ))

    # Tier 2: trim legend if it is the main driver
    if n_legend > 10:
        actions.append(Action(
            action_type="reduce_legend_entries",
            target="legend",
            params={
                "strategy": "top_n",
                "max_entries": 8,
                "semantic_note": (
                    "Keep the 8 most important series; note in the caption "
                    "that remaining series are omitted from the legend."
                ),
            },
            priority=2,
            description=(
                f"Trim legend from {n_legend} to ≤8 entries. "
                "Move the full list to the figure caption."
            ),
        ))

    # Tier 3: suggest splitting when score is very high
    if score >= 25.0:
        actions.append(Action(
            action_type="suggest_panel_split",
            target="figure",
            params={"complexity_score": score, "reasons": reasons},
            priority=3,
            description=(
                f"Panel complexity score {score:.1f} is very high. "
                "Consider moving secondary series or annotations to a "
                "supplementary / extended-data figure."
            ),
        ))

    return actions


def _actions_whitespace_excess(issue: dict) -> list[Action]:
    """Generate actions for ``whitespace_excess`` issues.

    Only issued by the compaction phase in auto_refine when the layout is
    already free of integrity violations.  Maps directly to reduce operations
    on hspace and figure height.
    """
    detail = issue.get("detail", "").lower()
    actions: list[Action] = []

    if "hspace" in detail:
        actions.append(Action(
            action_type="reduce_hspace",
            target="figure",
            params={"delta": 0.05, "min_hspace": 0.20},
            priority=2,
            description=(
                "Reduce vertical spacing between subplots (hspace) to "
                "remove excess whitespace while keeping content readable."
            ),
        ))

    if "height" in detail or "ratio" in detail:
        actions.append(Action(
            action_type="reduce_figsize_height",
            target="figure",
            params={"delta_height": 0.3, "min_height": 4.0},
            priority=2,
            description=(
                "Reduce figure height towards the target aspect ratio. "
                "Only applied after all truncation issues are resolved."
            ),
        ))

    return actions


def _actions_cross_axes_text_overlap(issue: dict) -> list[Action]:
    """Generate actions for ``cross_axes_text_overlap`` issues.

    When text from different axes overlaps (e.g. xlabel of top panel
    collides with title of bottom panel due to small hspace), the
    primary fix is to increase inter-panel spacing.
    """
    return [
        Action(
            action_type="increase_hspace",
            target="figure",
            params={"delta": 0.08},
            priority=1,
            description=(
                "Increase vertical spacing (hspace) between subplot rows "
                "to prevent text from adjacent panels from overlapping "
                "(e.g. xlabel vs title between rows)."
            ),
        ),
        Action(
            action_type="increase_wspace",
            target="figure",
            params={"delta": 0.05},
            priority=2,
            description=(
                "Increase horizontal spacing (wspace) between subplot "
                "columns to prevent text from adjacent panels from "
                "overlapping (e.g. ylabel vs ylabel between columns)."
            ),
        ),
        Action(
            action_type="increase_figsize",
            target="figure",
            params={"delta_width": 0.5, "delta_height": 0.5},
            priority=3,
            description=(
                "Enlarge the overall figure to give inter-panel text "
                "elements more room."
            ),
        ),
    ]


def _actions_panel_label_inside_axes(issue: dict) -> list[Action]:
    """Generate actions for ``panel_label_inside_axes`` issues.

    Panel labels (a)(b)(c) placed inside axes compete with data content.
    The fix is to reposition them outside the axes bounds.
    """
    return [
        Action(
            action_type="reposition_panel_labels",
            target="panel_labels",
            params={
                "placement": "outside_top_left",
                "offset_x": -0.05,
                "offset_y": 1.05,
                "transform": "axes_fraction",
            },
            priority=2,
            description=(
                "Reposition panel labels (a)(b)(c) to outside the axes "
                "area (top-left corner, slightly above and to the left) "
                "so they do not compete with data content."
            ),
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Issue-type -> action-generator registry
# ═══════════════════════════════════════════════════════════════════════════════

ISSUE_TO_ACTIONS: dict[str, Callable[[dict], list[Action]]] = {
    "text_overlap":            _actions_text_overlap,
    "text_truncation":         _actions_text_truncation,
    "patch_truncation":        _actions_patch_truncation,
    "legend_data_occlusion":   _actions_legend_data_occlusion,
    "legend_spillover":        _actions_legend_spillover,
    "legend_truncation":       _actions_legend_truncation,
    "legend_text_crowding":    _actions_legend_text_crowding,
    "fontsize_too_small":      _actions_fontsize_too_small,
    "cross_panel_spillover":   _actions_cross_panel_spillover,
    "cbar_tick_overlap":       _actions_cbar_tick_overlap,
    "cbar_tick_truncation":    _actions_cbar_tick_truncation,
    "artist_overlap":          _actions_artist_overlap,
    "tick_spine_overlap":      _actions_tick_spine_overlap,
    "font_family_violation":   _actions_font_family_violation,
    "label_density_excess":    _actions_label_density_excess,
    # Perceptual (passes 23-26)
    "low_contrast_text":       _actions_low_contrast_text,
    "colorblind_confusable":   _actions_colorblind_confusable,
    "errorbar_invisible":      _actions_errorbar_invisible,
    "precision_excess":        _actions_precision_excess,
    # Semantic (passes 27-30)
    "overplotted_scatter":     _actions_overplotted_scatter,
    "log_scale_unlabelled":    _actions_log_scale_unlabelled,
    "log_scale_nonpositive":   _actions_log_scale_nonpositive,
    "scale_inconsistency":     _actions_scale_inconsistency,
    "floating_significance":   _actions_floating_significance,
    # Complexity / whitespace (pass 31 + compaction)
    "panel_complexity_excess": _actions_panel_complexity_excess,
    "whitespace_excess":       _actions_whitespace_excess,
    # Layout (passes 32-33)
    "cross_axes_text_overlap": _actions_cross_axes_text_overlap,
    "panel_label_inside_axes": _actions_panel_label_inside_axes,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def diagnose(issues: list[dict]) -> list[Action]:
    """Translate VCD warning issues into a deduplicated, prioritised action list.

    Parameters
    ----------
    issues : list[dict]
        The full output of ``detect_all_conflicts``.  Only entries with
        ``severity == "warning"`` are processed; ``"info"`` items are
        silently skipped.

    Returns
    -------
    list[Action]
        Deduplicated actions sorted by priority (1 = highest first).
        When two actions share the same ``(action_type, target)`` key,
        only the one with the highest priority (lowest number) is kept.
    """
    raw_actions: list[Action] = []

    for issue in issues:
        if issue.get("severity") != "warning":
            continue
        issue_type = issue.get("type", "")
        generator = ISSUE_TO_ACTIONS.get(issue_type)
        if generator is not None:
            raw_actions.extend(generator(issue))

    # Deduplicate: same (action_type, target) -> keep highest priority
    best: dict[tuple[str, str], Action] = {}
    for action in raw_actions:
        key = (action.action_type, action.target)
        existing = best.get(key)
        if existing is None or action.priority < existing.priority:
            best[key] = action

    return sorted(best.values(), key=lambda a: a.priority)


# ── Category grouping ─────────────────────────────────────────────────────────

_ACTION_CATEGORY: dict[str, str] = {
    # typography
    "increase_fontsize":       "typography",
    "fix_font_family":         "typography",
    "rotate_labels":           "typography",
    # overlap
    "reduce_tick_labels":      "overlap",
    "reduce_annotations":      "overlap",
    "reduce_cbar_ticks":       "overlap",
    # truncation
    "increase_bottom_margin":  "truncation",
    "increase_right_margin":   "truncation",
    "increase_top_margin":     "truncation",
    "increase_margins":        "truncation",
    "adjust_cbar_pad":         "truncation",
    # legend
    "move_legend":             "legend",
    "move_legend_inside":      "legend",
    "shrink_legend_font":      "legend",
    "reduce_legend_entries":   "legend",
    # density
    "increase_figsize":        "density",
    "increase_figsize_width":  "density",
    "increase_figsize_height": "density",
    # spacing
    "increase_hspace":         "spacing",
    "increase_wspace":         "spacing",
    # structural
    "reduce_subplots_per_row": "density",
    # perceptual
    "increase_text_contrast":  "perceptual",
    "fix_cvd_palette":         "perceptual",
    "increase_errorbar_weight": "perceptual",
    "reduce_label_precision":  "perceptual",
    # semantic
    "use_density_viz":         "semantic",
    "reduce_alpha":            "semantic",
    "add_log_label_hint":      "semantic",
    "fix_log_data_range":      "semantic",
    "unify_axis_range":        "semantic",
    "remove_floating_marker":  "semantic",
    # complexity
    "drop_secondary_bar_labels": "complexity",
    "suggest_panel_split":       "complexity",
    # compaction
    "reduce_hspace":             "spacing",
    "reduce_figsize_height":     "density",
    # panel label repositioning
    "reposition_panel_labels":   "typography",
}


def group_by_category(actions: list[Action]) -> dict[str, list[Action]]:
    """Group actions into semantic categories.

    Categories
    ----------
    typography : font size, font family, label rotation
    overlap    : tick-label reduction, annotation reduction, cbar ticks
    truncation : margin adjustments, padding changes
    legend     : legend repositioning and resizing
    density    : figure size increases
    spacing    : subplot spacing (hspace / wspace)

    Parameters
    ----------
    actions : list[Action]
        Typically the output of :func:`diagnose`.

    Returns
    -------
    dict[str, list[Action]]
        Keys are category names; values are lists of actions belonging
        to that category, preserving the input order.
    """
    grouped: dict[str, list[Action]] = {
        "typography":  [],
        "overlap":     [],
        "truncation":  [],
        "legend":      [],
        "density":     [],
        "spacing":     [],
        "perceptual":  [],
        "semantic":    [],
        "complexity":  [],
    }

    for action in actions:
        category = _ACTION_CATEGORY.get(action.action_type, "density")
        grouped[category].append(action)

    return grouped
