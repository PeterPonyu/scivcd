"""LAYOUT-category detectors.

Ported from ``experiments/scivcd-lifetime/scripts/vcd/lifecycle/``
(``tier2_geometry.py``, ``tier2_policy.py``, ``tier2_density.py``).
Each detector now returns ``list[Finding]`` directly instead of the
legacy ``(artist, payload)`` tuples. Thresholds come from
``ScivcdConfig`` — defaults are identical to the original hardcoded
values.

The call-site string is intentionally left as ``None``: the runtime
resolves it later by walking ``artist._scivcd_stack`` if present.
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


# ---------------------------------------------------------------------------
# Shared helpers (local copies so this module has zero cross-check imports)
# ---------------------------------------------------------------------------

def _data_axes(fig: Any) -> list:
    out = []
    for ax in fig.get_axes():
        if getattr(ax, "_colorbar", None):
            continue
        out.append(ax)
    return out


def _distance_between_bboxes(a: Any, b: Any) -> float:
    """Minimum display-space distance between two bboxes, 0 if overlapping."""
    try:
        dx = max(float(a.x0) - float(b.x1), float(b.x0) - float(a.x1), 0.0)
        dy = max(float(a.y0) - float(b.y1), float(b.y0) - float(a.y1), 0.0)
    except Exception:
        return float("inf")
    return (dx * dx + dy * dy) ** 0.5


# ---------------------------------------------------------------------------
# excessive_border_whitespace
# ---------------------------------------------------------------------------

def _fire_excessive_border_whitespace(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag canvases where SubplotParams margins waste canvas area."""
    out: list[Finding] = []
    try:
        sp = fig.subplotpars
    except Exception:
        return out

    has_suptitle = False
    try:
        st = getattr(fig, "_suptitle", None)
        has_suptitle = bool(st and (st.get_text() or "").strip())
    except Exception:
        pass

    has_right_colorbar = False
    try:
        for ax in fig.get_axes():
            if getattr(ax, "_colorbar", None):
                pos = ax.get_position()
                if pos.x0 > 0.85:
                    has_right_colorbar = True
                    break
    except Exception:
        pass

    left_max = config.border_left_max  # default 0.18
    right_min = config.border_right_min  # default 0.88 -> right_margin > 0.12
    top_min = config.border_top_min  # default 0.88 -> top_margin > 0.12 (or .14 with suptitle)
    bottom_max = config.border_bottom_max  # default 0.14

    sides: list[str] = []
    if sp.left > left_max:
        sides.append(f"left={sp.left:.2f}")
    right_margin = 1.0 - sp.right
    # Original hard-coded: 0.18 with right colorbar, 0.12 otherwise.
    right_limit = 0.18 if has_right_colorbar else (1.0 - right_min)
    if right_margin > right_limit:
        sides.append(f"right={right_margin:.2f}")
    top_margin = 1.0 - sp.top
    # Original hard-coded: 0.14 with suptitle, 0.10 otherwise.
    top_limit = 0.14 if has_suptitle else max(0.10, 1.0 - top_min - 0.02)
    if top_margin > top_limit:
        sides.append(f"top={top_margin:.2f}")
    if sp.bottom > bottom_max:
        sides.append(f"bottom={sp.bottom:.2f}")

    if not sides:
        return out
    out.append(Finding(
        check_id="excessive_border_whitespace",
        severity=Severity.MEDIUM,
        category=Category.LAYOUT,
        stage=Stage.TIER2,
        message=(
            "canvas border whitespace exceeds publication heuristic on: "
            + ", ".join(sides)
        ),
        call_site=None,
        fix_suggestion=(
            "tighten `plt.subplots_adjust(...)` / `GridSpec(..., left/right/"
            "top/bottom=...)` so the outer axes sit closer to the canvas edge "
            "(target: left <= 0.12, right >= 0.96, top >= 0.94, bottom <= 0.10)"
        ),
        artist=fig,
    ))
    return out


register(CheckSpec(
    id="excessive_border_whitespace",
    severity=Severity.MEDIUM,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_excessive_border_whitespace,
    description="Canvas border whitespace exceeds publication heuristic",
    config_keys=(
        "border_left_max",
        "border_right_min",
        "border_top_min",
        "border_bottom_max",
    ),
))


