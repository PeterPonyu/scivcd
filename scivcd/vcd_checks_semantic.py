"""VCD semantic / data-encoding detection passes (27-31).

Pass 27: Overplotted scatter detection (too many points with low alpha).
Pass 28: Log-scale sanity (missing "log" hint, negative values, unlabelled).
Pass 29: Cross-panel scale inconsistency (same metric, different ranges).
Pass 30: Floating significance markers (stars with no associated bar/line).
Pass 31: Panel complexity excess (too many series, labels, or annotations).
"""
from __future__ import annotations

import re
from collections import defaultdict

import numpy as np
from matplotlib.text import Text
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection

from .vcd_core import _ArtistInfo, _safe_bbox, _fig_bbox


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 27: Overplotted scatter detection
# ═══════════════════════════════════════════════════════════════════════════════

def _check_overplotting(fig, renderer,
                         alpha_point_threshold=5000,
                         opaque_point_threshold=500):
    """Pass 27: Detect scatter plots that are likely overplotted.

    A scatter plot with many data points AND high alpha produces a
    solid blob where individual points are indistinguishable.  This
    check flags:
      a) *opaque_point_threshold*+ points with alpha ≥ 0.5.
      b) *alpha_point_threshold*+ points regardless of alpha
         (even low-alpha becomes opaque when stacked).

    Suggests using density visualisation (hexbin, KDE, subsampling)
    or lowering alpha.
    """
    issues: list[dict] = []

    for ax in fig.get_axes():
        if getattr(ax, 'name', None) == 'polar':
            continue
        title = ax.get_title() or f"ax@{id(ax):#x}"

        for child in ax.get_children():
            if not isinstance(child, PathCollection) or not child.get_visible():
                continue
            offsets = child.get_offsets()
            if offsets is None:
                continue
            n_points = len(offsets)

            # Determine effective alpha
            alphas = child.get_alpha()
            if alphas is None:
                # Default is 1.0
                eff_alpha = 1.0
            elif np.isscalar(alphas):
                eff_alpha = float(alphas)
            else:
                eff_alpha = float(np.mean(alphas))

            # Check for obvious overplotting
            if n_points >= alpha_point_threshold:
                issues.append({
                    "type": "overplotted_scatter",
                    "severity": "info",
                    "detail": (
                        f"Scatter in '{title}' has {n_points:,} points "
                        f"(α={eff_alpha:.2f}) — consider hexbin or KDE "
                        f"for readability"
                    ),
                    "elements": [f"scatter:{title}"],
                })
            elif n_points >= opaque_point_threshold and eff_alpha >= 0.5:
                issues.append({
                    "type": "overplotted_scatter",
                    "severity": "info",
                    "detail": (
                        f"Scatter in '{title}' has {n_points:,} points "
                        f"with high alpha ({eff_alpha:.2f}) — may be "
                        f"overplotted; consider reducing alpha or using "
                        f"density visualisation"
                    ),
                    "elements": [f"scatter:{title}"],
                })

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 28: Log-scale sanity
# ═══════════════════════════════════════════════════════════════════════════════

def _check_log_scale_sanity(fig, renderer):
    """Pass 28: Detect log-scale axes without proper labelling or with problems.

    Checks:
      a) Axes using log scale whose label does not contain "log" or
         the axis title does not indicate logarithmic scaling.
      b) Log-scale axes where data extends to zero or negative values
         (which produces -inf and is silently clipped by matplotlib).
    """
    issues: list[dict] = []

    for ax in fig.get_axes():
        if getattr(ax, 'name', None) == 'polar':
            continue
        title = ax.get_title() or f"ax@{id(ax):#x}"

        for axis_name, axis_obj in [("x", ax.xaxis), ("y", ax.yaxis)]:
            scale = axis_obj.get_scale()
            if scale != "log":
                continue

            # a) Check label mentions "log"
            label_text = axis_obj.label.get_text().strip().lower()
            title_text = title.lower()
            has_log_hint = (
                "log" in label_text
                or "log" in title_text
                or "10^" in label_text
                or "10^" in title_text
            )
            if not has_log_hint and label_text:
                issues.append({
                    "type": "log_scale_unlabelled",
                    "severity": "info",
                    "detail": (
                        f"{axis_name.upper()}-axis in '{title}' uses log scale "
                        f"but label '{label_text}' does not indicate this"
                    ),
                    "elements": [f"log_{axis_name}:{title}"],
                })

            # b) Check for zero/negative in data range
            lim = ax.get_xlim() if axis_name == "x" else ax.get_ylim()
            if lim[0] <= 0:
                issues.append({
                    "type": "log_scale_nonpositive",
                    "severity": "warning",
                    "detail": (
                        f"{axis_name.upper()}-axis in '{title}' uses log scale "
                        f"but range starts at {lim[0]:.4g} (≤0)"
                    ),
                    "elements": [f"log_{axis_name}:{title}"],
                })

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 29: Cross-panel scale inconsistency
# ═══════════════════════════════════════════════════════════════════════════════

