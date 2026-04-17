"""Figure-quality policy for CLOP-DiT publication figures.

Encodes typography, spacing, density, legend, and truncation rules that
every generated panel must satisfy before it is considered publication-ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Severity grading (US-202)
# ---------------------------------------------------------------------------
#
# Two layers of severity are tracked per issue:
#   - "severity"       : "warning" | "info"   (legacy; wired into every check)
#   - "severity_level" : one of SEVERITY_LEVELS (derived from type)
#
# CRITICAL  = publication-blocker; data or reviewer-cited element is clipped
#             or unreadable (e.g. xtick truncation, cross-axes text overlap)
# MAJOR     = reviewer-visible readability defect; must fix before upload
# MINOR     = cosmetic, safe to ship but worth addressing in the next round
# INFO      = informational signal; not a defect

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_MAJOR = "MAJOR"
SEVERITY_MINOR = "MINOR"
SEVERITY_INFO = "INFO"

SEVERITY_LEVELS: Tuple[str, ...] = (
    SEVERITY_CRITICAL,
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    SEVERITY_INFO,
)

# Default mapping from issue ``type`` to severity level. Consumers may
# override individual entries via ``FigurePolicy.severity_overrides``.
_DEFAULT_SEVERITY_BY_TYPE: Dict[str, str] = {
    # --- CRITICAL: data or reviewer-visible element is clipped/unreadable ---
    "text_truncation": SEVERITY_CRITICAL,
    "cross_axes_text_overlap": SEVERITY_CRITICAL,
    "axes_overflow": SEVERITY_CRITICAL,
    "scatter_clip_risk": SEVERITY_CRITICAL,
    "panel_label_overlap": SEVERITY_CRITICAL,

    # --- MAJOR: reviewer-noticeable readability defect ---
    "text_overlap": SEVERITY_MAJOR,
    "artist_content_overlap": SEVERITY_MAJOR,
    "text_artist_overlap": SEVERITY_MAJOR,
    "cross_panel_spillover": SEVERITY_MAJOR,
    "legend_spillover": SEVERITY_MAJOR,
    "legend_vs_other_panel_content": SEVERITY_MAJOR,
    "legend_data_occlusion": SEVERITY_MAJOR,
    "colorbar_data_overlap": SEVERITY_MAJOR,
    "fontsize_inadequate": SEVERITY_MAJOR,
    "label_density_excess": SEVERITY_MAJOR,
    "font_policy": SEVERITY_MAJOR,
    "contrast_low": SEVERITY_MAJOR,
    "colorblind_confusable": SEVERITY_MAJOR,
    "errorbar_invisible": SEVERITY_MAJOR,
    "significance_bracket_overlap": SEVERITY_MAJOR,
    "minimum_font_size": SEVERITY_MAJOR,
    "effective_dpi_low": SEVERITY_MAJOR,

    # --- MINOR: cosmetic, publication-safe ---
    "legend_artist_masking": SEVERITY_MINOR,
    "legend_vs_legend": SEVERITY_MINOR,
    "legend_vs_other_artists": SEVERITY_MINOR,
    "legend_vs_own_content": SEVERITY_MINOR,
    "legend_internal": SEVERITY_MINOR,
    "legend_crowding": SEVERITY_MINOR,
    "colorbar_internal": SEVERITY_MINOR,
    "annotation_data_overlap": SEVERITY_MINOR,
    "tick_spine_overlap": SEVERITY_MINOR,
    "panel_label_placement": SEVERITY_MINOR,
    "floating_significance": SEVERITY_MINOR,
    "precision_excess": SEVERITY_MINOR,
    "overplotting": SEVERITY_MINOR,
    "panel_complexity_excess": SEVERITY_MINOR,

    # --- INFO: stylistic signal, not a defect ---
    "bold_usage": SEVERITY_INFO,
    "log_scale_sanity": SEVERITY_INFO,
    "scale_consistency": SEVERITY_INFO,

    # --- Content-aware (US-305 fold-back) ---
    "label_string_ellipsis": SEVERITY_MINOR,
    "overlapping_series_values": SEVERITY_INFO,
    "duplicate_tick_labels": SEVERITY_INFO,

    # --- Annotation-crowding (scivcd follow-up 2026-04-17) ---
    "annotation_crowding": SEVERITY_MAJOR,
}


def severity_level_for(
    issue: dict,
    *,
    overrides: Optional[Dict[str, str]] = None,
    default: str = SEVERITY_INFO,
) -> str:
    """Return the 4-level severity for a VCD ``issue`` dict.

    Resolution order: ``overrides[type]`` → ``_DEFAULT_SEVERITY_BY_TYPE[type]``
    → for issues emitted with the legacy ``severity="warning"`` the fallback
    is ``MAJOR``; for ``severity="info"`` the fallback is ``INFO``; otherwise
    ``default`` is returned.
    """
    issue_type = str(issue.get("type", ""))
    if overrides and issue_type in overrides:
        return overrides[issue_type]
    if issue_type in _DEFAULT_SEVERITY_BY_TYPE:
        return _DEFAULT_SEVERITY_BY_TYPE[issue_type]
    legacy = str(issue.get("severity", "")).lower()
    if legacy == "warning":
        return SEVERITY_MAJOR
    if legacy == "info":
        return SEVERITY_INFO
    return default


def annotate_severity_levels(
    issues: list,
    *,
    overrides: Optional[Dict[str, str]] = None,
) -> list:
    """Attach ``severity_level`` in-place to every issue dict; return the list."""
    for issue in issues:
        if "severity_level" not in issue:
            issue["severity_level"] = severity_level_for(issue, overrides=overrides)
    return issues


def count_by_severity_level(issues: list) -> Dict[str, int]:
    """Return ``{level: count}`` across all 4 levels; zero-fills absent levels."""
    counts: Dict[str, int] = {level: 0 for level in SEVERITY_LEVELS}
    for issue in issues:
        level = issue.get("severity_level")
        if level not in counts:
            level = severity_level_for(issue)
        counts[level] = counts.get(level, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Policy dataclass
# ---------------------------------------------------------------------------

@dataclass
class FigurePolicy:
    """Central knob-file for every visual-conflict rule.

    Instantiate with defaults for the CLOP-DiT paper, or override individual
    fields for a different publication style.
    """

    # -- Typography rules ---------------------------------------------------
    allowed_fonts: set = field(
        default_factory=lambda: {
            "Arial",
            "Helvetica",
            "DejaVu Sans",
            "Liberation Sans",
            "sans-serif",
        }
    )
    min_body_pt: float = 10.0
    min_dense_pt: float = 8.0
    composed_scale: float = 0.70
    max_title_label_diff: float = 2.0

    # -- Density rules ------------------------------------------------------
    max_xtick_labels: int = 25
    max_ytick_labels: int = 25
    heatmap_max_ticks: int = 15
    bar_max_categories: int = 30
    rotation_threshold: int = 15  # start rotating labels above this count

    # -- Legend rules --------------------------------------------------------
    preferred_locations: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "line": ["best", "upper left"],
            "bar": ["upper right", "upper left"],
            "heatmap": ["outside_right"],
            "scatter": ["upper left", "best"],
            "polar": ["upper right"],
        }
    )
    max_legend_entries_inside: int = 6
    legend_fontsize_min: int = 8

    # -- Truncation / sizing rules ------------------------------------------
    border_tolerance_px: float = 3.0
    max_figsize: Tuple[float, float] = (14.0, 10.0)
    figsize_increment: Tuple[float, float] = (0.5, 0.5)

    # -- Annotation rules ---------------------------------------------------
    max_annotations_per_axes: int = 5
    max_heatmap_annotations: int = 50
    annotation_min_fontsize: int = 8

    # -- Height / whitespace compaction targets ----------------------------
    target_height_width_ratio: float = 0.50   # h/w for full-width standalone panels
    hspace_compact_target: float = 0.35       # aim for this hspace after cleanup
    hspace_excess_threshold: float = 0.70     # hspace above this triggers compaction
    height_compact_min_inches: float = 4.0    # never shrink figure below this height

    # -- Semantic integrity guards ----------------------------------------
    min_label_display_chars: int = 12         # never shorten a label below this
    label_ellipsis_mode: str = "end"          # "end" or "middle"
    protected_label_prefixes: set = field(
        default_factory=lambda: {"↑", "↓", "+", "-", "−", "∗"}
    )
    annotation_drop_order: list = field(
        default_factory=lambda: ["redundant", "secondary", "primary"]
    )

    # -- Panel complexity thresholds --------------------------------------
    max_legend_series: int = 10               # legend entries per axes
    max_numeric_bar_labels: int = 30          # per-bar value-label count
    max_annotations_complexity: int = 20      # text elements per axes
    complexity_score_threshold: float = 15.0  # weighted sum to trigger info


# ---------------------------------------------------------------------------
# Singleton default
# ---------------------------------------------------------------------------

DEFAULT_POLICY: FigurePolicy = FigurePolicy()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _resolve(policy: Optional[FigurePolicy]) -> FigurePolicy:
    """Return *policy* if given, else the module-level default."""
    return policy if policy is not None else DEFAULT_POLICY


def effective_pt(fontsize: float, policy: Optional[FigurePolicy] = None) -> float:
    """Return the effective point size after composed-figure scaling.

    When a panel is composed into a multi-panel figure the on-screen size
    shrinks by ``policy.composed_scale``.  This helper makes the maths
    explicit so callers do not have to remember the multiplication.
    """
    p = _resolve(policy)
    return fontsize * p.composed_scale


def is_font_adequate(
    fontsize: float,
    is_dense: bool = False,
    policy: Optional[FigurePolicy] = None,
) -> bool:
    """Check whether *fontsize* meets the minimum after composition scaling.

    Parameters
    ----------
    fontsize:
        Nominal font size in points as set by the plotting code.
    is_dense:
        If ``True`` the check uses the relaxed ``min_dense_pt`` threshold
        (e.g. for heatmap annotations or small-multiple tick labels).
    policy:
        Override the default policy if needed.

    Returns
    -------
    bool
        ``True`` when the effective size is at or above the minimum.
    """
    p = _resolve(policy)
    eff = effective_pt(fontsize, p)
    threshold = p.min_dense_pt if is_dense else p.min_body_pt
    return eff >= threshold


def suggest_max_ticks(
    plot_kind: str,
    n_items: int,
    policy: Optional[FigurePolicy] = None,
) -> int:
    """Return the recommended maximum number of visible tick labels.

    Parameters
    ----------
    plot_kind:
        One of ``"bar"``, ``"heatmap"``, ``"line"``, ``"scatter"``, etc.
    n_items:
        The actual number of data items along the axis.
    policy:
        Override the default policy if needed.

    Returns
    -------
    int
        The maximum number of ticks that should be displayed.  If *n_items*
        is already within the limit, *n_items* is returned unchanged.
    """
    p = _resolve(policy)

    if plot_kind == "heatmap":
        cap = p.heatmap_max_ticks
    elif plot_kind == "bar":
        cap = p.bar_max_categories
    else:
        cap = p.max_xtick_labels

    return min(n_items, cap)


def suggest_legend_loc(
    plot_kind: str,
    n_entries: int,
    policy: Optional[FigurePolicy] = None,
) -> str:
    """Return the recommended ``loc`` string for ``ax.legend()``.

    If the number of entries exceeds ``max_legend_entries_inside`` the
    function returns ``"outside_right"`` so the caller can switch to
    ``bbox_to_anchor`` placement.

    Parameters
    ----------
    plot_kind:
        One of ``"line"``, ``"bar"``, ``"heatmap"``, ``"scatter"``,
        ``"polar"``, etc.
    n_entries:
        How many legend entries will be displayed.
    policy:
        Override the default policy if needed.

    Returns
    -------
    str
        A matplotlib-compatible ``loc`` string (or ``"outside_right"``
        as a sentinel the caller must handle).
    """
    p = _resolve(policy)

    if n_entries > p.max_legend_entries_inside:
        return "outside_right"

    prefs = p.preferred_locations.get(plot_kind, ["best"])
    return prefs[0]


def should_rotate_labels(
    n_labels: int,
    policy: Optional[FigurePolicy] = None,
) -> Tuple[bool, int]:
    """Decide whether axis tick labels should be rotated.

    Parameters
    ----------
    n_labels:
        Number of tick labels along the axis.
    policy:
        Override the default policy if needed.

    Returns
    -------
    tuple[bool, int]
        A pair ``(should_rotate, angle)`` where *angle* is ``0`` when no
        rotation is needed, ``45`` for moderate crowding, or ``90`` for
        extreme crowding.
    """
    p = _resolve(policy)

    if n_labels <= p.rotation_threshold:
        return False, 0

    if n_labels <= p.rotation_threshold * 2:
        return True, 45

    return True, 90
