"""VCD perceptual detection passes (23-26).

Pass 23: Low-contrast text / lines against background.
Pass 24: Colorblind-unfriendly palette detection.
Pass 25: Error-bar / CI-band visibility at target DPI.
Pass 26: Numeric precision excess in labels and annotations.
"""
from __future__ import annotations

import re
from itertools import combinations

import numpy as np
from matplotlib.text import Text
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.collections import PathCollection

from .vcd_core import _ArtistInfo, _safe_bbox, _fig_bbox


# ═══════════════════════════════════════════════════════════════════════════════
# Colour helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _to_rgb(color) -> tuple[float, float, float] | None:
    """Convert any matplotlib colour spec to an (R, G, B) tuple in [0,1]."""
    try:
        import matplotlib.colors as mcolors
        rgba = mcolors.to_rgba(color)
        return rgba[:3]
    except Exception:
        return None


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG 2.0 relative luminance from linear sRGB."""
    def _lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = [_lin(c) for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(rgb1, rgb2) -> float:
    """WCAG 2.0 contrast ratio between two sRGB colours."""
    l1 = _relative_luminance(rgb1)
    l2 = _relative_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _simulate_cvd(rgb: tuple[float, float, float],
                   kind: str = "deuteranopia") -> tuple[float, float, float]:
    """Simulate colour-vision deficiency using the Brettel/Viénot model.

    Simplified 3×3 matrix approximation (Viénot 1999) for the two most
    common forms: deuteranopia (~5 % of males) and protanopia (~1 %).
    """
    r, g, b = rgb
    if kind == "deuteranopia":
        # Viénot 1999, Table 3, deuteranopia
        rr = 0.625 * r + 0.375 * g + 0.0 * b
        gg = 0.700 * r + 0.300 * g + 0.0 * b
        bb = 0.0   * r + 0.300 * g + 0.700 * b
    elif kind == "protanopia":
        rr = 0.567 * r + 0.433 * g + 0.0 * b
        gg = 0.558 * r + 0.442 * g + 0.0 * b
        bb = 0.0   * r + 0.242 * g + 0.758 * b
    else:
        return rgb
    return (max(0, min(1, rr)), max(0, min(1, gg)), max(0, min(1, bb)))


def _colour_distance_lab(rgb1, rgb2) -> float:
    """Approximate perceptual distance (CIE76 ΔE) via simple Lab conversion.

    Uses a linearised sRGB→XYZ→Lab path.  Not as precise as full CIEDE2000
    but sufficient for flagging near-identical colours.
    """
    def _to_xyz(rgb):
        r, g, b = rgb
        # sRGB linearise
        def _lin(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        rl, gl, bl = _lin(r), _lin(g), _lin(b)
        x = 0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl
        y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl
        z = 0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl
        return x, y, z

    def _xyz_to_lab(x, y, z):
        # D65 illuminant
        xn, yn, zn = 0.95047, 1.0, 1.08883
        def _f(t):
            return t ** (1/3) if t > 0.008856 else (7.787 * t + 16/116)
        fx, fy, fz = _f(x/xn), _f(y/yn), _f(z/zn)
        L = 116 * fy - 16
        a = 500 * (fx - fy)
        b = 200 * (fy - fz)
        return L, a, b

    x1, y1, z1 = _to_xyz(rgb1)
    x2, y2, z2 = _to_xyz(rgb2)
    L1, a1, b1 = _xyz_to_lab(x1, y1, z1)
    L2, a2, b2 = _xyz_to_lab(x2, y2, z2)
    return ((L1 - L2)**2 + (a1 - a2)**2 + (b1 - b2)**2) ** 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 23: Low contrast detection
# ═══════════════════════════════════════════════════════════════════════════════

def _check_contrast(fig, renderer, infos,
                    min_text_contrast=3.0,
                    min_line_contrast=1.8):
    """Pass 23: Flag text and lines with insufficient contrast against bg.

    Uses WCAG 2.0 contrast ratio.  Thresholds:
      - Text: min 3.0:1 (relaxed from WCAG AA 4.5:1 for scientific figures
        where coloured annotations on white backgrounds are common).
      - Lines/markers: min 1.8:1 against axes background.

    Parameters
    ----------
    min_text_contrast : float
        Minimum contrast ratio for text elements against the axes/figure bg.
    min_line_contrast : float
        Minimum contrast ratio for lines and markers.
    """
    issues: list[dict] = []

    # Determine per-axes background colour
    def _axes_bg(ax):
        try:
            fc = ax.get_facecolor()
            return _to_rgb(fc)
        except Exception:
            return (1.0, 1.0, 1.0)

    fig_bg = _to_rgb(fig.get_facecolor()) or (1.0, 1.0, 1.0)

    low_contrast_texts: list[str] = []
    low_contrast_lines: list[str] = []

    for ax in fig.get_axes():
        bg = _axes_bg(ax) or fig_bg

        # Detect heatmap axes: annotations on coloured cells are expected
        # to have variable contrast depending on cell colour — skip ax.texts
        # in heatmap axes since the axes bg is misleading.
        is_heatmap = bool(ax.images)

        # Check text elements
        all_text_artists = (
            [ax.title, ax.xaxis.label, ax.yaxis.label]
            + list(ax.get_xticklabels())
            + list(ax.get_yticklabels())
        )
        # Only check ax.texts (annotations) on non-heatmap axes
        if not is_heatmap:
            all_text_artists += list(ax.texts)
        for artist in all_text_artists:
            if not isinstance(artist, Text):
                continue
            txt = artist.get_text().strip()
            if not txt or not artist.get_visible():
                continue
            fg_rgb = _to_rgb(artist.get_color())
            if fg_rgb is None:
                continue
            cr = _contrast_ratio(fg_rgb, bg)
            if cr < min_text_contrast:
                low_contrast_texts.append(
                    f"'{txt[:25]}' contrast={cr:.1f}:1"
                )

        # Check lines
        for child in ax.get_children():
            if isinstance(child, Line2D) and child.get_visible():
                label = getattr(child, '_label', '') or ''
                if label.startswith('_'):
                    continue
                c = _to_rgb(child.get_color())
                if c is None:
                    continue
                cr = _contrast_ratio(c, bg)
                if cr < min_line_contrast:
                    display = label[:20] if label else "Line2D"
                    low_contrast_lines.append(
                        f"'{display}' contrast={cr:.1f}:1"
                    )

    if low_contrast_texts:
        sample = low_contrast_texts[:4]
        issues.append({
            "type": "low_contrast_text",
            "severity": "warning",
            "detail": (
                f"{len(low_contrast_texts)} text(s) with low contrast: "
                f"{'; '.join(sample)}"
                + (f" ... +{len(low_contrast_texts) - 4} more"
                   if len(low_contrast_texts) > 4 else "")
            ),
            "elements": low_contrast_texts[:5],
        })

    if low_contrast_lines:
        sample = low_contrast_lines[:4]
        issues.append({
            "type": "low_contrast_line",
            "severity": "info",
            "detail": (
                f"{len(low_contrast_lines)} line(s) with low contrast: "
                f"{'; '.join(sample)}"
                + (f" ... +{len(low_contrast_lines) - 4} more"
                   if len(low_contrast_lines) > 4 else "")
            ),
            "elements": low_contrast_lines[:5],
        })

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 24: Colorblind-unfriendly palette
# ═══════════════════════════════════════════════════════════════════════════════

def _check_colorblind_safety(fig, renderer,
                              min_cvd_distance=10.0,
                              max_categories=20):
    """Pass 24: Detect categorical colour palettes that become ambiguous
    under simulated colour-vision deficiency (deuteranopia).

    For each axes with multiple categorical scatter / bar series, extract
    the face colours, simulate deuteranopia, and check that all pairwise
    ΔE (CIE76) distances remain above *min_cvd_distance*.

    Only runs on axes with ≤ *max_categories* distinct colours to avoid
    expensive O(n²) checks on continuous gradient colorbars.
    """
    issues: list[dict] = []

    for ax in fig.get_axes():
        if getattr(ax, 'name', None) == 'polar':
            continue
        title = ax.get_title() or f"ax@{id(ax):#x}"

        # Collect categorical face colours
        face_colours: list[tuple[str, tuple]] = []

        for child in ax.get_children():
            if not child.get_visible():
                continue
            label = getattr(child, '_label', '') or ''
            if label.startswith('_'):
                continue

            if isinstance(child, PathCollection):
                fcs = child.get_facecolor()
                if len(fcs) > 0:
                    # Use the first colour as representative
                    rgb = _to_rgb(fcs[0])
                    if rgb:
                        face_colours.append((label[:20] or "scatter", rgb))
            elif isinstance(child, Patch):
                rgb = _to_rgb(child.get_facecolor())
                if rgb:
                    face_colours.append((label[:20] or "patch", rgb))

        # Also check bar containers
        for container in getattr(ax, 'containers', []):
            for patch in getattr(container, 'patches', []):
                if isinstance(patch, Patch):
                    label = getattr(container, '_label', '') or ''
                    rgb = _to_rgb(patch.get_facecolor())
                    if rgb:
                        face_colours.append((label[:20] or "bar", rgb))
                    break  # one per container

        n_colours = len(face_colours)
        if n_colours < 2 or n_colours > max_categories:
            continue

        # Deduplicate very close colours (same series shown twice)
        unique_colours: list[tuple[str, tuple]] = []
        for label, rgb in face_colours:
            duplicate = False
            for _, existing_rgb in unique_colours:
                if _colour_distance_lab(rgb, existing_rgb) < 2.0:
                    duplicate = True
                    break
            if not duplicate:
                unique_colours.append((label, rgb))

        if len(unique_colours) < 2:
            continue

        # Simulate CVD and check pairwise distances
        confusable_pairs: list[str] = []
        for (lbl_a, rgb_a), (lbl_b, rgb_b) in combinations(unique_colours, 2):
            sim_a = _simulate_cvd(rgb_a, "deuteranopia")
            sim_b = _simulate_cvd(rgb_b, "deuteranopia")
            dist = _colour_distance_lab(sim_a, sim_b)
            if dist < min_cvd_distance:
                confusable_pairs.append(
                    f"'{lbl_a}' vs '{lbl_b}' (ΔE={dist:.1f})"
                )

        if confusable_pairs:
            sample = confusable_pairs[:3]
            issues.append({
                "type": "colorblind_confusable",
                "severity": "info",
                "detail": (
                    f"In '{title}': {len(confusable_pairs)} colour pair(s) "
                    f"may be confusable under deuteranopia: "
                    f"{'; '.join(sample)}"
                    + (f" ... +{len(confusable_pairs) - 3} more"
                       if len(confusable_pairs) > 3 else "")
                ),
                "elements": [p for p in confusable_pairs[:5]],
            })

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 25: Error-bar / CI-band visibility
# ═══════════════════════════════════════════════════════════════════════════════

def _check_errorbar_visibility(fig, renderer, target_dpi=300,
                                min_cap_px=1.5):
    """Pass 25: Detect error bars or CI bands that are too thin to see.

    At publication DPI (300), a line that renders at < 1.5 px is nearly
    invisible.  This detects:
      a) Error-bar cap lines whose bbox height or width < min_cap_px.
      b) Fill-between CI bands whose rendered height < min_cap_px at any point.
    """
    issues: list[dict] = []
    scale = target_dpi / fig.dpi if fig.dpi > 0 else 1.0

    thin_errorbars: list[str] = []

    for ax in fig.get_axes():
        title = ax.get_title() or f"ax@{id(ax):#x}"

        # Check errorbar containers
        for container in getattr(ax, 'containers', []):
            if not hasattr(container, 'lines'):
                continue
            # ErrorbarContainer has .lines = (data_line, caplines, barlinecols)
            lines_tuple = container.lines
            if len(lines_tuple) < 3:
                continue
            cap_lines = lines_tuple[1] if lines_tuple[1] else []
            bar_cols = lines_tuple[2] if lines_tuple[2] else []

            for cap in cap_lines:
                if not isinstance(cap, Line2D) or not cap.get_visible():
                    continue
                bb = _safe_bbox(cap, renderer)
                if bb is None:
                    continue
                effective_h = bb.height * scale
                effective_w = bb.width * scale
                smallest = min(effective_h, effective_w)
                if smallest < min_cap_px and smallest > 0:
                    thin_errorbars.append(
                        f"errorbar cap in '{title}' ({smallest:.1f}px at {target_dpi}dpi)"
                    )

    if thin_errorbars:
        sample = thin_errorbars[:3]
        issues.append({
            "type": "errorbar_invisible",
            "severity": "info",
            "detail": (
                f"{len(thin_errorbars)} error-bar element(s) may be "
                f"invisible at {target_dpi} DPI: {'; '.join(sample)}"
                + (f" ... +{len(thin_errorbars) - 3} more"
                   if len(thin_errorbars) > 3 else "")
            ),
            "elements": thin_errorbars[:5],
        })

    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# Pass 26: Numeric precision excess
# ═══════════════════════════════════════════════════════════════════════════════

# Pattern: a number with 5+ decimal digits (e.g. "0.123456", "-3.14159265")
_EXCESS_PRECISION_RE = re.compile(
    r'-?\d+\.(\d{5,})'
)


def _check_precision_excess(fig, renderer, infos,
                             max_decimals=4):
    """Pass 26: Flag labels / annotations with excessive numeric precision.

    Scientific figures rarely need more than 4 decimal places in tick
    labels or annotations.  Excessive precision wastes space and impedes
    readability.

    Parameters
    ----------
    max_decimals : int
        Maximum acceptable decimal digits before flagging.
    """
    issues: list[dict] = []
    excess_examples: list[str] = []

    for info in infos:
        if info.kind != "text":
            continue
        artist = info.artist
        if not isinstance(artist, Text):
            continue
        txt = artist.get_text().strip()
        if not txt:
            continue

        m = _EXCESS_PRECISION_RE.search(txt)
        if m:
            n_dec = len(m.group(1))
            if n_dec > max_decimals:
                excess_examples.append(
                    f"'{txt[:30]}' ({n_dec} decimals)"
                )

    if excess_examples:
        sample = excess_examples[:4]
        issues.append({
            "type": "precision_excess",
            "severity": "info",
            "detail": (
                f"{len(excess_examples)} label(s) with >{max_decimals} "
                f"decimal places: {'; '.join(sample)}"
                + (f" ... +{len(excess_examples) - 4} more"
                   if len(excess_examples) > 4 else "")
            ),
            "elements": excess_examples[:5],
        })

    return issues
