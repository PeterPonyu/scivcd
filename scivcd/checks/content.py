"""CONTENT-category detectors.

Ported from ``experiments/scivcd-lifetime/scripts/vcd/lifecycle/tier2_geometry.py``.
"""
from __future__ import annotations

from typing import Any

from matplotlib.text import Text

from scivcd.core import (
    Category,
    CheckSpec,
    Finding,
    ScivcdConfig,
    Severity,
    Stage,
    register,
)


def _data_axes(fig: Any) -> list:
    out = []
    for ax in fig.get_axes():
        if getattr(ax, "_colorbar", None):
            continue
        out.append(ax)
    return out


def _axes_area_inches(ax: Any, fig: Any) -> float:
    try:
        bbox_fig = ax.get_position()
        fig_w, fig_h = fig.get_size_inches()
        return max(bbox_fig.width * fig_w, 0.0) * max(bbox_fig.height * fig_h, 0.0)
    except Exception:
        return 0.0


def _overlap_area(a: Any, b: Any) -> float:
    """Return pixel overlap area between two display-space bboxes."""
    try:
        x0 = max(float(a.x0), float(b.x0))
        y0 = max(float(a.y0), float(b.y0))
        x1 = min(float(a.x1), float(b.x1))
        y1 = min(float(a.y1), float(b.y1))
    except Exception:
        return 0.0
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _shrink_bbox(bb: Any, pad_px: float) -> Any:
    """Return a slightly shrunken bbox to avoid edge-touch false positives."""
    try:
        from matplotlib.transforms import Bbox
        return Bbox.from_extents(
            float(bb.x0) + pad_px,
            float(bb.y0) + pad_px,
            float(bb.x1) - pad_px,
            float(bb.y1) - pad_px,
        )
    except Exception:
        return bb


# ---------------------------------------------------------------------------
# content_clipped_at_render
# ---------------------------------------------------------------------------

