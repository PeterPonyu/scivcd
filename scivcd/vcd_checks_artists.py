"""VCD artist-related detection passes (2-4, 6-7)."""
from __future__ import annotations

import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.transforms import Bbox

from .vcd_core import _ArtistInfo, _safe_bbox, _shrink, _fig_bbox, _overlap_area, _sides_outside, _artist_label


def _check_truncation(infos: list[_ArtistInfo], fig_bb: Bbox, tol_px: float = 3.0, fig=None, renderer=None, tight_bb=None):
    """Pass 2–3: Check if any artist extends beyond figure canvas.

    VCD now evaluates truncation strictly against the authored figure canvas.
    Small single-pixel grazes near the tolerance boundary are downgraded to
    ``info`` to avoid noise, but there is no longer any severity downgrade
    based on auto-cropping or tight-bbox export behaviour.
    """
    # Build set of polar axes IDs to skip their patches in truncation checks
    _polar_ax_ids = set()
    if fig is not None:
        try:
            for _ax in fig.get_axes():
                if getattr(_ax, 'name', None) == 'polar':
                    _polar_ax_ids.add(id(_ax))
        except Exception:
            pass

    issues = []
    for a in infos:
        # Skip polar axes patches — circular geometry always exceeds the
        # rectangular figure bounds.
        if a.kind == "patch" and a.ax_id in _polar_ax_ids:
            continue
        sides = _sides_outside(a.bbox, fig_bb, tol_px)
        if sides:
            # Measure maximum overshoot
            overshoot = max(
                max(0, fig_bb.x0 - a.bbox.x0),
                max(0, fig_bb.y0 - a.bbox.y0),
                max(0, a.bbox.x1 - fig_bb.x1),
                max(0, a.bbox.y1 - fig_bb.y1),
            )
            # Skip extreme overshoots from polar/special-geometry axes
            # (e.g., radar plot wedge patches)
            if overshoot > 10000:
                continue
            # Tick labels and axis spines near figure borders produce
            # small pixel overshoots that are invisible in the final
            # exported PDF.  Use a more generous info threshold for
            # these elements to reduce false-positive warnings.
            is_border_element = any(
                k in a.tag for k in ("xtick", "ytick", "Spine")
            )
            info_threshold = tol_px + 10 if is_border_element else tol_px + 4
            if overshoot < info_threshold:
                sev = "info"
            elif a.kind == "text":
                sev = "warning"
            elif a.kind in ("collection", "patch", "line", "legend"):
                sev = "warning"
            else:
                sev = "info"
            is_fig_level = a.tag.startswith(("suptitle", "fig_text"))
            issues.append({
                "type": f"{a.kind}_truncation",
                "severity": sev,
                "detail": (f"'{a.tag}' extends beyond figure border "
                           f"({', '.join(sides)}, {overshoot:.0f}px)"),
                "elements": [a.tag],
                "is_fig_level": is_fig_level,
            })
    return issues


def _check_artist_content_overlap(
    infos: list[_ArtistInfo],
    min_overlap_px2: float = 200.0,
):
    """Pass 4: Check significant overlap between non-text graphical artists.

    Skips same-axes overlaps entirely — those are intentional layering
    (legend on bars, scatter layers, colorbar on image, etc.).
    Also skips Spine artists — cross-axes spine/patch overlaps are
    harmless background geometry.
    """
    graphical = [a for a in infos
                 if a.kind in ("collection", "patch", "image")
                 and "Spine" not in a.tag]
    issues = []
    for i in range(len(graphical)):
        for j in range(i + 1, len(graphical)):
            a, b = graphical[i], graphical[j]
            # Same axes = intentional layering — skip entirely
            if a.ax_id == b.ax_id:
                continue
            # Cross-axes patch-vs-patch (e.g. bar Rectangles in adjacent
            # panels) naturally share boundary pixels — not a real conflict.
            if a.kind == "patch" and b.kind == "patch":
                continue
            area = _overlap_area(a.bbox, b.bbox)
            if area > min_overlap_px2:
                issues.append({
                    "type": "artist_overlap",
                    "severity": "warning",
                    "detail": (f"'{a.tag}' overlaps '{b.tag}' "
                               f"({area:.0f} px\u00b2)"),
                    "elements": [a.tag, b.tag],
                })
    return issues


