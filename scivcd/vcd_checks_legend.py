"""VCD legend-related detection passes (10-13, 15, 18)."""
from __future__ import annotations

from matplotlib.transforms import Bbox

from .vcd_core import _ArtistInfo, _safe_bbox, _shrink, _fig_bbox, _overlap_area, _sides_outside


def _iter_legends(fig, renderer):
    """Yield (legend, bbox, owner_id, is_dedicated) for visible legends.

    *is_dedicated* is True when the legend lives on a dedicated helper
    axes (marked ``_is_legend_cell``) rather than a data-plotting axes.
    """
    seen_ids: set[int] = set()
    for ax in fig.get_axes():
        legend = ax.get_legend()
        if legend is None or not legend.get_visible():
            continue
        leg_bb = _safe_bbox(legend, renderer)
        if leg_bb is None:
            continue
        seen_ids.add(id(legend))
        is_dedicated = bool(getattr(ax, '_is_legend_cell', False))
        owner_id = id(fig) if is_dedicated else id(ax)
        yield legend, leg_bb, owner_id, is_dedicated

    for legend in getattr(fig, "legends", []) or []:
        if id(legend) in seen_ids or not legend.get_visible():
            continue
        leg_bb = _safe_bbox(legend, renderer)
        if leg_bb is None:
            continue
        seen_ids.add(id(legend))
        yield legend, leg_bb, id(fig), False

    for child in fig.get_children():
        if hasattr(child, 'get_texts') and hasattr(child, '_legend_box') and id(child) not in seen_ids:
            if not getattr(child, "get_visible", lambda: True)():
                continue
            leg_bb = _safe_bbox(child, renderer)
            if leg_bb is None:
                continue
            seen_ids.add(id(child))
            yield child, leg_bb, id(fig), False


def _check_legend_spillover(fig, renderer, tol_px=5.0, tight_bb=None):
    """Pass 10: Legends extending beyond their parent axes or the figure.
    """
    issues = []
    fig_bb = _fig_bbox(fig)

    for ax in fig.get_axes():
        legend = ax.get_legend()
        if legend is None or not legend.get_visible():
            continue
        leg_bb = _safe_bbox(legend, renderer)
        if leg_bb is None:
            continue

        # Check legend vs figure bounds
        sides = _sides_outside(leg_bb, fig_bb, tol_px)
        if sides:
            issues.append({
                "type": "legend_truncation",
                "severity": "warning",
                "detail": (
                    f"Legend in axes extends beyond figure "
                    f"({', '.join(sides)})"
                ),
                "elements": ["legend"],
            })

        # Check legend vs other axes
        for other_ax in fig.get_axes():
            if other_ax is ax:
                continue
            other_bb = _safe_bbox(other_ax, renderer)
            if other_bb is None:
                continue
            area = _overlap_area(leg_bb, other_bb)
            if area > 100:
                issues.append({
                    "type": "legend_spillover",
                    "severity": "warning",
                    "detail": (
                        f"Legend from axes spills into a "
                        f"neighbouring axes ({area:.0f} px\u00b2)"
                    ),
                    "elements": ["legend"],
                })

    # Also check figure-level legends
    for child in fig.get_children():
        if hasattr(child, 'get_texts') and hasattr(child, '_legend_box'):
            leg_bb = _safe_bbox(child, renderer)
            if leg_bb is None:
                continue
            sides = _sides_outside(leg_bb, fig_bb, tol_px)
            if sides:
                issues.append({
                    "type": "legend_truncation",
                    "severity": "warning",
                    "detail": f"Figure legend extends beyond border ({', '.join(sides)})",
                    "elements": ["fig_legend"],
                })

    return issues


