"""VCD layout detection passes (19-22) + new passes (32-33).

Passes migrated from vcd_checks_structure.py for modular file sizing:
  Pass 19: Font-size adequacy detection.
  Pass 20: Tick-spine overlap detection.
  Pass 21: Global font consistency check.
  Pass 22: Label density excess detection (with colorbar-axes exclusion).

New passes:
  Pass 32: Cross-axes text overlap (e.g. xlabel vs title between rows).
  Pass 33: Panel label placement (inside vs outside axes bounds).
"""

from __future__ import annotations

import re

from matplotlib.text import Text
from matplotlib.transforms import Bbox

from .vcd_core import (
    _ArtistInfo,
    _safe_bbox,
    _shrink,
    _fig_bbox,
    _overlap_area,
    _sides_outside,
    _is_colorbar_axes,
)


# ===============================================================================
# Pass 19: Font-size adequacy detection
# ===============================================================================

def _check_fontsize_adequacy(
    fig,
    renderer,
    infos: list[_ArtistInfo],
    min_pt: float = 6.0,
    composed_scale: float = 0.5,
    dense_label_min_pt: float = 5.5,
) -> list[dict]:
    """Detect text whose effective print size falls below *min_pt*.

    The *composed_scale* parameter approximates the downscaling that
    occurs when the subplot PNG is placed inside the Next.js compositor
    (e.g. a 3-column grid in a 2-panel layout -> each subplot rendered
    at ~50% of its original size).  The effective font size is::

        effective_pt = artist.get_fontsize() * composed_scale

    Any text below *min_pt* after scaling is flagged.  This prevents
    tiny illegible labels from reaching the final PDF.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
    renderer : matplotlib renderer
    infos : list of _ArtistInfo
    min_pt : float
        Minimum acceptable point size in the composed figure (default 6).
    composed_scale : float
        Approximate scale factor from subplot PNG to composed screenshot
        (default 0.5 for 2-panel layout with 3-column grid).

    Returns
    -------
    list[dict]
        Issues with ``type='fontsize_too_small'``.
    """
    issues: list[dict] = []
    seen_sizes: dict[float, list[str]] = {}  # group by fontsize for summary

    for info in infos:
        if info.kind != "text":
            continue
        artist = info.artist
        if not isinstance(artist, Text):
            continue
        text_str = artist.get_text().strip()
        if not text_str:
            continue
        # Skip internal matplotlib artists (underscore prefix)
        label = getattr(artist, '_label', '') or ''
        if label.startswith('_'):
            continue

        fs = artist.get_fontsize()
        effective = fs * composed_scale
        # Dense labels (tagged via gid or very small tick labels) use a
        # relaxed threshold to avoid false alarms on intentionally compact
        # heatmap / dense bar-chart ticks.
        gid = getattr(artist, '_gid', None) or ''
        is_dense = 'dense_label' in str(gid) or info.tag.startswith(('xtick', 'ytick', 'cbar_tick'))
        threshold = dense_label_min_pt if is_dense else min_pt
        if effective < threshold:
            seen_sizes.setdefault(fs, []).append(text_str[:30])

    # Emit one warning per distinct fontsize (avoids 50+ duplicate warnings)
    for fs, examples in sorted(seen_sizes.items()):
        effective = fs * composed_scale
        n = len(examples)
        sample = examples[:3]
        sample_str = ", ".join(f"'{s}'" for s in sample)
        if n > 3:
            sample_str += f" ... +{n - 3} more"
        issues.append({
            "type": "fontsize_too_small",
            "severity": "warning",
            "detail": (
                f"{n} text(s) at {fs:.1f}pt \u2192 effective {effective:.1f}pt "
                f"(min {min_pt}pt): {sample_str}"
            ),
            "elements": examples,
        })

    return issues


# ===============================================================================
# Pass 20: Tick-spine overlap detection
# ===============================================================================

