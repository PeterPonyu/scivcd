"""Figure complexity classifier + adaptive check routing (US-301).

Classifies a matplotlib figure into one of three complexity classes so the
VCD sweep runs only the checks that are actually relevant:

- ``SIMPLE``  — single axes, no suptitle/fig-level legend, <=50 artists.
               Runs 4 cheap checks.
- ``COMPOUND`` — <=4 axes, either a single row or single column gridspec.
                 Runs 7 checks (adds cross-axes + legend placement + label density).
- ``COMPOSED`` — >=5 axes or 2-D gridspec or figure-level legend/suptitle.
                 Runs the full suite.

``PROFILES`` maps each class to a list of *pass names* (strings) that the
driver (``__init__.detect_all_conflicts``) can look up to decide whether a
given check should run for the current figure.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, List

try:
    import matplotlib.figure
except Exception:  # pragma: no cover
    matplotlib = None  # type: ignore


class Complexity(str, Enum):
    SIMPLE = "SIMPLE"
    COMPOUND = "COMPOUND"
    COMPOSED = "COMPOSED"


# All pass names used by the driver. Order does not matter; matching is
# substring-insensitive on the function-name the driver looks up.
_ALL_PASSES: List[str] = [
    "text_overlaps",
    "truncation",
    "artist_content_overlap",
    "text_vs_artist_overlap",
    "axes_overflow",
    "scatter_clip_risk",
    "cross_panel_spillover",
    "panel_label_overlap",
    "legend_spillover",
    "legend_vs_other_panel_content",
    "legend_vs_legend",
    "legend_vs_other_artists",
    "legend_vs_own_content",
    "fig_legend_vs_subplot_content",
    "colorbar_internal",
    "legend_internal",
    "significance_brackets",
    "colorbar_data_overlap",
    "legend_crowding_autofix",
    "fontsize_adequacy",
    "tick_spine_overlap",
    "font_policy",
    "label_density",
    "contrast",
    "colorblind_safety",
    "errorbar_visibility",
    "precision_excess",
    "overplotting",
    "log_scale_sanity",
    "scale_consistency",
    "floating_significance",
    "panel_complexity",
    "cross_axes_text_overlap",
    "panel_label_placement",
    "minimum_font_size",
    "colorblind_safety_pub",
    "effective_dpi",
]


# Profiles pick a subset of the pass list by name.
PROFILES: dict[Complexity, List[str]] = {
    Complexity.SIMPLE: [
        "text_overlaps",
        "truncation",
        "minimum_font_size",
        "effective_dpi",
    ],
    Complexity.COMPOUND: [
        "text_overlaps",
        "truncation",
        "artist_content_overlap",
        "text_vs_artist_overlap",
        "cross_axes_text_overlap",
        "legend_spillover",
        "label_density",
        "fontsize_adequacy",
        "minimum_font_size",
        "effective_dpi",
    ],
    Complexity.COMPOSED: list(_ALL_PASSES),  # everything
}


def classify_figure(fig) -> Complexity:
    """Classify a matplotlib figure by structural complexity."""
    axes = [ax for ax in fig.get_axes() if getattr(ax, "axison", True)]
    n_axes = len(axes)

    # Figure-level signals
    has_suptitle = bool(
        getattr(fig, "_suptitle", None)
        and fig._suptitle.get_text().strip()
    )
    has_fig_legend = bool(getattr(fig, "legends", []))

    # Count artists across all axes — cheap proxy for density
    n_artists = 0
    for ax in axes:
        n_artists += len(ax.lines) + len(ax.patches) + len(ax.collections) + len(ax.texts)

    # Detect gridspec shape: COMPOUND iff single row or single column
    gs_is_grid = False
    gs_is_single_rc = False
    for ax in axes:
        try:
            ss = ax.get_subplotspec()
        except Exception:
            continue
        if ss is None:
            continue
        gs = ss.get_gridspec()
        nrows, ncols = gs.get_geometry()
        if nrows > 1 and ncols > 1:
            gs_is_grid = True
            break
        if (nrows == 1 and ncols > 1) or (ncols == 1 and nrows > 1):
            gs_is_single_rc = True

    if n_axes >= 5 or gs_is_grid or has_fig_legend:
        return Complexity.COMPOSED
    if n_axes <= 1 and not has_suptitle and n_artists <= 50:
        return Complexity.SIMPLE
    # 2–4 axes, or single row/column, or a single-axes figure with lots of
    # artists — treat as COMPOUND.
    if n_axes <= 4 or gs_is_single_rc:
        return Complexity.COMPOUND
    return Complexity.COMPOSED


def select_passes(profile: str | Complexity, fig=None) -> List[str]:
    """Return the pass names to run for a given profile.

    ``profile`` may be ``"auto"`` (classify the figure first), ``"full"``
    (run every pass regardless), or one of the Complexity values.
    """
    if isinstance(profile, Complexity):
        return PROFILES[profile]
    p = str(profile).lower()
    if p == "full":
        return list(_ALL_PASSES)
    if p == "auto":
        if fig is None:
            return list(_ALL_PASSES)
        return PROFILES[classify_figure(fig)]
    # Explicit class name
    for c in Complexity:
        if p == c.value.lower():
            return PROFILES[c]
    return list(_ALL_PASSES)


def should_run(pass_name: str, selected: Iterable[str]) -> bool:
    """Small helper so the driver can skip passes cleanly."""
    return pass_name in set(selected)


__all__ = [
    "Complexity",
    "PROFILES",
    "classify_figure",
    "select_passes",
    "should_run",
]
