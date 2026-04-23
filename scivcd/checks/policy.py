"""POLICY-category detectors.

Ported from ``experiments/scivcd-lifetime/scripts/vcd/lifecycle/``
(``tier2_policy.py`` + ``tier2_density.py``).
"""
from __future__ import annotations

import re
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

_PANEL_LABEL_LETTER_RE = re.compile(r"^\(?[A-Za-z][0-9]?\)?[:.\-]?$")


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
# panel_label_has_descriptive_text
# ---------------------------------------------------------------------------

def _fire_panel_label_has_descriptive_text(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Panel labels must be a standalone letter/digit."""
    out: list[Finding] = []
    try:
        artists = list(fig.findobj(Text))
    except Exception:
        return out
    for artist in artists:
        if not _is_panel_label(artist):
            continue
        try:
            text = (artist.get_text() or "").strip()
        except Exception:
            continue
        if not text:
            continue
        if _PANEL_LABEL_LETTER_RE.match(text):
            continue
        out.append(Finding(
            check_id="panel_label_has_descriptive_text",
            severity=Severity.HIGH,
            category=Category.POLICY,
            stage=Stage.TIER2,
            message=(
                f"panel label text '{text[:40]}' carries descriptive prose; "
                "labels must be a bare letter ('A', '(a)', 'A.')"
            ),
            call_site=None,
            fix_suggestion=(
                "set the label text to just the letter, and move the section "
                "title into a sibling `fig.text()` with a separate gid, or "
                "into a suptitle on the inner row"
            ),
            artist=artist,
        ))
    return out


register(CheckSpec(
    id="panel_label_has_descriptive_text",
    severity=Severity.HIGH,
    category=Category.POLICY,
    stage=Stage.TIER2,
    fire=_fire_panel_label_has_descriptive_text,
    description="Panel label contains descriptive prose beyond the letter",
))


# ---------------------------------------------------------------------------
# panel_label_companion_text
# ---------------------------------------------------------------------------

def _fire_panel_label_companion_text(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Detects the 'A Training dynamics' side-by-side anti-pattern."""
    out: list[Finding] = []
    try:
        texts = list(fig.findobj(Text))
    except Exception:
        return out
    figlevel: list[Any] = []
    for t in texts:
        try:
            if getattr(t, "axes", None) is not None:
                continue
            txt = (t.get_text() or "").strip()
            if not txt:
                continue
            pos = t.get_position()
        except Exception:
            continue
        figlevel.append((t, txt, float(pos[0]), float(pos[1])))

    horiz_limit = config.panel_label_companion_horiz  # default 0.12
    vert_limit = config.panel_label_companion_vert  # default 0.025

    for label_artist, label_text, lx, ly in figlevel:
        if not _is_panel_label(label_artist):
            continue
        for other, other_text, ox, oy in figlevel:
            if other is label_artist:
                continue
            if _is_panel_label(other):
                continue
            other_gid = _gid(other)
            if other_gid.startswith(("tick", "cbar_tick", "Spine")):
                continue
            try:
                float(other_text.replace("−", "-").replace(",", "").strip("()%"))
                continue
            except ValueError:
                pass
            if abs(oy - ly) > vert_limit:
                continue
            if not (0.0 < (ox - lx) < horiz_limit):
                continue
            out.append(Finding(
                check_id="panel_label_companion_text",
                severity=Severity.HIGH,
                category=Category.POLICY,
                stage=Stage.TIER2,
                message=(
                    f"panel label '{label_text[:12]}' has a companion "
                    f"heading '{other_text[:30]}' at ({ox:.2f},{oy:.2f}); "
                    "panel labels must stand alone"
                ),
                call_site=None,
                fix_suggestion=(
                    "remove the adjacent section heading; if a section "
                    "title is needed, place it as a suptitle on the row's "
                    "top inner axes, not next to the letter"
                ),
                artist=other,
            ))
            break
    return out


register(CheckSpec(
    id="panel_label_companion_text",
    severity=Severity.HIGH,
    category=Category.POLICY,
    stage=Stage.TIER2,
    fire=_fire_panel_label_companion_text,
    description="Panel label has an adjacent descriptive-heading sibling",
    config_keys=("panel_label_companion_horiz", "panel_label_companion_vert"),
))


# ---------------------------------------------------------------------------
# non_panel_bold_text
# ---------------------------------------------------------------------------

def _fire_non_panel_bold_text(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Only panel labels may carry bold weight."""
    out: list[Finding] = []
    try:
        artists = list(fig.findobj(Text))
    except Exception:
        return out
    seen = set()
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
        if not text:
            continue
        if not _is_bold(artist):
            continue
        out.append(Finding(
            check_id="non_panel_bold_text",
            severity=Severity.MEDIUM,
            category=Category.POLICY,
            stage=Stage.TIER2,
            message=(
                f"Text '{text[:30]}' uses bold weight; policy reserves bold "
                "for panel labels only — use italic or size for emphasis"
            ),
            call_site=None,
            fix_suggestion=(
                "set fontweight='regular' (or 'normal'); keep bold for "
                "artists carrying gid='panel_label:...'"
            ),
            artist=artist,
        ))
    return out


register(CheckSpec(
    id="non_panel_bold_text",
    severity=Severity.MEDIUM,
    category=Category.POLICY,
    stage=Stage.TIER2,
    fire=_fire_non_panel_bold_text,
    description="Non-panel-label text uses bold weight",
))


# ---------------------------------------------------------------------------
# missing_axis_labels
# ---------------------------------------------------------------------------

def _has_visible_data(ax: Any) -> bool:
    try:
        if any(line.get_visible() for line in getattr(ax, "lines", [])):
            return True
        if any(coll.get_visible() for coll in getattr(ax, "collections", [])):
            return True
        for patch in getattr(ax, "patches", []):
            if patch is getattr(ax, "patch", None):
                continue
            if patch.get_visible():
                return True
        if any(img.get_visible() for img in getattr(ax, "images", [])):
            return True
    except Exception:
        return False
    return False


def _fire_missing_axis_labels(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Axes with visible data should expose both x and y labels."""
    out: list[Finding] = []
    for ax in _data_axes(fig):
        if not _has_visible_data(ax):
            continue
        try:
            xlabel = (ax.get_xlabel() or "").strip()
            ylabel = (ax.get_ylabel() or "").strip()
        except Exception:
            continue
        missing = []
        if not xlabel:
            missing.append("xlabel")
        if not ylabel:
            missing.append("ylabel")
        if not missing:
            continue
        out.append(Finding(
            check_id="missing_axis_labels",
            severity=Severity.HIGH,
            category=Category.POLICY,
            stage=Stage.TIER2,
            message=(
                f"data axes is missing required labels: {', '.join(missing)}"
            ),
            call_site=None,
            fix_suggestion=(
                "add informative x/y labels (even short scientific units or "
                "dimension names) so the panel remains interpretable in isolation"
            ),
            artist=ax,
        ))
    return out


register(CheckSpec(
    id="missing_axis_labels",
    severity=Severity.HIGH,
    category=Category.POLICY,
    stage=Stage.TIER2,
    fire=_fire_missing_axis_labels,
    description="Axes with data are missing an x or y label",
))


# ---------------------------------------------------------------------------
# missing_legend
# ---------------------------------------------------------------------------

def _fire_missing_legend(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """If multiple labeled series exist, a legend should also exist."""
    out: list[Finding] = []
    for ax in _data_axes(fig):
        try:
            handles, labels = ax.get_legend_handles_labels()
        except Exception:
            continue
        visible_labels = [
            label for handle, label in zip(handles, labels)
            if label and not label.startswith("_")
        ]
        if len(visible_labels) < 2:
            continue
        if ax.get_legend() is not None:
            continue
        out.append(Finding(
            check_id="missing_legend",
            severity=Severity.HIGH,
            category=Category.POLICY,
            stage=Stage.TIER2,
            message=(
                f"{len(visible_labels)} labeled series are present but no legend was added"
            ),
            call_site=None,
            fix_suggestion=(
                "call `ax.legend(...)` or replace the labels with a direct-labeling "
                "scheme that clearly names every plotted series"
            ),
            artist=ax,
        ))
    return out


register(CheckSpec(
    id="missing_legend",
    severity=Severity.HIGH,
    category=Category.POLICY,
    stage=Stage.TIER2,
    fire=_fire_missing_legend,
    description="Multiple labeled series are present without a legend",
))


# ---------------------------------------------------------------------------
# figure_too_small
# ---------------------------------------------------------------------------

def _fire_figure_too_small(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Very small figures are unlikely to meet publication readability floors."""
    out: list[Finding] = []
    try:
        width_in, height_in = fig.get_size_inches()
    except Exception:
        return out
    if width_in >= 2.5 and height_in >= 2.0:
        return out
    out.append(Finding(
        check_id="figure_too_small",
        severity=Severity.HIGH,
        category=Category.POLICY,
        stage=Stage.TIER2,
        message=(
            f"figure canvas is too small for publication ({width_in:.1f}×{height_in:.1f} in)"
        ),
        call_site=None,
        fix_suggestion=(
            "increase `figsize` to a publication-oriented minimum before relying "
            "on font and label heuristics"
        ),
        artist=fig,
    ))
    return out


register(CheckSpec(
    id="figure_too_small",
    severity=Severity.HIGH,
    category=Category.POLICY,
    stage=Stage.TIER2,
    fire=_fire_figure_too_small,
    description="Figure canvas is too small for publication-ready output",
))


# ---------------------------------------------------------------------------
# incomplete_panel_labeling
# ---------------------------------------------------------------------------

def _axes_has_nearby_panel_label(ax: Any, panel_label_artists: list) -> bool:
    try:
        pos = ax.get_position()
    except Exception:
        return True
    y_mid = 0.5 * (pos.y0 + pos.y1)
    above = []
    left = []
    for art in panel_label_artists:
        try:
            x, y = art.get_position()
            x = float(x)
            y = float(y)
        except Exception:
            continue
        dx = max(x - pos.x1, pos.x0 - x, 0.0)
        dy = max(y - pos.y1, pos.y0 - y, 0.0)
        if dx + dy <= 0.08:
            return True
        if y >= pos.y1 - 0.005:
            above.append((x, y))
        if x < pos.x0 and abs(y - y_mid) <= (pos.y1 - pos.y0) * 0.5 + 0.05:
            left.append((x, y))
    if left:
        return True
    if above:
        return True
    return False


def _fire_incomplete_panel_labeling(
    fig: Any, config: ScivcdConfig
) -> list[Finding]:
    """Flag multi-panel figures where some axes have labels and others don't."""
    out: list[Finding] = []
    data_axes = _data_axes(fig)
    if len(data_axes) <= 2:
        return out
    try:
        all_texts = list(fig.findobj(Text))
    except Exception:
        return out
    panel_labels = [t for t in all_texts if _is_panel_label(t)]
    if not panel_labels:
        return out
    unlabeled = []
    for ax in data_axes:
        if not _axes_has_nearby_panel_label(ax, panel_labels):
            unlabeled.append(ax)
    if not unlabeled:
        return out
    if len(unlabeled) == len(data_axes):
        return out
    out.append(Finding(
        check_id="incomplete_panel_labeling",
        severity=Severity.HIGH,
        category=Category.POLICY,
        stage=Stage.TIER2,
        message=(
            f"{len(panel_labels)} panel labels found but {len(unlabeled)} of "
            f"{len(data_axes)} data axes have no nearby label — labeling is "
            "partial; either label every axes or none"
        ),
        call_site=None,
        fix_suggestion=(
            "add panel labels (e.g. `fig.text(..., gid='panel_label:X')`) "
            "to the unlabeled axes, anchored to each axes' top-left via "
            "ax.get_position(), or remove existing labels for consistency"
        ),
        artist=unlabeled[0],
    ))
    return out


register(CheckSpec(
    id="incomplete_panel_labeling",
    severity=Severity.HIGH,
    category=Category.POLICY,
    stage=Stage.TIER2,
    fire=_fire_incomplete_panel_labeling,
    description="Some axes have panel labels while others do not",
))


__all__ = [
    "_fire_panel_label_has_descriptive_text",
    "_fire_panel_label_companion_text",
    "_fire_non_panel_bold_text",
    "_fire_missing_axis_labels",
    "_fire_missing_legend",
    "_fire_figure_too_small",
    "_fire_incomplete_panel_labeling",
]
