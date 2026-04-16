"""VCD text-related detection passes (1, 5, 8, 9)."""

from __future__ import annotations

import re

from matplotlib.text import Text
from matplotlib.transforms import Bbox

from .vcd_core import _ArtistInfo, _safe_bbox, _shrink, _overlap_area, _sides_outside, _artist_label, _is_colorbar_axes


def _check_text_overlaps(infos: list[_ArtistInfo], tol_px: float = 2.5):
    """Pass 1: Pairwise text overlap detection."""
    texts = [a for a in infos if a.kind == "text"]
    issues = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            # Skip xtick-vs-ytick pairs (naturally meet at axes corner)
            tags = {a.tag.split(":")[0].strip(), b.tag.split(":")[0].strip()}
            if tags == {"xtick", "ytick"}:
                continue
            sa = _shrink(a.bbox, tol_px)
            sb = _shrink(b.bbox, tol_px)
            if sa and sb and sa.overlaps(sb):
                issues.append({
                    "type": "text_overlap",
                    "severity": "warning",
                    "detail": f"'{a.tag}' overlaps '{b.tag}'",
                    "elements": [a.tag, b.tag],
                })
    return issues


def _is_significance_marker(tag: str) -> bool:
    """Return True if *tag* looks like a statistical significance annotation.

    Catches common patterns: ``*``, ``**``, ``***``, ``ns``, ``p<0.05``, etc.
    """
    if not tag.startswith("annotation:"):
        return False
    txt = tag.split(":", 1)[1].strip()
    if re.fullmatch(r"\*{1,4}", txt):          # *, **, ***, ****
        return True
    if txt.lower() in ("ns", "n.s.", "ns."):   # not-significant
        return True
    if re.match(r"p\s*[<>=]", txt, re.I):       # p<0.05, P = 0.01 ...
        return True
    return False


def _check_text_vs_artist_overlap(
    infos: list[_ArtistInfo],
    tol_px: float = 2.0,
    min_overlap_px2: float = 150.0,
):
    """Pass 5: Check if graphical content overlaps text labels.

    In-axes annotations (especially significance markers like ``*``, ``ns``)
    overlapping with data artists in the same panel are elevated to warnings.
    """
    texts = [a for a in infos if a.kind == "text"]
    graphics = [a for a in infos
                if a.kind in ("collection", "patch", "line", "image")]
    issues = []
    for t in texts:
        tb = _shrink(t.bbox, tol_px)
        if not tb:
            continue
        for g in graphics:
            area = _overlap_area(tb, g.bbox)
            if area > min_overlap_px2:
                # Determine severity: in-axes annotations overlapping with
                # data artists in the same panel are warnings (especially
                # significance markers like *, **, ns, etc.)
                is_annotation = t.tag.startswith("annotation:")
                same_axes = (t.ax_id == g.ax_id) and (t.ax_id is not None)
                if is_annotation and same_axes and _is_significance_marker(t.tag):
                    severity = "warning"
                    issue_type = "significance_marker_overlap"
                elif is_annotation and same_axes:
                    # Non-significance annotations on bars/patches are
                    # intentional (value labels, fold-change, etc.)
                    severity = "info"
                    issue_type = "annotation_data_overlap"
                else:
                    severity = "info"
                    issue_type = "text_artist_overlap"

                issues.append({
                    "type": issue_type,
                    "severity": severity,
                    "detail": (f"Text '{t.tag}' overlaps content "
                               f"'{g.tag}' ({area:.0f} px\u00b2)"),
                    "elements": [t.tag, g.tag],
                })
    return issues


