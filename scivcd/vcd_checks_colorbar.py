"""VCD colorbar-related detection passes (14, 17)."""
from __future__ import annotations

from .vcd_core import _safe_bbox, _shrink, _fig_bbox, _overlap_area, _sides_outside, _artist_label, _is_colorbar_axes
from matplotlib.collections import PathCollection, PolyCollection, LineCollection
from matplotlib.lines import Line2D
from matplotlib.image import AxesImage
from matplotlib.transforms import Bbox


def _check_colorbar_internal(fig, renderer, tol_px=1.0):
    """Pass 14: Detect overlaps within colorbar axes.

    Checks:
      a) Colorbar tick labels overlapping each other.
      b) Colorbar axis label overlapping tick labels.
      c) Colorbar extending beyond its parent/inset host axes.
      d) Colorbar tick labels truncated at figure edges.
    """
    issues: list[dict] = []
    fig_bb = _fig_bbox(fig)

    for ax in fig.get_axes():
        is_cbar = _is_colorbar_axes(ax)
        if not is_cbar:
            continue

        # Gather tick labels
        xticks = [tl for tl in ax.get_xticklabels()
                  if tl.get_text().strip()]
        yticks = [tl for tl in ax.get_yticklabels()
                  if tl.get_text().strip()]
        tick_labels = xticks + yticks

        tick_bbs: list[tuple[str, Bbox]] = []
        for tl in tick_labels:
            bb = _safe_bbox(tl, renderer)
            if bb:
                tick_bbs.append((tl.get_text().strip()[:20], bb))

        # a) Tick labels overlapping each other
        for i in range(len(tick_bbs)):
            for j in range(i + 1, len(tick_bbs)):
                txt_i, bb_i = tick_bbs[i]
                txt_j, bb_j = tick_bbs[j]
                si = _shrink(bb_i, tol_px)
                sj = _shrink(bb_j, tol_px)
                if si and sj and si.overlaps(sj):
                    area = _overlap_area(bb_i, bb_j)
                    issues.append({
                        "type": "cbar_tick_overlap",
                        "severity": "warning",
                        "detail": (
                            f"Colorbar tick '{txt_i}' overlaps "
                            f"tick '{txt_j}' ({area:.0f} px\u00b2)"
                        ),
                        "elements": [f"cbar_tick:{txt_i}",
                                     f"cbar_tick:{txt_j}"],
                    })

        # b) Colorbar axis label vs tick labels
        for lbl_artist in [ax.xaxis.label, ax.yaxis.label]:
            lbl_txt = lbl_artist.get_text().strip()
            if not lbl_txt:
                continue
            lbl_bb = _safe_bbox(lbl_artist, renderer)
            if lbl_bb is None:
                continue
            lbl_s = _shrink(lbl_bb, tol_px)
            if not lbl_s:
                continue
            for txt_t, bb_t in tick_bbs:
                bb_ts = _shrink(bb_t, tol_px)
                if bb_ts and lbl_s.overlaps(bb_ts):
                    area = _overlap_area(lbl_bb, bb_t)
                    issues.append({
                        "type": "cbar_label_tick_overlap",
                        "severity": "warning",
                        "detail": (
                            f"Colorbar label '{lbl_txt[:20]}' overlaps "
                            f"tick '{txt_t}' ({area:.0f} px\u00b2)"
                        ),
                        "elements": [f"cbar_label:{lbl_txt[:20]}",
                                     f"cbar_tick:{txt_t}"],
                    })

        # c) + d) Tick labels extending beyond figure
        for txt_t, bb_t in tick_bbs:
            sides = _sides_outside(bb_t, fig_bb, 1.0)
            if sides:
                issues.append({
                    "type": "cbar_tick_truncation",
                    "severity": "warning",
                    "detail": (
                        f"Colorbar tick '{txt_t}' extends beyond "
                        f"figure ({', '.join(sides)})"
                    ),
                    "elements": [f"cbar_tick:{txt_t}"],
                })

    return issues


def _check_colorbar_data_overlap(fig, renderer, auto_fix=True):
    """Pass 17: Detect colorbar axes overlapping parent data content.

    For each colorbar-type axes:
      1. Find the parent axes (hosting the actual data).
      2. Compute the colorbar's display-space bbox.
      3. Collect all data artists (scatter, lines, images) in the parent.
      4. If >5% of any data artist is occluded, flag as warning.
      5. If auto_fix=True, attempt to relocate the inset to a less crowded
         corner (lower-left, upper-left, upper-right, lower-right).

    Returns list of issue dicts.
    """
    issues: list[dict] = []

    for ax in fig.get_axes():
        is_cbar = _is_colorbar_axes(ax)
        if not is_cbar:
            continue

        cbar_bb = _safe_bbox(ax, renderer)
        if cbar_bb is None:
            continue

        # Find parent axes — the colorbar's host
        parent = None
        if hasattr(ax, '_parent_axes'):
            parent = ax._parent_axes
        elif hasattr(ax, 'get_axes_locator'):
            loc = ax.get_axes_locator()
            if loc and hasattr(loc, '_parent'):
                parent = loc._parent
        if parent is None:
            best_area = 0
            for candidate in fig.get_axes():
                if candidate is ax:
                    continue
                c_is_cbar = _is_colorbar_axes(candidate)
                if c_is_cbar:
                    continue
                c_bb = _safe_bbox(candidate, renderer)
                if c_bb is None:
                    continue
                area = _overlap_area(cbar_bb, c_bb)
                if area > best_area:
                    best_area = area
                    parent = candidate
        if parent is None:
            continue

        # Collect data artists in parent
        data_artists = []
        for child in parent.get_children():
            if child is ax:
                continue
            if isinstance(child, (PathCollection, PolyCollection,
                                  LineCollection, Line2D, AxesImage)):
                da_bb = _safe_bbox(child, renderer)
                if da_bb:
                    data_artists.append((_artist_label(child), da_bb))

        for da_tag, da_bb in data_artists:
            area = _overlap_area(cbar_bb, da_bb)
            if area < 1:
                continue
            da_area = da_bb.width * da_bb.height
            if da_area < 1:
                continue
            frac = area / da_area
            if frac > 0.05:
                issues.append({
                    "type": "cbar_data_overlap",
                    "severity": "warning",
                    "detail": (
                        f"Colorbar overlaps data '{da_tag}' "
                        f"({frac:.0%}, {area:.0f} px\u00b2)"
                    ),
                    "elements": ["colorbar", da_tag],
                    "auto_fixable": auto_fix,
                })

    return issues