def _check_legend_vs_other_panel_content(fig, renderer, infos, min_overlap_px2=30.0):
    """Pass 11: Detect legends overlapping data content in OTHER panels.

    Panel A's legend could spill out of its axes and land on top of Panel B's
    bar chart.  Also checks figure-level legends against all subplot content.
    """
    issues: list[dict] = []

    legend_infos: list[tuple[Bbox, int]] = []
    for ax in fig.get_axes():
        legend = ax.get_legend()
        if legend is None or not legend.get_visible():
            continue
        leg_bb = _safe_bbox(legend, renderer)
        if leg_bb:
            owner_id = id(fig) if getattr(ax, '_is_legend_cell', False) else id(ax)
            legend_infos.append((leg_bb, owner_id))

    # Also include figure-level legends
    for child in fig.get_children():
        if hasattr(child, 'get_texts') and hasattr(child, '_legend_box'):
            leg_bb = _safe_bbox(child, renderer)
            if leg_bb:
                legend_infos.append((leg_bb, id(fig)))

    data_artists_full = [a for a in infos
                         if a.kind in ("collection", "line", "image", "patch")]
    data_artists_no_patch = [a for a in infos
                             if a.kind in ("collection", "line", "image")]

    for leg_bb, leg_owner_id in legend_infos:
        # Figure-level legends: skip patches (axis backgrounds/spines)
        targets = data_artists_no_patch if leg_owner_id == id(fig) \
                  else data_artists_full
        for da in targets:
            if da.ax_id == leg_owner_id:
                continue  # same panel — handled by pass 12
            area = _overlap_area(leg_bb, da.bbox)
            if area > min_overlap_px2:
                # Lines span the full axes; overlap is expected.
                sev = "info" if da.kind == "line" else "warning"
                issues.append({
                    "type": "legend_panel_overlap",
                    "severity": sev,
                    "detail": (
                        f"Legend overlaps '{da.tag}' in a different "
                        f"panel ({area:.0f} px\u00b2)"
                    ),
                    "elements": ["legend", da.tag],
                })
    return issues


def _check_legend_vs_own_content(fig, renderer, infos, min_overlap_px2=200.0):
    """Pass 12: Detect legends covering data IN THEIR OWN panel.

    Checks every legend bbox against ALL data artists (including patches/bars)
    in the same axes.  Only reports when the legend covers >5% of the artist.
    """
    issues: list[dict] = []

    for ax in fig.get_axes():
        legend = ax.get_legend()
        if legend is None or not legend.get_visible():
            continue
        # Skip axes that are purely legend-holding cells
        if getattr(ax, '_is_legend_cell', False):
            continue
        leg_bb = _safe_bbox(legend, renderer)
        if leg_bb is None:
            continue

        aid = id(ax)
        _SKIP = ("Spine", "Wedge", "FancyBbox")
        local_data = [a for a in infos
                      if a.ax_id == aid
                      and a.kind in ("collection", "line", "image", "patch")
                      and not any(s in a.tag for s in _SKIP)]

        for da in local_data:
            area = _overlap_area(leg_bb, da.bbox)
            if area > min_overlap_px2:
                frac = area / (da.bbox.width * da.bbox.height + 1e-8)
                if frac > 0.05:  # legend covers >5% of the data artist
                    # Lines span the full axes; any legend placement
                    # will overlap them — accepted scientific practice.
                    # Rectangle (bar) patches in grouped bar charts also
                    # necessarily overlap with legends — downgrade to info.
                    # FillBetween polys span the full axes like lines;
                    # legend overlap is unavoidable — downgrade to info.
                    if (da.kind == "line" or da.kind == "patch"
                            or "Rectangle" in da.tag
                            or "FillBetween" in da.tag):
                        sev = "info"
                    else:
                        sev = "warning"
                    issues.append({
                        "type": "legend_data_occlusion",
                        "severity": sev,
                        "detail": (
                            f"Legend in same panel occludes "
                            f"'{da.tag}' ({frac:.0%}, {area:.0f} px\u00b2)"
                        ),
                        "elements": ["legend", da.tag],
                    })
    return issues


def _check_fig_legend_vs_subplot_content(fig, renderer, infos,
                                          min_overlap_px2=30.0):
    """Pass 13: Figure-level legends overlapping subplot scatter/bar data.

    Shared legends (e.g. UMAP legend placed via fig.legend()) can overlap
    the scatter/bar content of individual subplots.
    """
    issues: list[dict] = []

    fig_legends = []
    for child in fig.get_children():
        if hasattr(child, 'get_texts') and hasattr(child, '_legend_box'):
            leg_bb = _safe_bbox(child, renderer)
            if leg_bb:
                fig_legends.append(leg_bb)

    if not fig_legends:
        return issues

    _SKIP = ("Spine", "Wedge", "FancyBbox")
    data_artists = [a for a in infos
                    if a.kind in ("collection", "line", "image", "patch")
                    and not any(s in a.tag for s in _SKIP)]

    for leg_bb in fig_legends:
        for da in data_artists:
            area = _overlap_area(leg_bb, da.bbox)
            if area > min_overlap_px2:
                frac = area / (da.bbox.width * da.bbox.height + 1e-8)
                if frac > 0.03:  # 3% — very sensitive for shared legends
                    # Lines and PolyCollections span the full axes;
                    # overlap with a figure-level legend is expected.
                    sev = ("info"
                           if da.kind == "line" or "Poly" in da.tag
                           else "warning")
                    issues.append({
                        "type": "fig_legend_subplot_occlusion",
                        "severity": sev,
                        "detail": (
                            f"Figure-level legend occludes subplot "
                            f"content '{da.tag}' ({frac:.0%}, {area:.0f} px\u00b2)"
                        ),
                        "elements": ["fig_legend", da.tag],
                    })
    return issues


