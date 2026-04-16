"""VCD core: geometry utilities, ArtistInfo, and the artist collector."""

from __future__ import annotations

import numpy as np
from matplotlib.text import Text
from matplotlib.patches import Patch, FancyBboxPatch
from matplotlib.collections import PathCollection, PolyCollection, LineCollection
from matplotlib.lines import Line2D
from matplotlib.image import AxesImage
from matplotlib.transforms import Bbox


# ═══════════════════════════════════════════════════════════════════════════════
# Geometry helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_bbox(artist, renderer) -> Bbox | None:
    """Try to extract display-coords BBox from any artist."""
    try:
        bb = artist.get_window_extent(renderer)
        if bb is not None and bb.width > 0 and bb.height > 0:
            return bb
    except Exception:
        pass
    return None


def _shrink(bb: Bbox, px: float) -> Bbox | None:
    """Shrink a Bbox by *px* pixels on each side; return None if degenerate."""
    b = Bbox.from_extents(bb.x0 + px, bb.y0 + px, bb.x1 - px, bb.y1 - px)
    if b.width > 0 and b.height > 0:
        return b
    return None


def _fig_bbox(fig) -> Bbox:
    """Figure bounding box in display coordinates."""
    w, h = fig.get_size_inches()
    dpi = fig.dpi
    return Bbox.from_bounds(0, 0, w * dpi, h * dpi)


def _overlap_area(a: Bbox, b: Bbox) -> float:
    """Pixel area of intersection between two Bboxes (0 if no overlap)."""
    x0 = max(a.x0, b.x0)
    y0 = max(a.y0, b.y0)
    x1 = min(a.x1, b.x1)
    y1 = min(a.y1, b.y1)
    if x1 > x0 and y1 > y0:
        return (x1 - x0) * (y1 - y0)
    return 0.0


def _sides_outside(bb: Bbox, fig_bb: Bbox, tol: float = 1.0) -> list[str]:
    """Which sides of *bb* extend beyond *fig_bb*."""
    sides = []
    if bb.x0 < fig_bb.x0 - tol:
        sides.append("left")
    if bb.y0 < fig_bb.y0 - tol:
        sides.append("bottom")
    if bb.x1 > fig_bb.x1 + tol:
        sides.append("right")
    if bb.y1 > fig_bb.y1 + tol:
        sides.append("top")
    return sides


def _is_colorbar_axes(ax) -> bool:
    """Return True if *ax* is a colorbar axes (not a data-plotting axes).

    Centralises the heuristic so every check module uses the same logic.
    Matplotlib marks colorbar axes with ``_colorbar_info`` (>=3.6) or
    the older ``_colorbar`` attribute.
    """
    return (hasattr(ax, '_colorbar_info')
            or getattr(ax, '_colorbar', None) is not None)


def _artist_label(artist, hint: str = "") -> str:
    """Human-readable tag for an artist."""
    if isinstance(artist, Text):
        s = artist.get_text().strip()
        return f"{hint}: {s[:50]}" if hint else f"text: {s[:50]}"
    cls = type(artist).__name__
    label = getattr(artist, "_label", "") or ""
    tag = f"{cls}"
    if label and not label.startswith("_"):
        tag += f"({label[:30]})"
    return f"{hint}: {tag}" if hint else tag


# ═══════════════════════════════════════════════════════════════════════════════
# ArtistInfo carrier
# ═══════════════════════════════════════════════════════════════════════════════

class _ArtistInfo:
    """Lightweight carrier for an artist + its display bbox + metadata."""
    __slots__ = ("artist", "bbox", "tag", "kind", "ax_id")

    def __init__(self, artist, bbox, tag, kind, ax_id=None):
        self.artist = artist
        self.bbox = bbox
        self.tag = tag
        self.kind = kind        # "text" | "patch" | "collection" | "line" | "image" | "legend"
        self.ax_id = ax_id      # id(ax) if owned by a specific axes


# ═══════════════════════════════════════════════════════════════════════════════
# Artist collector
# ═══════════════════════════════════════════════════════════════════════════════