# ---------------------------------------------------------------------------
# excessive_gutter_whitespace
# ---------------------------------------------------------------------------

def _fire_excessive_gutter_whitespace(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag GridSpecs whose hspace or wspace exceed publication heuristics."""
    out: list[Finding] = []
    hspace_max = config.gutter_hspace_max  # default 0.60
    wspace_max = config.gutter_wspace_max  # default 0.55
    seen_gs: set = set()
    for ax in fig.get_axes():
        try:
            ss = ax.get_subplotspec()
        except Exception:
            continue
        gs = None
        while ss is not None:
            gs = ss.get_gridspec() if hasattr(ss, "get_gridspec") else None
            if gs is None:
                break
            gid = id(gs)
            if gid in seen_gs:
                ss = getattr(gs, "_subplot_spec", None)
                continue
            seen_gs.add(gid)
            hs = float(getattr(gs, "hspace", 0.0) or 0.0)
            ws = float(getattr(gs, "wspace", 0.0) or 0.0)
            offend: list[str] = []
            if hs > hspace_max:
                offend.append(f"hspace={hs:.2f}")
            if ws > wspace_max:
                offend.append(f"wspace={ws:.2f}")
            if offend:
                out.append(Finding(
                    check_id="excessive_gutter_whitespace",
                    severity=Severity.MEDIUM,
                    category=Category.LAYOUT,
                    stage=Stage.TIER2,
                    message=(
                        "GridSpec row/col gutter too wide: "
                        + ", ".join(offend)
                    ),
                    call_site=None,
                    fix_suggestion=(
                        "reduce the GridSpec hspace/wspace (target: <= 0.30 "
                        "for publication-ready density) and compensate by "
                        "bumping inner axes fontsize rather than inflating "
                        "gutters"
                    ),
                    artist=fig,
                ))
            ss = getattr(gs, "_subplot_spec", None)
    return out


register(CheckSpec(
    id="excessive_gutter_whitespace",
    severity=Severity.MEDIUM,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_excessive_gutter_whitespace,
    description="GridSpec hspace/wspace exceed publication heuristic",
    config_keys=("gutter_hspace_max", "gutter_wspace_max"),
))


# ---------------------------------------------------------------------------
# undersized_font_vs_canvas (LAYOUT-category per task contract)
# ---------------------------------------------------------------------------

def _axes_area_inches(ax: Any, fig: Any) -> float:
    try:
        bbox_fig = ax.get_position()
        fig_w, fig_h = fig.get_size_inches()
        return max(bbox_fig.width * fig_w, 0.0) * max(bbox_fig.height * fig_h, 0.0)
    except Exception:
        return 0.0


def _fire_undersized_font_vs_canvas(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag axes where title/xlabel/ylabel fontsize is too small for the
    rendered axes area.
    """
    out: list[Finding] = []
    title_min = config.title_min_pt  # default 11.0
    label_min = config.label_min_pt  # default 10.0
    for ax in _data_axes(fig):
        area = _axes_area_inches(ax, fig)
        if area < 0.5:
            continue
        threshold_title = title_min if area >= 4.0 else label_min
        threshold_label = label_min if area >= 4.0 else (label_min - 1.0)
        for role, artist, limit in (
            ("title", ax.title, threshold_title),
            ("xlabel", ax.xaxis.label, threshold_label),
            ("ylabel", ax.yaxis.label, threshold_label),
        ):
            try:
                txt = (artist.get_text() or "").strip() if artist else ""
                size = float(artist.get_fontsize()) if artist else 0.0
            except Exception:
                continue
            if not txt:
                continue
            if size < limit:
                out.append(Finding(
                    check_id="undersized_font_vs_canvas",
                    severity=Severity.MEDIUM,
                    category=Category.LAYOUT,
                    stage=Stage.TIER2,
                    message=(
                        f"{role} '{txt[:30]}' at {size:.1f}pt on "
                        f"{area:.1f}in^2 axes (target >= {limit:.0f}pt)"
                    ),
                    call_site=None,
                    fix_suggestion=(
                        f"bump {role} fontsize to >= {limit:.0f}pt so the "
                        "text reads cleanly at publication scale"
                    ),
                    artist=artist,
                ))
    return out


register(CheckSpec(
    id="undersized_font_vs_canvas",
    severity=Severity.MEDIUM,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_undersized_font_vs_canvas,
    description="Axes title/xlabel/ylabel fontsize too small for rendered area",
    config_keys=("title_min_pt", "label_min_pt"),
))


# ---------------------------------------------------------------------------
# panel_label_too_far_from_panel
# ---------------------------------------------------------------------------

def _gid(artist: Any) -> str:
    try:
        g = artist.get_gid()
    except Exception:
        return ""
    return g if isinstance(g, str) else ""


def _is_panel_label(artist: Any) -> bool:
    return _gid(artist).startswith("panel_label:")


def _fire_panel_label_too_far_from_panel(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """A panel label must sit close to the top-left of the panel it annotates."""
    out: list[Finding] = []
    try:
        axes = [
            ax for ax in fig.get_axes()
            if not getattr(ax, "_colorbar", None)
        ]
    except Exception:
        return out
    if not axes:
        return out
    ax_boxes: list[tuple[float, float, float, float]] = []
    for ax in axes:
        try:
            pos = ax.get_position()
            ax_boxes.append((pos.x0, pos.x1, pos.y0, pos.y1))
        except Exception:
            continue
    if not ax_boxes:
        return out
    try:
        artists = list(fig.findobj(Text))
    except Exception:
        return out
    margin = config.panel_label_radius  # default 0.08
    for artist in artists:
        if not _is_panel_label(artist):
            continue
        try:
            x, y = artist.get_position()
            x = float(x)
            y = float(y)
        except Exception:
            continue
        dist = min(
            max(x - x1, x0 - x, 0.0) + max(y - y1, y0 - y, 0.0)
            for (x0, x1, y0, y1) in ax_boxes
        )
        if dist > margin:
            text = (artist.get_text() or "").strip()
            out.append(Finding(
                check_id="panel_label_too_far_from_panel",
                severity=Severity.HIGH,
                category=Category.LAYOUT,
                stage=Stage.TIER2,
                message=(
                    f"panel label '{text[:20]}' at ({x:.2f}, {y:.2f}) "
                    f"sits {dist:.3f} fig-fractions from the nearest axes; "
                    f"must be <= {margin:.2f} to read as that panel's label"
                ),
                call_site=None,
                fix_suggestion=(
                    "move the label to the top-left of its anchored axes, "
                    "e.g. fig.text(ax.get_position().x0 - 0.01, "
                    "ax.get_position().y1 + 0.01, 'A', ...)"
                ),
                artist=artist,
            ))
    return out


register(CheckSpec(
    id="panel_label_too_far_from_panel",
    severity=Severity.HIGH,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_panel_label_too_far_from_panel,
    description="Panel label not anchored close to its target axes",
    config_keys=("panel_label_radius",),
))


# ---------------------------------------------------------------------------
# excessive_whitespace_vs_content
# ---------------------------------------------------------------------------

def _fire_excessive_whitespace_vs_content(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag canvases where axes occupy less than the whitespace/content min."""
    out: list[Finding] = []
    floor = config.whitespace_content_min  # default 0.45
    try:
        fig_w, fig_h = fig.get_size_inches()
        canvas = fig_w * fig_h
        if canvas <= 0:
            return out
        axes = [
            ax for ax in fig.get_axes()
            if not getattr(ax, "_colorbar", None)
        ]
        if not axes:
            return out
        total = 0.0
        for ax in axes:
            pos = ax.get_position()
            total += pos.width * pos.height * canvas
        ratio = total / canvas
    except Exception:
        return out
    if ratio >= floor:
        return out
    out.append(Finding(
        check_id="excessive_whitespace_vs_content",
        severity=Severity.MEDIUM,
        category=Category.LAYOUT,
        stage=Stage.TIER2,
        message=(
            f"axes occupy {ratio*100:.1f}% of the canvas "
            f"(target >= {floor*100:.0f}%); layout is whitespace-heavy"
        ),
        call_site=None,
        fix_suggestion=(
            "tighten GridSpec margins + reduce hspace/wspace, or enlarge "
            "inner axes via width/height_ratios to push content above the "
            "whitespace floor"
        ),
        artist=fig,
    ))
    return out


register(CheckSpec(
    id="excessive_whitespace_vs_content",
    severity=Severity.MEDIUM,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_excessive_whitespace_vs_content,
    description="Sum of axes area vs canvas is below publication floor",
    config_keys=("whitespace_content_min",),
))


# ---------------------------------------------------------------------------
# sparse_row_coverage
# ---------------------------------------------------------------------------

def _fire_sparse_row_coverage(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Within each outer-GridSpec row, sum of axes width must be >= 60% of
    the row's x-span.
    """
    out: list[Finding] = []
    rows: dict[tuple[int, int], list] = {}
    for ax in _data_axes(fig):
        try:
            ss = ax.get_subplotspec()
            gs = ss.get_gridspec() if ss is not None else None
            while gs is not None:
                parent = getattr(gs, "_subplot_spec", None)
                if parent is None:
                    break
                gs = parent.get_gridspec()
            if ss is None:
                continue
            row_key = (ss.rowspan.start, ss.rowspan.stop)
            rows.setdefault(row_key, []).append(ax)
        except Exception:
            continue
    if not rows:
        return out
    for row_key, axes_in_row in rows.items():
        try:
            positions = [ax.get_position() for ax in axes_in_row]
            if not positions:
                continue
            width_sum = sum(p.width for p in positions)
            x_min = min(p.x0 for p in positions)
            x_max = max(p.x1 for p in positions)
            row_span = x_max - x_min
            if row_span <= 0:
                continue
            coverage = width_sum / row_span
        except Exception:
            continue
        if coverage >= 0.60:
            continue
        out.append(Finding(
            check_id="sparse_row_coverage",
            severity=Severity.MEDIUM,
            category=Category.LAYOUT,
            stage=Stage.TIER2,
            message=(
                f"row {row_key} has {len(axes_in_row)} axes covering "
                f"{coverage*100:.0f}% of its x-span (target >= 60%); row is "
                "content-sparse with wide gutters"
            ),
            call_site=None,
            fix_suggestion=(
                "reduce wspace on this row's inner GridSpec, increase "
                "width_ratios for data axes, or stretch the row to fill "
                "more of the canvas horizontally"
            ),
            artist=axes_in_row[0],
        ))
    return out


register(CheckSpec(
    id="sparse_row_coverage",
    severity=Severity.MEDIUM,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_sparse_row_coverage,
    description="Row axes cover too little of the row's x-span",
))


# ---------------------------------------------------------------------------
# suptitle_too_far_from_axes
# ---------------------------------------------------------------------------

def _fire_suptitle_too_far_from_axes(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag figure titles that float far above the top row of panels."""
    out: list[Finding] = []
    st = getattr(fig, "_suptitle", None)
    if st is None:
        return out
    try:
        if not (st.get_text() or "").strip():
            return out
        axes = _data_axes(fig)
        if not axes:
            return out
        top_axes = max(ax.get_position().y1 for ax in axes)
        _x, title_y = st.get_position()
        gap = float(title_y) - float(top_axes)
    except Exception:
        return out
    if gap <= config.title_axes_gap_max:
        return out
    out.append(Finding(
        check_id="suptitle_too_far_from_axes",
        severity=Severity.MEDIUM,
        category=Category.LAYOUT,
        stage=Stage.TIER2,
        message=(
            f"figure title sits {gap:.3f} figure-fractions above the top axes "
            f"(target <= {config.title_axes_gap_max:.3f})"
        ),
        call_site=None,
        fix_suggestion=(
            "lower the suptitle or reduce tight_layout/constrained-layout top "
            "reservation so the title belongs visually to the panel grid"
        ),
        artist=st,
    ))
    return out


register(CheckSpec(
    id="suptitle_too_far_from_axes",
    severity=Severity.MEDIUM,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_suptitle_too_far_from_axes,
    description="Figure title is too far from the top panel row",
    config_keys=("title_axes_gap_max",),
))


# ---------------------------------------------------------------------------
# panel_row_misalignment
# ---------------------------------------------------------------------------

def _fire_panel_row_misalignment(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag rows whose axes are not horizontally aligned."""
    out: list[Finding] = []
    axes = _data_axes(fig)
    if len(axes) < 3:
        return out
    rows: list[list[Any]] = []
    for ax in sorted(axes, key=lambda a: -a.get_position().y0):
        pos = ax.get_position()
        ymid = 0.5 * (pos.y0 + pos.y1)
        for row in rows:
            rpos = row[0].get_position()
            rmid = 0.5 * (rpos.y0 + rpos.y1)
            if abs(ymid - rmid) <= 0.08:
                row.append(ax)
                break
        else:
            rows.append([ax])
    for row in rows:
        if len(row) < 2:
            continue
        tops = [a.get_position().y1 for a in row]
        bottoms = [a.get_position().y0 for a in row]
        spread = max(max(tops) - min(tops), max(bottoms) - min(bottoms))
        if spread <= config.row_alignment_tol:
            continue
        out.append(Finding(
            check_id="panel_row_misalignment",
            severity=Severity.MEDIUM,
            category=Category.LAYOUT,
            stage=Stage.TIER2,
            message=(
                f"row with {len(row)} panels has vertical-edge spread {spread:.3f} "
                f"(target <= {config.row_alignment_tol:.3f})"
            ),
            call_site=None,
            fix_suggestion=(
                "align axes in the row to a shared top/bottom rectangle or use a "
                "common GridSpec row instead of independent manual positions"
            ),
            artist=row[0],
        ))
    return out


register(CheckSpec(
    id="panel_row_misalignment",
    severity=Severity.MEDIUM,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_panel_row_misalignment,
    description="Panels in the same row are not horizontally aligned",
    config_keys=("row_alignment_tol",),
))


# ---------------------------------------------------------------------------
# legend_tick_clearance
# ---------------------------------------------------------------------------

def _fire_legend_tick_clearance(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag legends placed too close to tick labels."""
    out: list[Finding] = []
    try:
        renderer = fig.canvas.get_renderer()
    except Exception:
        return out
    tick_labels = []
    for ax in fig.get_axes():
        for lbl in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
            try:
                if lbl.get_visible() and (lbl.get_text() or "").strip():
                    tick_labels.append(lbl.get_window_extent(renderer))
            except Exception:
                continue
    if not tick_labels:
        return out
    for ax in fig.get_axes():
        leg = ax.get_legend()
        if leg is None:
            continue
        try:
            bb = leg.get_window_extent(renderer)
        except Exception:
            continue
        nearest = min(_distance_between_bboxes(bb, tb) for tb in tick_labels)
        if nearest >= config.legend_tick_clearance_px:
            continue
        out.append(Finding(
            check_id="legend_tick_clearance",
            severity=Severity.MEDIUM,
            category=Category.LAYOUT,
            stage=Stage.TIER2,
            message=(
                f"legend is {nearest:.1f}px from a tick label "
                f"(target >= {config.legend_tick_clearance_px:.1f}px)"
            ),
            call_site=None,
            fix_suggestion=(
                "move the legend farther from tick labels, add bottom/top padding, "
                "or use a dedicated legend axes"
            ),
            artist=leg,
        ))
    return out


register(CheckSpec(
    id="legend_tick_clearance",
    severity=Severity.MEDIUM,
    category=Category.LAYOUT,
    stage=Stage.TIER2,
    fire=_fire_legend_tick_clearance,
    description="Legend is too close to tick labels",
    config_keys=("legend_tick_clearance_px",),
))


__all__ = [
    "_fire_excessive_border_whitespace",
    "_fire_excessive_gutter_whitespace",
    "_fire_undersized_font_vs_canvas",
    "_fire_panel_label_too_far_from_panel",
    "_fire_excessive_whitespace_vs_content",
    "_fire_sparse_row_coverage",
    "_fire_suptitle_too_far_from_axes",
    "_fire_panel_row_misalignment",
    "_fire_legend_tick_clearance",
]