def _check_tick_spine_overlap(fig, renderer, tol_px=2.0):
    """Pass 20: Detect tick labels rendered *inside* the data area.

    Tick labels normally sit outside the axes.  This check flags labels
    whose bbox is **entirely** inside the axes area (i.e. the label is
    rendered on top of data content rather than in the margin).

    Normal adjacent-to-spine positioning is NOT flagged -- only labels
    whose full extent is within the plot rectangle.
    """
    issues = []
    for ax in fig.get_axes():
        if getattr(ax, 'name', None) == 'polar':
            continue
        ax_bb = _safe_bbox(ax, renderer)
        if ax_bb is None:
            continue

        # X-tick labels: flag only if the ENTIRE label is above the bottom spine
        for tl in ax.get_xticklabels():
            txt = tl.get_text().strip()
            if not txt:
                continue
            bb = _safe_bbox(tl, renderer)
            if bb is None:
                continue
            # Label is "inside" if its bottom edge is above the spine
            if bb.y0 > ax_bb.y0 + tol_px and bb.y1 < ax_bb.y1 - tol_px:
                issues.append({
                    "type": "tick_spine_overlap",
                    "severity": "warning",
                    "detail": (
                        f"X-tick '{txt[:20]}' rendered inside plot area"
                    ),
                    "elements": [f"xtick:{txt[:20]}"],
                })

        # Y-tick labels: flag only if the ENTIRE label is to the right of the left spine
        for tl in ax.get_yticklabels():
            txt = tl.get_text().strip()
            if not txt:
                continue
            bb = _safe_bbox(tl, renderer)
            if bb is None:
                continue
            # Label is "inside" if its left edge is past the left spine
            if bb.x0 > ax_bb.x0 + tol_px and bb.x1 < ax_bb.x1 - tol_px:
                issues.append({
                    "type": "tick_spine_overlap",
                    "severity": "warning",
                    "detail": (
                        f"Y-tick '{txt[:20]}' rendered inside plot area"
                    ),
                    "elements": [f"ytick:{txt[:20]}"],
                })
    return issues


# ===============================================================================
# Pass 21: Global font consistency check
# ===============================================================================

def _check_font_policy(fig, renderer, infos,
                        allowed_families=None,
                        max_title_label_diff=2.0):
    """Pass 21: Enforce global font consistency.

    Checks:
      a) Font family must be in allowed_families (Arial/Helvetica/DejaVu Sans).
      b) Title vs label font sizes should differ by at most max_title_label_diff pt.
      c) Flag any fontweight='bold' usage (except in explicit whitelist).
    """
    if allowed_families is None:
        allowed_families = {"Arial", "Helvetica", "DejaVu Sans", "sans-serif"}

    issues = []
    bold_count = 0
    wrong_family_examples = []
    title_sizes = []
    label_sizes = []

    for info in infos:
        if info.kind != "text":
            continue
        artist = info.artist
        if not isinstance(artist, Text):
            continue
        txt = artist.get_text().strip()
        if not txt:
            continue

        # Check font family
        family = artist.get_fontfamily()
        if family:
            top_family = family[0] if isinstance(family, list) else family
            if top_family not in allowed_families:
                wrong_family_examples.append(f"'{txt[:25]}' uses {top_family}")

        # Collect title vs label sizes
        if info.tag.startswith(("title", "suptitle")):
            title_sizes.append(artist.get_fontsize())
        elif info.tag.startswith(("xlabel", "ylabel")):
            label_sizes.append(artist.get_fontsize())

        # Check bold usage
        weight = artist.get_fontweight()
        if weight in ("bold", "heavy", "extra bold", 700, 800, 900):
            bold_count += 1

    # Report wrong families
    if wrong_family_examples:
        sample = wrong_family_examples[:3]
        issues.append({
            "type": "font_family_violation",
            "severity": "warning",
            "detail": (
                f"{len(wrong_family_examples)} text(s) use non-standard font: "
                f"{'; '.join(sample)}"
                + (f" ... +{len(wrong_family_examples) - 3} more"
                   if len(wrong_family_examples) > 3 else "")
            ),
            "elements": wrong_family_examples[:5],
        })

    # Report title/label size mismatch
    if title_sizes and label_sizes:
        mean_title = sum(title_sizes) / len(title_sizes)
        mean_label = sum(label_sizes) / len(label_sizes)
        diff = abs(mean_title - mean_label)
        if diff > max_title_label_diff:
            issues.append({
                "type": "title_label_size_mismatch",
                "severity": "info",
                "detail": (
                    f"Title avg {mean_title:.1f}pt vs label avg "
                    f"{mean_label:.1f}pt (diff={diff:.1f}pt, "
                    f"max={max_title_label_diff}pt)"
                ),
                "elements": [],
            })

    # Report bold usage
    if bold_count > 0:
        issues.append({
            "type": "bold_usage",
            "severity": "info",
            "detail": f"{bold_count} text(s) use bold fontweight",
            "elements": [],
        })

    return issues