def _collect_artists(fig, renderer) -> list[_ArtistInfo]:
    """Walk *fig* and collect all visible artists with valid bboxes."""
    infos: list[_ArtistInfo] = []
    seen_legend_ids: set[int] = set()

    # Identify colorbar axes to annotate properly
    cbar_axes = set()
    for ax in fig.get_axes():
        if _is_colorbar_axes(ax):
            cbar_axes.add(id(ax))

    for ax in fig.get_axes():
        is_cbar = id(ax) in cbar_axes
        pfx = "cbar" if is_cbar else ""
        aid = id(ax)

        # Skip axis labels and ticks on invisible axes (e.g. legend cells
        # created by add_shared_legend_axes with set_axis_off()).
        _collect_axis_text = ax.axison

        # ── Text artists ───────────────────────────────────────────────
        # Titles
        for title_obj in [ax.title, ax._left_title, ax._right_title]:
            if title_obj and title_obj.get_text().strip():
                bb = _safe_bbox(title_obj, renderer)
                if bb:
                    infos.append(_ArtistInfo(
                        title_obj, bb,
                        _artist_label(title_obj, f"{pfx}title"),
                        "text", aid))

        if _collect_axis_text:
            # Axis labels
            for lbl, hint in [(ax.xaxis.label, f"{pfx}xlabel"),
                              (ax.yaxis.label, f"{pfx}ylabel")]:
                if lbl.get_text().strip():
                    bb = _safe_bbox(lbl, renderer)
                    if bb:
                        infos.append(_ArtistInfo(lbl, bb,
                                                 _artist_label(lbl, hint),
                                                 "text", aid))

            # Tick labels
            for tl in ax.get_xticklabels():
                if tl.get_text().strip():
                    bb = _safe_bbox(tl, renderer)
                    if bb:
                        infos.append(_ArtistInfo(
                            tl, bb,
                            _artist_label(tl, "cbar_tick" if is_cbar else "xtick"),
                            "text", aid))
            for tl in ax.get_yticklabels():
                if tl.get_text().strip():
                    bb = _safe_bbox(tl, renderer)
                    if bb:
                        infos.append(_ArtistInfo(
                            tl, bb,
                            _artist_label(tl, "cbar_tick" if is_cbar else "ytick"),
                            "text", aid))

        if not is_cbar:
            # Manual ax.text() objects
            for txt in ax.texts:
                if txt.get_text().strip():
                    bb = _safe_bbox(txt, renderer)
                    if bb:
                        infos.append(_ArtistInfo(
                            txt, bb, _artist_label(txt, "annotation"),
                            "text", aid))

            # Legend
            legend = ax.get_legend()
            if legend is not None:
                seen_legend_ids.add(id(legend))
                bb = _safe_bbox(legend, renderer)
                if bb:
                    infos.append(_ArtistInfo(
                        legend, bb, "legend_box", "legend", aid))
                for txt in legend.get_texts():
                    if txt.get_text().strip():
                        tbb = _safe_bbox(txt, renderer)
                        if tbb:
                            infos.append(_ArtistInfo(
                                txt, tbb,
                                _artist_label(txt, "legend_text"),
                                "text", aid))

        # ── Graphical artists ──────────────────────────────────────────
        for child in ax.get_children():
            if isinstance(child, Text):
                continue   # already handled above
            if not getattr(child, "get_visible", lambda: True)():
                continue
            if child is ax.patch:
                continue
            label = getattr(child, "_label", "") or ""
            if label.startswith("_") and label not in ("_nolegend_",):
                if isinstance(child, (Line2D,)):
                    if child.get_linestyle() in ("--", ":", "-."):
                        continue
                continue

            bb = _safe_bbox(child, renderer)
            if bb is None:
                continue

            if isinstance(child, PathCollection):
                infos.append(_ArtistInfo(
                    child, bb,
                    _artist_label(child, "scatter"),
                    "collection", aid))
            elif isinstance(child, (PolyCollection, LineCollection)):
                infos.append(_ArtistInfo(
                    child, bb,
                    _artist_label(child, "poly"),
                    "collection", aid))
            elif isinstance(child, Patch):
                infos.append(_ArtistInfo(
                    child, bb,
                    _artist_label(child, "patch"),
                    "patch", aid))
            elif isinstance(child, Line2D):
                infos.append(_ArtistInfo(
                    child, bb,
                    _artist_label(child, "line"),
                    "line", aid))
            elif isinstance(child, AxesImage):
                infos.append(_ArtistInfo(
                    child, bb,
                    _artist_label(child, "image"),
                    "image", aid))

    # ── Figure-level text (suptitle and fig.text) ────────────────────────
    _fig_suptitle_obj = getattr(fig, "_suptitle", None)
    for txt in getattr(fig, "texts", []) or []:
        if not getattr(txt, "get_visible", lambda: True)():
            continue
        if not txt.get_text().strip():
            continue
        bb = _safe_bbox(txt, renderer)
        if bb:
            tag = "suptitle" if (txt is _fig_suptitle_obj) else "fig_text"
            infos.append(_ArtistInfo(
                txt, bb, _artist_label(txt, tag), "text", None))
    # Only add fig._suptitle if it wasn't already in fig.texts
    if (_fig_suptitle_obj is not None
            and _fig_suptitle_obj.get_text().strip()
            and _fig_suptitle_obj not in getattr(fig, "texts", [])):
        if getattr(_fig_suptitle_obj, "get_visible", lambda: True)():
            bb = _safe_bbox(_fig_suptitle_obj, renderer)
            if bb:
                infos.append(_ArtistInfo(
                    _fig_suptitle_obj, bb,
                    _artist_label(_fig_suptitle_obj, "suptitle"),
                    "text", None))

    # ── Figure-level legends (fig.legend / shared legends) ─────────────────
    fig_legends = list(getattr(fig, "legends", []) or [])
    for child in fig.get_children():
        if hasattr(child, "get_texts") and hasattr(child, "_legend_box") and id(child) not in seen_legend_ids:
            fig_legends.append(child)

    for legend in fig_legends:
        if id(legend) in seen_legend_ids:
            continue
        if not getattr(legend, "get_visible", lambda: True)():
            continue
        seen_legend_ids.add(id(legend))
        bb = _safe_bbox(legend, renderer)
        if bb:
            infos.append(_ArtistInfo(
                legend, bb, "fig_legend_box", "legend", None))
        for txt in legend.get_texts():
            if txt.get_text().strip():
                tbb = _safe_bbox(txt, renderer)
                if tbb:
                    infos.append(_ArtistInfo(
                        txt, tbb,
                        _artist_label(txt, "fig_legend_text"),
                        "text", None))

    return infos