def _check_scale_consistency(fig, renderer):
    """Pass 29: Detect panels sharing the same axis label but different ranges.

    When two subplots label an axis identically (e.g. "Fréchet Distance")
    but one has range [0, 3] and another [0, 50], the reader must mentally
    re-calibrate between panels.  This check flags such mismatches as info.

    Only fires when ≥ 2 axes share the exact same axis label text.
    """
    issues: list[dict] = []

    # Collect (label_text -> [(title, lo, hi), ...]) for x and y
    for axis_kind in ("x", "y"):
        label_groups: dict[str, list[tuple[str, float, float]]] = defaultdict(list)

        for ax in fig.get_axes():
            if getattr(ax, 'name', None) == 'polar':
                continue
            title = ax.get_title() or f"ax@{id(ax):#x}"

            if axis_kind == "x":
                lbl = ax.get_xlabel().strip()
                lo, hi = ax.get_xlim()
            else:
                lbl = ax.get_ylabel().strip()
                lo, hi = ax.get_ylim()

            if lbl:
                label_groups[lbl].append((title, lo, hi))

        for lbl, entries in label_groups.items():
            if len(entries) < 2:
                continue

            # Check range spread
            all_lo = [e[1] for e in entries]
            all_hi = [e[2] for e in entries]
            min_lo, max_lo = min(all_lo), max(all_lo)
            min_hi, max_hi = min(all_hi), max(all_hi)

            # Significant mismatch: one range is >3× another
            ranges = [(hi - lo) for _, lo, hi in entries]
            if min(ranges) > 0 and max(ranges) / min(ranges) > 3.0:
                panels = [e[0][:25] for e in entries]
                issues.append({
                    "type": "scale_inconsistency",
                    "severity": "info",
                    "detail": (
                        f"{axis_kind.upper()}-axis label '{lbl}' shared by "
                        f"{len(entries)} panels with {max(ranges)/min(ranges):.1f}× "
                        f"range spread: {', '.join(panels[:3])}"
                    ),
                    "elements": [f"scale_{axis_kind}:{lbl}"],
                })

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 30: Floating significance markers
# ═══════════════════════════════════════════════════════════════════════════════

_STAR_RE = re.compile(r'^(\*{1,3}|ns)$')


def _check_floating_significance(fig, renderer, proximity_px=50):
    """Pass 30: Detect significance markers not near any bar or line.

    Significance annotations (*, **, ***, ns) should be positioned above
    the bars/lines they annotate.  If a star text is farther than
    *proximity_px* from any bar/line bbox, it may be a layout artefact
    (e.g. a bracket was removed but the star was left behind).
    """
    issues: list[dict] = []

    for ax in fig.get_axes():
        if getattr(ax, 'name', None) == 'polar':
            continue
        title = ax.get_title() or f"ax@{id(ax):#x}"

        # Collect star texts
        star_texts: list[tuple[str, float, float]] = []
        for child in ax.get_children():
            if not isinstance(child, Text) or not child.get_visible():
                continue
            txt = child.get_text().strip()
            if _STAR_RE.match(txt):
                bb = _safe_bbox(child, renderer)
                if bb:
                    cx = (bb.x0 + bb.x1) / 2
                    cy = (bb.y0 + bb.y1) / 2
                    star_texts.append((txt, cx, cy))

        if not star_texts:
            continue

        # Collect data artist bboxes (bars, lines)
        data_bbs = []
        for child in ax.get_children():
            if not child.get_visible():
                continue
            if isinstance(child, (Line2D,)):
                bb = _safe_bbox(child, renderer)
                if bb:
                    data_bbs.append(bb)
            elif hasattr(child, 'get_facecolor'):
                # Patches (bars)
                label = getattr(child, '_label', '') or ''
                if child is not ax.patch and not label.startswith('_'):
                    bb = _safe_bbox(child, renderer)
                    if bb:
                        data_bbs.append(bb)

        for txt, cx, cy in star_texts:
            # Find minimum distance to any data artist bbox
            min_dist = float('inf')
            for dbb in data_bbs:
                # Distance from point to bbox
                dx = max(dbb.x0 - cx, 0, cx - dbb.x1)
                dy = max(dbb.y0 - cy, 0, cy - dbb.y1)
                dist = (dx**2 + dy**2) ** 0.5
                min_dist = min(min_dist, dist)

            if min_dist > proximity_px:
                issues.append({
                    "type": "floating_significance",
                    "severity": "warning",
                    "detail": (
                        f"Significance marker '{txt}' in '{title}' is "
                        f"{min_dist:.0f}px from nearest data element "
                        f"(>{proximity_px}px threshold)"
                    ),
                    "elements": [f"sig:{txt}:{title}"],
                })

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 31: Panel complexity excess
# ═══════════════════════════════════════════════════════════════════════════════