# ===============================================================================
# Pass 22: Label density excess detection (colorbar-aware)
# ===============================================================================

def _check_label_density(fig, renderer, infos, density_threshold=0.70):
    """Pass 22: Detect axes where tick labels consume too much of the axis width/height.

    For each axes, estimates the total display width of visible tick labels
    and compares it to the available axis dimension.  If the total label
    footprint exceeds *density_threshold* (fraction) of the axis extent,
    emits a ``label_density_excess`` warning.

    **Colorbar axes are excluded** -- they are inherently narrow and would
    almost always trigger false-positive density warnings.

    This check enables the auto-refine loop to make *structural* layout
    changes (fewer subplots per row, rotate labels) rather than just
    growing margins.
    """
    issues: list[dict] = []

    for ax in fig.get_axes():
        if getattr(ax, 'name', None) == 'polar':
            continue
        if getattr(ax, '_is_legend_cell', False):
            continue
        # Skip colorbar axes -- they are narrow by design and their tick
        # density is governed by the colorbar tick locator, not by data layout.
        if _is_colorbar_axes(ax):
            continue
        ax_bb = _safe_bbox(ax, renderer)
        if ax_bb is None or ax_bb.width < 1 or ax_bb.height < 1:
            continue

        title = ax.get_title() or f"ax@{id(ax):#x}"

        # -- X-tick label density --
        xtick_widths = []
        max_xtick_len = 0
        for tl in ax.get_xticklabels():
            txt = tl.get_text().strip()
            if not txt:
                continue
            max_xtick_len = max(max_xtick_len, len(txt))
            bb = _safe_bbox(tl, renderer)
            if bb:
                xtick_widths.append(bb.width)

        if xtick_widths:
            total_w = sum(xtick_widths)
            ratio_x = total_w / ax_bb.width
            if ratio_x > density_threshold:
                issues.append({
                    "type": "label_density_excess",
                    "severity": "warning",
                    "detail": (
                        f"X-tick labels in '{title}' fill {ratio_x:.0%} of axis width "
                        f"({len(xtick_widths)} labels, max_len={max_xtick_len} chars)"
                    ),
                    "elements": [f"xtick_density:{title}"],
                    "axis_kind": "xtick",
                    "axes_title": title,
                    "num_labels": len(xtick_widths),
                    "max_label_length": max_xtick_len,
                    "density_ratio": ratio_x,
                })

        # -- Y-tick label density --
        ytick_heights = []
        max_ytick_len = 0
        for tl in ax.get_yticklabels():
            txt = tl.get_text().strip()
            if not txt:
                continue
            max_ytick_len = max(max_ytick_len, len(txt))
            bb = _safe_bbox(tl, renderer)
            if bb:
                ytick_heights.append(bb.height)

        if ytick_heights:
            total_h = sum(ytick_heights)
            ratio_y = total_h / ax_bb.height
            if ratio_y > density_threshold:
                issues.append({
                    "type": "label_density_excess",
                    "severity": "warning",
                    "detail": (
                        f"Y-tick labels in '{title}' fill {ratio_y:.0%} of axis height "
                        f"({len(ytick_heights)} labels, max_len={max_ytick_len} chars)"
                    ),
                    "elements": [f"ytick_density:{title}"],
                    "axis_kind": "ytick",
                    "axes_title": title,
                    "num_labels": len(ytick_heights),
                    "max_label_length": max_ytick_len,
                    "density_ratio": ratio_y,
                })

    return issues


# ===============================================================================
# Pass 32: Cross-axes text overlap detection (NEW)
# ===============================================================================

