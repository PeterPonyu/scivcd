"""TYPOGRAPHY-category detectors.

Ported from ``experiments/scivcd-lifetime/scripts/vcd/lifecycle/``
(``tier2_geometry.py`` + ``tier2_density.py``).
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


_BOLD_WEIGHTS = {"bold", "heavy", "semibold", "extra bold", "extra-bold",
                 600, 700, 800, 900}
_ELLIPSIS_TOKENS = ("\u2026", "...")


def _is_bold(artist: Any) -> bool:
    try:
        w = artist.get_fontweight()
    except Exception:
        return False
    if isinstance(w, (int, float)):
        return w >= 600
    if isinstance(w, str):
        return w.lower() in _BOLD_WEIGHTS
    return False


def _gid(artist: Any) -> str:
    try:
        g = artist.get_gid()
    except Exception:
        return ""
    return g if isinstance(g, str) else ""


def _is_panel_label(artist: Any) -> bool:
    return _gid(artist).startswith("panel_label:")


def _data_axes(fig: Any) -> list:
    out = []
    for ax in fig.get_axes():
        if getattr(ax, "_colorbar", None):
            continue
        out.append(ax)
    return out


# ---------------------------------------------------------------------------
# inconsistent_typography
# ---------------------------------------------------------------------------

def _fire_inconsistent_typography(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag figures with too many distinct fontsizes."""
    out: list[Finding] = []
    max_distinct = config.max_distinct_sizes  # default 6
    sizes: set = set()
    try:
        texts = list(fig.findobj(Text))
    except Exception:
        return out
    for t in texts:
        try:
            txt = (t.get_text() or "").strip()
            if not txt:
                continue
            size = round(float(t.get_fontsize()), 1)
            sizes.add(size)
        except Exception:
            continue
    if len(sizes) > max_distinct:
        out.append(Finding(
            check_id="inconsistent_typography",
            severity=Severity.MEDIUM,
            category=Category.TYPOGRAPHY,
            stage=Stage.TIER2,
            message=(
                f"figure uses {len(sizes)} distinct fontsizes "
                f"({sorted(sizes)[:10]}); cap at {max_distinct} for consistency"
            ),
            call_site=None,
            fix_suggestion=(
                f"collapse to <= {max_distinct} fontsize tiers (title, "
                "inner-title, label, tick, legend, annotation); reuse the "
                "same size across axes"
            ),
            artist=fig,
        ))
    return out


register(CheckSpec(
    id="inconsistent_typography",
    severity=Severity.MEDIUM,
    category=Category.TYPOGRAPHY,
    stage=Stage.TIER2,
    fire=_fire_inconsistent_typography,
    description="Figure mixes too many distinct fontsizes",
    config_keys=("max_distinct_sizes",),
))


# ---------------------------------------------------------------------------
# canvas_scale_font_too_small
# ---------------------------------------------------------------------------

def _canvas_font_floor(fig: Any, config: ScivcdConfig) -> float:
    """Return the canvas-aware absolute minimum rendered fontsize (pt)."""
    try:
        w, h = fig.get_size_inches()
        short = min(float(w), float(h))
    except Exception:
        return config.floor_pt
    if short >= config.large_canvas_threshold_in:
        return config.large_canvas_floor_pt
    return config.floor_pt