def _fire_content_clipped_at_render(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag Text artists whose rendered bbox extends past the figure canvas."""
    out: list[Finding] = []
    tol = 3.0
    try:
        renderer = fig.canvas.get_renderer()
    except Exception:
        return out
    try:
        fig_bb = fig.bbox
    except Exception:
        return out

    tick_label_ids: set[int] = set()
    try:
        for ax in fig.get_axes():
            for lbl in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
                tick_label_ids.add(id(lbl))
    except Exception:
        tick_label_ids = set()

    seen = set()
    for artist in fig.findobj(Text):
        try:
            txt = (artist.get_text() or "").strip()
            if not txt:
                continue
            bb = artist.get_window_extent(renderer)
        except Exception:
            continue
        if id(artist) in seen:
            continue
        seen.add(id(artist))
        if id(artist) in tick_label_ids:
            continue
        gid = ""
        try:
            g = artist.get_gid()
            if isinstance(g, str):
                gid = g
        except Exception:
            pass
        if gid.startswith("tick"):
            continue
        sides: list[str] = []
        if bb.x0 < fig_bb.x0 - tol:
            sides.append(f"left {fig_bb.x0 - bb.x0:.0f}px")
        if bb.x1 > fig_bb.x1 + tol:
            sides.append(f"right {bb.x1 - fig_bb.x1:.0f}px")
        if bb.y0 < fig_bb.y0 - tol:
            sides.append(f"bottom {fig_bb.y0 - bb.y0:.0f}px")
        if bb.y1 > fig_bb.y1 + tol:
            sides.append(f"top {bb.y1 - fig_bb.y1:.0f}px")
        if not sides:
            continue
        out.append(Finding(
            check_id="content_clipped_at_render",
            severity=Severity.HIGH,
            category=Category.CONTENT,
            stage=Stage.TIER2,
            message=(
                f"Text '{txt[:30]}' extends past figure canvas on "
                + ", ".join(sides)
            ),
            call_site=None,
            fix_suggestion=(
                "reposition the text inside the canvas (use axes-relative "
                "coords or adjust bbox_to_anchor) or enlarge the figure"
            ),
            artist=artist,
        ))
    return out


register(CheckSpec(
    id="content_clipped_at_render",
    severity=Severity.HIGH,
    category=Category.CONTENT,
    stage=Stage.TIER2,
    fire=_fire_content_clipped_at_render,
    description="Text artist rendered outside the figure canvas",
))


# ---------------------------------------------------------------------------
# text_density_crowding
# ---------------------------------------------------------------------------

def _fire_text_density_crowding(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag axes whose free-floating Text count per square inch exceeds the
    density threshold.
    """
    out: list[Finding] = []
    density_max = config.text_density_max_per_sqin  # default 2.2
    for ax in _data_axes(fig):
        area = _axes_area_inches(ax, fig)
        if area < 1.0:
            continue
        try:
            n_text = len([t for t in ax.texts if (t.get_text() or "").strip()])
        except Exception:
            n_text = 0
        density = n_text / max(area, 0.25)
        if density > density_max:
            out.append(Finding(
                check_id="text_density_crowding",
                severity=Severity.MEDIUM,
                category=Category.CONTENT,
                stage=Stage.TIER2,
                message=(
                    f"{n_text} free-floating text artists on {area:.1f}in^2 "
                    f"axes (density {density:.2f}/in^2 > {density_max:.2f}/in^2)"
                ),
                call_site=None,
                fix_suggestion=(
                    "consolidate multiple annotations into a single compact "
                    "box, drop redundant labels, or widen the axes"
                ),
                artist=ax,
            ))
    return out


register(CheckSpec(
    id="text_density_crowding",
    severity=Severity.MEDIUM,
    category=Category.CONTENT,
    stage=Stage.TIER2,
    fire=_fire_text_density_crowding,
    description="Free-floating text artists per sq-inch exceed density limit",
    config_keys=("text_density_max_per_sqin",),
))


# ---------------------------------------------------------------------------
# annotation_data_overlap
# ---------------------------------------------------------------------------

def _fire_annotation_data_overlap(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag in-axes annotations whose rendered bbox overlaps data artists.

    This check intentionally scopes to free-floating `ax.text(...)` / annotate
    content inside the same axes rather than titles, tick labels, or legends.
    It is designed to catch the exact publication smell surfaced during the
    figure-polish loops: explanatory callouts that compete with plotted data.
    """
    out: list[Finding] = []
    min_area = float(config.min_overlap_px2)
    shrink_px = 2.0
    try:
        renderer = fig.canvas.get_renderer()
    except Exception:
        return out

    for ax in _data_axes(fig):
        data_artists: list[Any] = []
        for artist in list(getattr(ax, "lines", [])) + list(getattr(ax, "collections", [])) + list(getattr(ax, "patches", [])) + list(getattr(ax, "images", [])):
            try:
                if not artist.get_visible():
                    continue
                if artist is getattr(ax, "patch", None):
                    continue
                bb = artist.get_window_extent(renderer)
            except Exception:
                continue
            data_artists.append((artist, bb))
        if not data_artists:
            continue

        for text in getattr(ax, "texts", []):
            try:
                if not text.get_visible():
                    continue
                content = (text.get_text() or "").strip()
                if not content:
                    continue
                bb = _shrink_bbox(text.get_window_extent(renderer), shrink_px)
            except Exception:
                continue

            max_overlap = 0.0
            culprit = None
            for artist, artist_bb in data_artists:
                area = _overlap_area(bb, artist_bb)
                if area > max_overlap:
                    max_overlap = area
                    culprit = artist
            if max_overlap < min_area or culprit is None:
                continue

            artist_type = type(culprit).__name__
            out.append(Finding(
                check_id="annotation_data_overlap",
                severity=Severity.LOW,
                category=Category.CONTENT,
                stage=Stage.TIER2,
                message=(
                    f"annotation '{content[:36]}' overlaps plotted data "
                    f"({artist_type}, {max_overlap:.0f} px²)"
                ),
                call_site=None,
                fix_suggestion=(
                    "move the annotation into whitespace, convert it into a "
                    "legend/subtitle, or reduce its box size so it no longer "
                    "sits on top of marks"
                ),
                artist=text,
            ))
    return out


register(CheckSpec(
    id="annotation_data_overlap",
    severity=Severity.LOW,
    category=Category.CONTENT,
    stage=Stage.TIER2,
    fire=_fire_annotation_data_overlap,
    description="Free-floating annotation overlaps plotted data in the same axes",
    config_keys=("min_overlap_px2",),
))


# ---------------------------------------------------------------------------
# annotation_style_risk
# ---------------------------------------------------------------------------

def _fire_annotation_style_risk(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag visually fragile in-panel annotations.

    Human QA repeatedly caught annotation labels that were small, italic,
    colored, or backed by a white bbox. Those are not always wrong, but the
    combination is a useful low-severity signal that the annotation may be
    compensating for a crowded panel instead of improving readability.
    """
    out: list[Finding] = []
    min_pt = float(config.annotation_min_pt)
    for ax in _data_axes(fig):
        for text in getattr(ax, "texts", []):
            try:
                if not text.get_visible():
                    continue
                content = (text.get_text() or "").strip()
                if not content:
                    continue
                size = float(text.get_fontsize())
                style = str(text.get_fontstyle()).lower()
                color = str(text.get_color()).lower()
                has_bbox = text.get_bbox_patch() is not None
            except Exception:
                continue

            risk_reasons = []
            if size < min_pt:
                risk_reasons.append(f"small {size:.1f}pt text")
            if style not in {"normal", "regular"}:
                risk_reasons.append(f"{style} style")
            if color not in {"black", "#000000", "#111111", "#222222", "#333333", "#444444"}:
                risk_reasons.append(f"colored text ({color})")
            if has_bbox:
                risk_reasons.append("boxed annotation")
            if len(risk_reasons) < 2:
                continue

            out.append(Finding(
                check_id="annotation_style_risk",
                severity=Severity.LOW,
                category=Category.CONTENT,
                stage=Stage.TIER2,
                message=(
                    f"annotation '{content[:36]}' has fragile styling: "
                    + ", ".join(risk_reasons)
                ),
                call_site=None,
                fix_suggestion=(
                    "prefer >=10pt neutral regular text without a white bbox, "
                    "or move the statistic into a title/caption/legend slot"
                ),
                artist=text,
            ))
    return out


register(CheckSpec(
    id="annotation_style_risk",
    severity=Severity.LOW,
    category=Category.CONTENT,
    stage=Stage.TIER2,
    fire=_fire_annotation_style_risk,
    description="In-panel annotation uses fragile small/colored/italic/boxed styling",
    config_keys=("annotation_min_pt",),
))


__all__ = [
    "_fire_content_clipped_at_render",
    "_fire_text_density_crowding",
    "_fire_annotation_data_overlap",
    "_fire_annotation_style_risk",
]