def _check_axes_overflow(infos: list[_ArtistInfo], fig):
    """Pass 6: Check if artist content exceeds its parent axes bounds.

    Only checks meaningful data artists (collections, lines, data patches),
    not axis furniture (spines, background rectangles, etc.).
    """
    from matplotlib.spines import Spine

    renderer = fig.canvas.get_renderer()
    issues = []

    for ax in fig.get_axes():
        ax_bb = _safe_bbox(ax, renderer)
        if not ax_bb:
            continue
        aid = id(ax)
        # Include patch (e.g. bar rectangles) so bars extending past axes are detected
        kinds = ("collection", "line", "patch")
        if getattr(ax, "name", None) == "polar":
            kinds = ("collection", "line")  # skip patch: polar wedges are full-radius by design
        ax_artists = [a for a in infos
                      if a.ax_id == aid
                      and a.kind in kinds]
        for a in ax_artists:
            # Skip Spine objects — they *define* the axes border and always
            # have a bbox that coincides with or extends to axes edges.
            if isinstance(a.artist, Spine):
                continue
            # Skip the axes background patch
            if a.artist is ax.patch:
                continue
            # Skip any patch whose tag indicates it is a Spine
            if "Spine" in a.tag:
                continue
            sides = _sides_outside(a.bbox, ax_bb, tol=3.0)
            if sides:
                issues.append({
                    "type": "axes_overflow",
                    "severity": "info",
                    "detail": (f"'{a.tag}' extends beyond axes border "
                               f"({', '.join(sides)})"),
                    "elements": [a.tag],
                })
    return issues


def _check_scatter_clip_risk(fig) -> list[dict]:
    """Pass 7: Detect scatter markers silently clipped by axes boundaries.

    When ``clip_on=True`` (matplotlib's default), scatter dots that
    extend past the axes clip box are *invisibly* truncated.
    ``get_window_extent()`` returns the *already-clipped* bbox, so the
    standard checks cannot detect the loss.

    This pass reconstructs the **true unclipped extent** of each scatter
    marker by reading raw data offsets, transforming to display coords,
    adding marker radius, and comparing against the axes clip box.
    """
    renderer = fig.canvas.get_renderer()
    issues = []

    for ax in fig.get_axes():
        ax_bb = _safe_bbox(ax, renderer)
        if ax_bb is None:
            continue

        for child in ax.get_children():
            if not isinstance(child, PathCollection):
                continue
            if not child.get_visible():
                continue
            if not child.get_clip_on():
                continue

            offsets = child.get_offsets()
            if offsets is None or len(offsets) == 0:
                continue

            raw_sizes = child.get_sizes()
            if raw_sizes is None or len(raw_sizes) == 0:
                continue
            sizes = np.broadcast_to(np.asarray(raw_sizes),
                                    (len(offsets),))

            transform = child.get_offset_transform()
            if transform is None:
                transform = ax.transData
            try:
                display_pts = transform.transform(offsets)
            except Exception:
                continue

            pts_per_px = 72.0 / fig.dpi
            radii_px = np.sqrt(sizes / np.pi) / pts_per_px

            n_clipped = 0
            clipped_sides: set[str] = set()
            for (dx, dy), r in zip(display_pts, radii_px):
                if dx - r < ax_bb.x0:
                    n_clipped += 1
                    clipped_sides.add("left")
                elif dx + r > ax_bb.x1:
                    n_clipped += 1
                    clipped_sides.add("right")
                if dy - r < ax_bb.y0:
                    n_clipped += 1
                    clipped_sides.add("bottom")
                elif dy + r > ax_bb.y1:
                    n_clipped += 1
                    clipped_sides.add("top")

            if n_clipped > 0:
                label = getattr(child, "_label", "") or ""
                tag = f"scatter({label})" if label and not label.startswith("_") else "scatter"
                issues.append({
                    "type": "scatter_clip_risk",
                    "severity": "warning",
                    "detail": (
                        f"'{tag}' has {n_clipped} marker(s) clipped at "
                        f"axes edge ({', '.join(sorted(clipped_sides))}). "
                        f"Set clip_on=False or add axis margin."
                    ),
                    "elements": [tag],
                })

    return issues
