"""VCD structural detection passes (16) + per-axes summary.

Passes 19-22 have been moved to ``vcd_checks_layout.py`` for modular
file-size management.  This module retains:
  Pass 16: Significance bracket annotation issues.
  Per-axes summary helper (Layer 1).

Backward-compatible re-exports are provided so existing imports from
``vcd_checks_structure`` continue to work.
"""

from __future__ import annotations

import re
from matplotlib.text import Text

from .vcd_core import _ArtistInfo, _safe_bbox, _shrink, _fig_bbox, _overlap_area, _sides_outside

# Re-export moved functions for backward compatibility
from .vcd_checks_layout import (  # noqa: F401
    _check_fontsize_adequacy,
    _check_tick_spine_overlap,
    _check_font_policy,
    _check_label_density,
)


# ===============================================================================
# Pass 16: Significance bracket annotation issues
# ===============================================================================

def _check_significance_brackets(fig, renderer, border_tol_px=5.0):
    """Pass 16: Detect significance bracket annotation issues.

    Checks:
      a) Bracket star/ns text truncated at figure border.
      b) Bracket star text overlapping other text labels.
      c) Bracket lines (drawn with clip_on=False) extending
         beyond figure bounds.

    Significance brackets are drawn by ``significance_brackets.py``
    using ``clip_on=False``, ``zorder=10-11``, fontweight=bold, and
    text content matching ``*``, ``**``, ``***``, or ``ns``.
    """
    issues: list[dict] = []
    fig_bb = _fig_bbox(fig)
    star_pattern = re.compile(r'^(\*{1,3}|ns)$')

    # Collect all significance annotation texts and bracket lines
    star_texts = []
    bracket_lines = []

    for ax in fig.get_axes():
        for child in ax.get_children():
            if hasattr(child, 'get_text'):
                txt = child.get_text().strip()
                if star_pattern.match(txt) and child.get_visible():
                    bb = _safe_bbox(child, renderer)
                    if bb:
                        star_texts.append((txt, bb, child))

            # Lines with zorder >= 10 and clip_on=False are likely brackets
            if hasattr(child, 'get_xdata') and hasattr(child, 'get_zorder'):
                if child.get_zorder() >= 10 and not child.get_clip_on():
                    bb = _safe_bbox(child, renderer)
                    if bb:
                        bracket_lines.append(("bracket_line", bb, child))

    # a) Check star texts for truncation at figure border
    for txt, bb, artist in star_texts:
        sides = _sides_outside(bb, fig_bb, border_tol_px)
        if sides:
            issues.append({
                "type": "bracket_text_truncation",
                "severity": "warning",
                "detail": (
                    f"Significance text '{txt}' extends beyond "
                    f"figure border ({', '.join(sides)})"
                ),
                "elements": [f"sig_text:{txt}"],
            })

    # b) Check star texts overlapping other (non-bracket) texts
    all_texts = []
    for ax in fig.get_axes():
        for child in ax.get_children():
            if hasattr(child, 'get_text') and child.get_visible():
                other_txt = child.get_text().strip()
                if other_txt and not star_pattern.match(other_txt):
                    bb = _safe_bbox(child, renderer)
                    if bb:
                        all_texts.append((other_txt[:25], bb))

    for sig_txt, sig_bb, _ in star_texts:
        for other_txt, other_bb in all_texts:
            shrunk_sig = _shrink(sig_bb, 1.0)
            shrunk_other = _shrink(other_bb, 1.0)
            if shrunk_sig and shrunk_other and shrunk_sig.overlaps(shrunk_other):
                area = _overlap_area(sig_bb, other_bb)
                if area > 10:
                    issues.append({
                        "type": "bracket_text_overlap",
                        "severity": "warning",
                        "detail": (
                            f"Significance '{sig_txt}' overlaps "
                            f"label '{other_txt}' ({area:.0f} px\u00b2)"
                        ),
                        "elements": [f"sig_text:{sig_txt}",
                                     f"label:{other_txt}"],
                    })

    # c) Check bracket lines for figure-border truncation
    for tag, bb, artist in bracket_lines:
        sides = _sides_outside(bb, fig_bb, border_tol_px)
        if sides:
            issues.append({
                "type": "bracket_line_truncation",
                "severity": "warning",
                "detail": (
                    f"Bracket line extends beyond "
                    f"figure border ({', '.join(sides)})"
                ),
                "elements": [tag],
            })

    return issues


# ===============================================================================
# Per-axes summary helper
# ===============================================================================

def _per_axes_summary(fig, renderer, infos):
    """Per-subplot conflict summary (Layer 1).

    Returns a dict mapping axes title -> list of issues in that subplot,
    useful for pinpointing which panels still have internal conflicts.
    """
    per_ax: dict[str, list[dict]] = {}

    for ax in fig.get_axes():
        if getattr(ax, '_is_legend_cell', False):
            continue
        title = ax.get_title() or f"ax@{id(ax):#x}"
        aid = id(ax)
        ax_issues: list[dict] = []

        legend = ax.get_legend()
        if legend is None or not legend.get_visible():
            per_ax[title] = ax_issues
            continue

        leg_bb = _safe_bbox(legend, renderer)
        if leg_bb is None:
            per_ax[title] = ax_issues
            continue

        local_data = [a for a in infos
                      if a.ax_id == aid
                      and a.kind in ("collection", "line", "image", "patch")
                      and not any(s in a.tag for s in ("Spine", "Wedge", "FancyBbox"))]

        for da in local_data:
            area = _overlap_area(leg_bb, da.bbox)
            if area > 30:
                frac = area / (da.bbox.width * da.bbox.height + 1e-8)
                if frac > 0.03:
                    # Lines span the full axes; legend overlap is expected.
                    # Rectangle (bar) patches in grouped bar charts also
                    # extend across the full axes, so legend overlap is
                    # unavoidable -- downgrade to info like lines.
                    # FillBetween polys span the full axes like lines.
                    if (da.kind == "line" or da.kind == "patch"
                            or "Rectangle" in da.tag
                            or "FillBetween" in da.tag):
                        sev = "info"
                    else:
                        sev = "warning"
                    ax_issues.append({
                        "type": "subplot_legend_overlap",
                        "severity": sev,
                        "detail": (
                            f"[{title}] Legend occludes '{da.tag}' "
                            f"({frac:.0%}, {area:.0f} px\u00b2)"
                        ),
                    })
        per_ax[title] = ax_issues
    return per_ax