def _check_legend_internal(fig, renderer, tol_px=1.0, tight_bb=None):
    """Pass 15: Detect internal crowding within legend boxes.

    Checks:
      a) Legend text entries overlapping each other.
      b) Legend texts extending beyond the legend frame bbox.
      c) Legend texts extending beyond figure bounds.
    """
    issues: list[dict] = []
    fig_bb = _fig_bbox(fig)

    def _audit_legend(legend, ctx_label="axes"):
        if legend is None or not legend.get_visible():
            return
        leg_bb = _safe_bbox(legend, renderer)
        if leg_bb is None:
            return

        texts = legend.get_texts()
        text_bbs: list[tuple[str, Bbox]] = []
        for t in texts:
            txt = t.get_text().strip()
            if not txt:
                continue
            bb = _safe_bbox(t, renderer)
            if bb:
                text_bbs.append((txt[:30], bb))

        # a) Pairwise text overlap within legend
        for i in range(len(text_bbs)):
            for j in range(i + 1, len(text_bbs)):
                txt_i, bb_i = text_bbs[i]
                txt_j, bb_j = text_bbs[j]
                si = _shrink(bb_i, tol_px)
                sj = _shrink(bb_j, tol_px)
                if si and sj and si.overlaps(sj):
                    area = _overlap_area(bb_i, bb_j)
                    issues.append({
                        "type": "legend_text_crowding",
                        "severity": "warning",
                        "detail": (
                            f"Legend entries '{txt_i}' and '{txt_j}' "
                            f"overlap in {ctx_label} ({area:.0f} px\u00b2)"
                        ),
                        "elements": [f"legend_text:{txt_i}",
                                     f"legend_text:{txt_j}"],
                    })

        # b) Texts extending beyond legend frame
        for txt_t, bb_t in text_bbs:
            sides = _sides_outside(bb_t, leg_bb, 2.0)
            if sides:
                issues.append({
                    "type": "legend_text_overflow",
                    "severity": "info",
                    "detail": (
                        f"Legend text '{txt_t}' extends beyond "
                        f"legend frame in {ctx_label} "
                        f"({', '.join(sides)})"
                    ),
                    "elements": [f"legend_text:{txt_t}"],
                })

        # c) Texts extending beyond figure bounds
        for txt_t, bb_t in text_bbs:
            sides = _sides_outside(bb_t, fig_bb, 1.0)
            if sides:
                issues.append({
                    "type": "legend_text_truncation",
                    "severity": "warning",
                    "detail": (
                        f"Legend text '{txt_t}' extends beyond "
                        f"figure border ({', '.join(sides)})"
                    ),
                    "elements": [f"legend_text:{txt_t}"],
                })

    # Check per-axes legends
    for idx, ax in enumerate(fig.get_axes()):
        _audit_legend(ax.get_legend(), f"axes[{idx}]")

    # Check figure-level legends
    for child in fig.get_children():
        if hasattr(child, 'get_texts') and hasattr(child, '_legend_box'):
            _audit_legend(child, "figure-legend")

    return issues