def _check_cross_axes_text_overlap(fig, renderer, tol_px=2.0, min_overlap_px2=10.0):
    """Pass 32: Detect text from different axes overlapping each other.

    When ``hspace`` or ``wspace`` is reduced, text elements belonging to
    *different* axes can collide in the gap between panels.  The classic
    case: Panel A's xlabel overlaps Panel D's title when rows are close.

    Unlike ``_check_cross_panel_spillover`` (Pass 8), which tests whether
    text enters another axes *bbox*, this pass tests whether text elements
    from *different* axes overlap **each other** in display space --
    regardless of whether either enters the other's axes rectangle.

    Colorbar-axes text (ticks, labels) is excluded to avoid noise from
    colorbars that are deliberately placed adjacent to data axes.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
    renderer : matplotlib renderer
    tol_px : float
        Shrink each text bbox by this many pixels before overlap test
        (reduces false positives from pixel-level adjacency).
    min_overlap_px2 : float
        Minimum overlap area (px^2) to report.

    Returns
    -------
    list[dict]
        Issues with ``type='cross_axes_text_overlap'``.
    """
    issues: list[dict] = []

    # Collect text elements keyed by owning axes id
    # Each entry: (text_string, bbox, axes_index, axes_id, role)
    ax_texts: list[tuple[str, Bbox, int, int, str]] = []

    for idx, ax in enumerate(fig.get_axes()):
        # Skip colorbar axes entirely -- their ticks are right next to
        # the parent axes and would produce false positives.
        if _is_colorbar_axes(ax) or getattr(ax, '_is_legend_cell', False):
            continue
        aid = id(ax)

        # Titles
        for title_obj in [ax.title, getattr(ax, '_left_title', None),
                          getattr(ax, '_right_title', None)]:
            if title_obj is None:
                continue
            txt = title_obj.get_text().strip()
            if not txt:
                continue
            bb = _safe_bbox(title_obj, renderer)
            if bb:
                ax_texts.append((txt[:40], bb, idx, aid, "title"))

        # Axis labels
        for lbl, role in [(ax.xaxis.label, "xlabel"),
                          (ax.yaxis.label, "ylabel")]:
            txt = lbl.get_text().strip()
            if not txt:
                continue
            bb = _safe_bbox(lbl, renderer)
            if bb:
                ax_texts.append((txt[:40], bb, idx, aid, role))

        # Tick labels (only check x-ticks and y-ticks, not annotations)
        for tl in ax.get_xticklabels():
            txt = tl.get_text().strip()
            if not txt:
                continue
            bb = _safe_bbox(tl, renderer)
            if bb:
                ax_texts.append((txt[:20], bb, idx, aid, "xtick"))
        for tl in ax.get_yticklabels():
            txt = tl.get_text().strip()
            if not txt:
                continue
            bb = _safe_bbox(tl, renderer)
            if bb:
                ax_texts.append((txt[:20], bb, idx, aid, "ytick"))

    # Pairwise check across different axes only
    seen_pairs: set[tuple[int, int]] = set()
    for i in range(len(ax_texts)):
        for j in range(i + 1, len(ax_texts)):
            txt_i, bb_i, ax_idx_i, aid_i, role_i = ax_texts[i]
            txt_j, bb_j, ax_idx_j, aid_j, role_j = ax_texts[j]

            # Only cross-axes pairs
            if aid_i == aid_j:
                continue

            # Deduplicate: only report one issue per pair of axes indices
            # for the same role combination to avoid flooding
            pair_key = (min(ax_idx_i, ax_idx_j), max(ax_idx_i, ax_idx_j))
            role_pair = tuple(sorted([role_i, role_j]))

            si = _shrink(bb_i, tol_px)
            sj = _shrink(bb_j, tol_px)
            if si is None or sj is None:
                continue
            if not si.overlaps(sj):
                continue

            area = _overlap_area(bb_i, bb_j)
            if area < min_overlap_px2:
                continue

            dedup_key = (pair_key[0], pair_key[1])
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)

            issues.append({
                "type": "cross_axes_text_overlap",
                "severity": "warning",
                "detail": (
                    f"{role_i} '{txt_i}' (axes {ax_idx_i}) overlaps "
                    f"{role_j} '{txt_j}' (axes {ax_idx_j}) -- "
                    f"{area:.0f} px\u00b2; consider increasing hspace/wspace"
                ),
                "elements": [
                    f"{role_i}:{txt_i}:ax{ax_idx_i}",
                    f"{role_j}:{txt_j}:ax{ax_idx_j}",
                ],
            })

    return issues