_NUMERIC_RE = re.compile(r'^[+\-−]?\d[\d,\.%eE+\-]*$')


def _check_panel_complexity(
    fig,
    renderer,
    max_legend_series: int = 10,
    max_numeric_labels: int = 30,
    max_annotations: int = 20,
    score_threshold: float = 15.0,
):
    """Pass 31: Detect panels carrying more visual information than is legible.

    Computes a weighted complexity score per axes from three components:

    1. **Legend entries**: each entry above *max_legend_series* adds 1.5 pts.
    2. **Numeric bar/annotation labels**: each visible numeric text above
       *max_numeric_labels* adds 0.5 pts.
    3. **Total text elements**: each element above *max_annotations* adds 0.3 pts
       (catches dense annotation grids that the other two miss).

    Emits ``panel_complexity_excess`` (severity ``"info"``) when the score
    reaches *score_threshold*.  The issue dict includes ``"score"``,
    ``"reasons"``, and ``"n_legend"`` / ``"n_numeric"`` / ``"n_text"``
    for use by action generators.
    """
    issues: list[dict] = []

    for ax in fig.get_axes():
        if getattr(ax, 'name', None) == 'polar':
            continue
        title = ax.get_title() or f"ax@{id(ax):#x}"

        # Axes fixed-role text elements to exclude from counts
        _excluded = {ax.title, ax.xaxis.label, ax.yaxis.label}

        # 1. Legend entries
        n_legend = 0
        legend = ax.get_legend()
        if legend is not None and legend.get_visible():
            n_legend = len(legend.get_texts())

        # 2. Numeric text labels (look like numbers / percentages)
        n_numeric = 0
        n_text = 0
        for child in ax.get_children():
            if not isinstance(child, Text):
                continue
            if not child.get_visible():
                continue
            if child in _excluded:
                continue
            txt = child.get_text().strip()
            if not txt:
                continue
            n_text += 1
            if _NUMERIC_RE.match(txt):
                n_numeric += 1

        # 3. Compute weighted score
        score = 0.0
        reasons: list[str] = []

        if n_legend > max_legend_series:
            excess = n_legend - max_legend_series
            score += excess * 1.5
            reasons.append(f"{n_legend} legend entries (>{max_legend_series})")

        if n_numeric > max_numeric_labels:
            excess = n_numeric - max_numeric_labels
            score += excess * 0.5
            reasons.append(f"{n_numeric} numeric labels (>{max_numeric_labels})")

        if n_text > max_annotations:
            excess = n_text - max_annotations
            score += excess * 0.3
            reasons.append(f"{n_text} text elements (>{max_annotations})")

        if score >= score_threshold:
            issues.append({
                "type": "panel_complexity_excess",
                "severity": "info",
                "detail": (
                    f"Panel '{title}' complexity score {score:.1f} "
                    f"(threshold {score_threshold}): {'; '.join(reasons)}. "
                    f"Consider simplifying or splitting."
                ),
                "elements": [f"panel:{title}"],
                "score": score,
                "reasons": reasons,
                "n_legend": n_legend,
                "n_numeric": n_numeric,
                "n_text": n_text,
            })

    return issues