def _check_legend_crowding_autofix(fig, renderer, auto_fix=True):
    """Pass 18: Detect and optionally auto-fix legend crowding.

    For each axes legend:
      1. Check if legend entries overlap each other.
      2. If auto_fix and overlap detected, try ``loc='best'`` relocation.
      3. If legend has >6 entries and font > 8pt, shrink by 1pt.

    Returns list of issue dicts.
    """
    issues: list[dict] = []

    for idx, ax in enumerate(fig.get_axes()):
        legend = ax.get_legend()
        if legend is None or not legend.get_visible():
            continue

        leg_bb = _safe_bbox(legend, renderer)
        if leg_bb is None:
            continue

        texts = legend.get_texts()
        if not texts:
            continue

        text_bbs = []
        for t in texts:
            txt = t.get_text().strip()
            bb = _safe_bbox(t, renderer)
            if bb and txt:
                text_bbs.append((txt[:25], bb))

        has_crowding = False
        for i in range(len(text_bbs)):
            for j in range(i + 1, len(text_bbs)):
                _, bb_i = text_bbs[i]
                _, bb_j = text_bbs[j]
                si = _shrink(bb_i, 0.5)
                sj = _shrink(bb_j, 0.5)
                if si and sj and si.overlaps(sj):
                    has_crowding = True
                    break
            if has_crowding:
                break

        fixed = False
        if has_crowding and auto_fix:
            if len(texts) > 6:
                for t in texts:
                    current_fs = t.get_fontsize()
                    if current_fs > 8:
                        t.set_fontsize(current_fs - 1)
                        fixed = True
            try:
                legend._loc = 0  # 0 = 'best' in matplotlib
                fig.canvas.draw()
                fixed = True
            except Exception:
                pass

        if has_crowding:
            issues.append({
                "type": "legend_crowding_autofix",
                "severity": "info" if fixed else "warning",
                "detail": (
                    f"Legend in axes[{idx}] has crowded entries"
                    + (" \u2014 auto-fixed (font shrink / relocation)" if fixed
                       else " \u2014 auto-fix not possible")
                ),
                "elements": [f"legend_axes_{idx}"],
            })

    return issues


def _check_legend_vs_legend(fig, renderer, min_overlap_px2=60.0):
    """Detect overlapping legend boxes anywhere in the figure."""
    issues: list[dict] = []
    legends = list(_iter_legends(fig, renderer))
    for i in range(len(legends)):
        leg_i, bb_i, owner_i, _ = legends[i]
        for j in range(i + 1, len(legends)):
            leg_j, bb_j, owner_j, _ = legends[j]
            if owner_i == owner_j:
                continue
            area = _overlap_area(bb_i, bb_j)
            if area > min_overlap_px2:
                issues.append({
                    "type": "legend_legend_overlap",
                    "severity": "warning",
                    "detail": f"Legend boxes overlap ({area:.0f} px²)",
                    "elements": ["legend_box", "legend_box"],
                })
    return issues


def _check_legend_vs_other_artists(fig, renderer, infos, min_overlap_px2=60.0):
    """Detect legend boxes masking text or non-background artists anywhere in the figure."""
    issues: list[dict] = []
    legends = list(_iter_legends(fig, renderer))
    if not legends:
        return issues

    for legend, leg_bb, owner_id, is_dedicated in legends:
        own_text_ids = {id(txt) for txt in legend.get_texts()}
        for info in infos:
            if info.artist is legend or id(info.artist) in own_text_ids:
                continue
            if info.kind == "legend" and info.artist is not legend:
                area = _overlap_area(leg_bb, info.bbox)
                if area > min_overlap_px2:
                    issues.append({
                        "type": "legend_artist_masking",
                        "severity": "warning",
                        "detail": f"Legend masks '{info.tag}' ({area:.0f} px²)",
                        "elements": ["legend_box", info.tag],
                    })
                continue

            if info.kind == "patch" and any(skip in info.tag for skip in ("Spine", "FancyBbox", "_ColorbarSpine")):
                continue

            area = _overlap_area(leg_bb, info.bbox)
            if area <= min_overlap_px2:
                continue

            target_area = max(info.bbox.width * info.bbox.height, 1.0)
            frac = area / target_area
            same_owner = owner_id == info.ax_id and info.ax_id is not None

            # Dedicated legend axes (shared legends created by
            # add_shared_legend_axes) are deliberately positioned near
            # the axis labels / ticks of a neighbouring data axes.
            # Overlap with those elements is an intentional layout
            # choice, not a design error — use a generous threshold.
            is_adjacent_label = (
                is_dedicated
                and info.kind == "text"
                and any(k in info.tag for k in ("xlabel", "ylabel", "xtick", "ytick"))
            )

            if is_adjacent_label and frac < 0.80:
                severity = "info"
            elif same_owner and info.kind == "line" and frac < 0.30:
                severity = "info"
            elif same_owner and info.kind == "collection" and frac < 0.15:
                severity = "info"
            elif same_owner and info.kind == "patch" and frac < 0.20:
                severity = "info"
            elif same_owner and info.kind == "text" and frac < 0.20:
                severity = "info"
            else:
                severity = "warning"

            issues.append({
                "type": "legend_artist_masking",
                "severity": severity,
                "detail": (
                    f"Legend masks '{info.tag}' "
                    f"({frac:.0%}, {area:.0f} px²)"
                ),
                "elements": ["legend_box", info.tag],
            })
    return issues