# ===============================================================================
# Pass 33: Panel label placement detection (NEW)
# ===============================================================================

_PANEL_LABEL_RE = re.compile(
    r'^[\(\[\{]?\s*[a-zA-Z]\s*[\)\]\}]?$'   # (a), [B], {c}, a), (A, etc.
)


def _check_panel_label_placement(fig, renderer, margin_px=5.0):
    """Pass 33: Warn if panel labels (a)(b)(c) are inside axes bounds.

    Publication-quality figures typically place panel labels *outside*
    the axes area (e.g. top-left corner, slightly above and to the left
    of the plot).  Labels placed inside the axes compete with data content
    for attention and may be occluded by bars, scatter points, or legends.

    This check inspects figure-level text objects (``fig.text()``) and
    per-axes text objects that look like single-letter panel labels.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
    renderer : matplotlib renderer
    margin_px : float
        A label whose bbox is fully inside axes bounds + this margin is
        considered "inside".

    Returns
    -------
    list[dict]
        Issues with ``type='panel_label_inside_axes'``.
    """
    issues: list[dict] = []

    # Collect axes bboxes (exclude colorbars and invisible/off axes)
    ax_bboxes: list[tuple[int, Bbox]] = []
    for idx, ax in enumerate(fig.get_axes()):
        if _is_colorbar_axes(ax):
            continue
        # Skip axes that have been turned off (e.g. single-axes diagrams
        # where the entire figure is one canvas).  Panel labels drawn in
        # data coords inside such an axes are intentional.
        if not ax.axison:
            continue
        bb = _safe_bbox(ax, renderer)
        if bb:
            ax_bboxes.append((idx, bb))

    if not ax_bboxes:
        return issues

    # Check figure-level text objects
    for child in fig.texts:
        if not child.get_visible():
            continue
        txt = child.get_text().strip()
        if not txt:
            continue
        if not _PANEL_LABEL_RE.match(txt):
            continue

        lbl_bb = _safe_bbox(child, renderer)
        if lbl_bb is None:
            continue

        # Is the label fully inside any axes?
        for ax_idx, ax_bb in ax_bboxes:
            if (lbl_bb.x0 >= ax_bb.x0 - margin_px
                    and lbl_bb.y0 >= ax_bb.y0 - margin_px
                    and lbl_bb.x1 <= ax_bb.x1 + margin_px
                    and lbl_bb.y1 <= ax_bb.y1 + margin_px):
                issues.append({
                    "type": "panel_label_inside_axes",
                    "severity": "warning",
                    "detail": (
                        f"Panel label '{txt}' is inside axes {ax_idx} bounds; "
                        f"consider placing it outside the plot area"
                    ),
                    "elements": [f"panel_label:{txt}", f"axes:{ax_idx}"],
                })
                break  # only report once per label

    # Also check per-axes text objects (some workflows use ax.text() for labels)
    for ax_idx, ax_bb in ax_bboxes:
        ax = fig.get_axes()[ax_idx]
        for child in ax.texts:
            if not child.get_visible():
                continue
            txt = child.get_text().strip()
            if not txt:
                continue
            if not _PANEL_LABEL_RE.match(txt):
                continue

            lbl_bb = _safe_bbox(child, renderer)
            if lbl_bb is None:
                continue

            # ax.text() objects in data/axes coords are inside by definition;
            # only flag if the bbox is fully within the axes display bbox
            if (lbl_bb.x0 >= ax_bb.x0 - margin_px
                    and lbl_bb.y0 >= ax_bb.y0 - margin_px
                    and lbl_bb.x1 <= ax_bb.x1 + margin_px
                    and lbl_bb.y1 <= ax_bb.y1 + margin_px):
                issues.append({
                    "type": "panel_label_inside_axes",
                    "severity": "warning",
                    "detail": (
                        f"Panel label '{txt}' is placed inside axes {ax_idx}; "
                        f"consider using fig.text() outside the plot area"
                    ),
                    "elements": [f"panel_label:{txt}", f"axes:{ax_idx}"],
                })

    return issues