def _fire_canvas_scale_font_too_small(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Every Text artist must render at >= canvas-aware floor."""
    out: list[Finding] = []
    floor = _canvas_font_floor(fig, config)
    seen = set()
    try:
        artists = list(fig.findobj(Text))
    except Exception:
        return out
    for artist in artists:
        if id(artist) in seen:
            continue
        seen.add(id(artist))
        if _is_panel_label(artist):
            continue
        try:
            text = (artist.get_text() or "").strip()
            if not text:
                continue
            size = float(artist.get_fontsize())
        except Exception:
            continue
        if size >= floor:
            continue
        g = _gid(artist)
        role = "text"
        if g.startswith("tick"):
            role = "tick"
        elif g.startswith("legend_text"):
            role = "legend"
        elif g.startswith("cbar"):
            role = "colorbar"
        out.append(Finding(
            check_id="canvas_scale_font_too_small",
            severity=Severity.MEDIUM,
            category=Category.TYPOGRAPHY,
            stage=Stage.TIER2,
            message=(
                f"{role} '{text[:30]}' at {size:.1f}pt below canvas floor "
                f"{floor:.1f}pt (canvas-aware)"
            ),
            call_site=None,
            fix_suggestion=(
                f"bump fontsize to >= {floor:.0f}pt; for ticks, use "
                "`ax.tick_params(labelsize=N)`; for legend, "
                "`ax.legend(fontsize=N)`"
            ),
            artist=artist,
        ))
    return out


register(CheckSpec(
    id="canvas_scale_font_too_small",
    severity=Severity.MEDIUM,
    category=Category.TYPOGRAPHY,
    stage=Stage.TIER2,
    fire=_fire_canvas_scale_font_too_small,
    description="Text fontsize below canvas-aware publication floor",
    config_keys=(
        "floor_pt",
        "large_canvas_floor_pt",
        "large_canvas_threshold_in",
    ),
))


# ---------------------------------------------------------------------------
# label_string_ellipsis
# ---------------------------------------------------------------------------

def _looks_like_truncated_label(text: str) -> bool:
    """Heuristic for pre-truncated label strings.

    We intentionally only flag explicit ellipsis tokens, not every shortened
    abbreviation. This keeps the rule low-noise and focused on the exact class
    of publication-polish issues surfaced in visual review.
    """
    text = text.strip()
    if not text:
        return False
    return any(token in text for token in _ELLIPSIS_TOKENS)


def _fire_label_string_ellipsis(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag text labels that already contain a visible ellipsis marker."""
    out: list[Finding] = []
    seen = set()
    try:
        artists = list(fig.findobj(Text))
    except Exception:
        return out
    for artist in artists:
        if id(artist) in seen:
            continue
        seen.add(id(artist))
        if _is_panel_label(artist):
            continue
        try:
            text = (artist.get_text() or "").strip()
        except Exception:
            continue
        if not _looks_like_truncated_label(text):
            continue
        out.append(Finding(
            check_id="label_string_ellipsis",
            severity=Severity.LOW,
            category=Category.TYPOGRAPHY,
            stage=Stage.TIER2,
            message=(
                f"text label '{text[:40]}' contains a visible ellipsis marker; "
                "pre-truncated labels often hide publication-readiness issues"
            ),
            call_site=None,
            fix_suggestion=(
                "prefer semantic abbreviation, numeric/index indirection, or "
                "more panel space instead of baking ellipses into the figure label"
            ),
            artist=artist,
        ))
    return out


register(CheckSpec(
    id="label_string_ellipsis",
    severity=Severity.LOW,
    category=Category.TYPOGRAPHY,
    stage=Stage.TIER2,
    fire=_fire_label_string_ellipsis,
    description="Text label contains a visible ellipsis / pre-truncation marker",
))


# ---------------------------------------------------------------------------
# effective_font_too_small
# ---------------------------------------------------------------------------

def _text_role(artist: Any) -> str:
    gid = _gid(artist)
    if _is_panel_label(artist):
        return "panel_label"
    if gid.startswith("tick"):
        return "tick"
    if gid.startswith("legend"):
        return "legend"
    try:
        axes = getattr(artist, "axes", None)
        if axes is not None and artist in (axes.title, axes.xaxis.label, axes.yaxis.label):
            return "title" if artist is axes.title else "axis_label"
    except Exception:
        pass
    return "annotation"


def _fire_effective_font_too_small(fig: Any, config: ScivcdConfig) -> list[Finding]:
    out: list[Finding] = []
    composed_scale = float(getattr(config, "composed_scale", 1.0))
    final_scale = float(getattr(config, "final_print_scale", 1.0))
    floors = getattr(config, "effective_font_floors", {}) or {}
    seen = set()
    try:
        artists = list(fig.findobj(Text))
    except Exception:
        return out
    for artist in artists:
        if id(artist) in seen:
            continue
        seen.add(id(artist))
        try:
            text = (artist.get_text() or "").strip()
            source = float(artist.get_fontsize())
        except Exception:
            continue
        if not text:
            continue
        role = _text_role(artist)
        floor = float(floors.get(role, floors.get("annotation", 8.0)))
        effective = source * composed_scale * final_scale
        if effective >= floor:
            continue
        out.append(Finding(
            check_id="effective_font_too_small",
            severity=Severity.MEDIUM,
            category=Category.TYPOGRAPHY,
            stage=Stage.TIER2,
            message=f"{role} '{text[:30]}' effective font {effective:.1f}pt below floor {floor:.1f}pt",
            fix_suggestion="increase source fontsize or reduce composed/final downscaling for this text role",
            evidence={"role": role, "source_font_pt": source, "component_to_composed_scale": composed_scale, "final_print_scale": final_scale, "effective_font_pt": round(effective, 3), "role_floor_pt": floor},
            artist=artist,
        ))
    return out


register(CheckSpec(
    id="effective_font_too_small",
    severity=Severity.MEDIUM,
    category=Category.TYPOGRAPHY,
    stage=Stage.TIER2,
    fire=_fire_effective_font_too_small,
    description="Text effective font size after composition/final scaling is too small",
    config_keys=("composed_scale", "final_print_scale", "effective_font_floors"),
))


# ---------------------------------------------------------------------------
# bold_subpanel_title
# ---------------------------------------------------------------------------

def _fire_bold_subpanel_title(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Policy check: axes titles must not be bold."""
    out: list[Finding] = []
    for ax in _data_axes(fig):
        try:
            title = ax.title
            if title is None:
                continue
            txt = (title.get_text() or "").strip()
            if not txt:
                continue
        except Exception:
            continue
        if _is_bold(title):
            out.append(Finding(
                check_id="bold_subpanel_title",
                severity=Severity.LOW,
                category=Category.TYPOGRAPHY,
                stage=Stage.TIER2,
                message=(
                    f"axes title '{txt[:30]}' rendered bold; policy reserves "
                    "bold for panel labels only"
                ),
                call_site=None,
                fix_suggestion=(
                    "call `ax.set_title(..., fontweight='regular')` (or drop "
                    "the weight kwarg entirely); use italic for emphasis"
                ),
                artist=title,
            ))
    return out


register(CheckSpec(
    id="bold_subpanel_title",
    severity=Severity.LOW,
    category=Category.TYPOGRAPHY,
    stage=Stage.TIER2,
    fire=_fire_bold_subpanel_title,
    description="Axes title uses bold weight (policy: labels only)",
))


__all__ = [
    "_fire_inconsistent_typography",
    "_fire_canvas_scale_font_too_small",
    "_fire_label_string_ellipsis",
    "_fire_effective_font_too_small",
    "_fire_bold_subpanel_title",
]