def _check_cross_panel_spillover(fig, renderer, tol_px=5.0):
    """Pass 8: Detect content from one axes spilling into an adjacent axes."""
    axes_list = [
        ax for ax in fig.get_axes()
        if not getattr(ax, '_is_legend_cell', False) and not _is_colorbar_axes(ax)
    ]
    if len(axes_list) < 2:
        return []

    issues = []
    ax_bboxes = []
    for ax in axes_list:
        bb = _safe_bbox(ax, renderer)
        if bb:
            ax_bboxes.append((ax, bb))

    for i, (ax_i, bb_i) in enumerate(ax_bboxes):
        if getattr(ax_i, '_is_legend_cell', False):
            continue
        for child in ax_i.get_children():
            if not child.get_visible():
                continue
            if isinstance(child, Text):
                child_bb = _safe_bbox(child, renderer)
                if child_bb is None:
                    continue
                for j, (ax_j, bb_j) in enumerate(ax_bboxes):
                    if i == j:
                        continue
                    if getattr(ax_j, '_is_legend_cell', False):
                        continue
                    if (
                        abs(bb_i.x0 - bb_j.x0) < 1.0
                        and abs(bb_i.y0 - bb_j.y0) < 1.0
                        and abs(bb_i.x1 - bb_j.x1) < 1.0
                        and abs(bb_i.y1 - bb_j.y1) < 1.0
                    ):
                        continue  # twinx/twiny axes share the same panel region
                    area = _overlap_area(child_bb, bb_j)
                    if area > 50:
                        txt = getattr(child, "_text", "")[:30]
                        issues.append({
                            "type": "cross_panel_spillover",
                            "severity": "warning",
                            "detail": (
                                f"Text '{txt}' from axes {i} "
                                f"spills into axes {j} ({area:.0f} px\u00b2)"
                            ),
                            "elements": [f"ax{i}", f"ax{j}"],
                        })
    return issues


def _check_panel_label_overlap(fig, renderer, infos, tol_px=2.0):
    """Pass 9: Check that panel labels (A), (B), etc. don't overlap content or text.

    Panel labels must be clearly visible; any overlap with data content,
    axis text (titles, ticks, axis labels), or legend text is a warning.
    """
    panel_texts = []
    for child in fig.texts:
        txt = getattr(child, "_text", "")
        if txt and txt.startswith("(") and txt.endswith(")") and len(txt) <= 4:
            bb = _safe_bbox(child, renderer)
            if bb:
                panel_texts.append((txt, bb, child))

    issues = []
    for txt, pbb, panel_obj in panel_texts:
        # Check against graphical content (collection, patch, image, line)
        for a in infos:
            if a.kind in ("collection", "patch", "image", "line"):
                if a.artist is panel_obj:
                    continue
                area = _overlap_area(pbb, a.bbox)
                if area > 20:
                    issues.append({
                        "type": "panel_label_overlap",
                        "severity": "warning",
                        "detail": (
                            f"Panel label '{txt}' overlaps "
                            f"content '{a.tag}' ({area:.0f} px\u00b2)"
                        ),
                        "elements": [txt, a.tag],
                    })

        # Check against all text (titles, ticks, labels, legend text, annotations)
        for a in infos:
            if a.kind == "text":
                if a.artist is panel_obj:
                    continue
                area = _overlap_area(pbb, a.bbox)
                if area > tol_px:
                    issues.append({
                        "type": "panel_label_text_overlap",
                        "severity": "warning",
                        "detail": (
                            f"Panel label '{txt}' overlaps "
                            f"text '{a.tag}' ({area:.0f} px\u00b2)"
                        ),
                        "elements": [txt, a.tag],
                    })

        # Check against other panel labels
        for txt2, pbb2, panel_obj2 in panel_texts:
            if panel_obj2 is panel_obj:
                continue
            area = _overlap_area(pbb, pbb2)
            if area > tol_px:
                issues.append({
                    "type": "panel_label_mutual_overlap",
                    "severity": "warning",
                    "detail": (
                        f"Panel labels '{txt}' and '{txt2}' overlap ({area:.0f} px\u00b2)"
                    ),
                    "elements": [txt, txt2],
                })
    return issues
