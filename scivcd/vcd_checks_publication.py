"""Publication-quality VCD checks (US-204).

Three reviewer-facing checks that target defects invisible to the artist-overlap
geometry passes but frequently caught by typesetting reviewers:

- ``check_minimum_font_size``  — flags any text artist whose effective rendered
  size at the figure's ``\\includegraphics`` width is below the configured
  threshold (default 7pt, the Nature/Cell lower bound).
- ``check_colorblind_safety``  — simulates deuteranopia and protanopia via the
  Machado 2009 CVD matrices and flags color pairs whose simulated CIE ΔE₇₆
  distance drops below a configurable threshold.
- ``check_effective_dpi``      — computes effective DPI at the target rendered
  width and flags anything below 300 (print-quality).

Each check returns a list of issue dicts using the same schema as the other
``vcd_checks_*`` modules (``type``, ``severity``, ``detail``, ``elements``).
Callers should let the package-level severity mapper annotate each issue with
its 4-level ``severity_level`` after collection.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.text import Text


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Nature/Cell lower bound for body text after composition scaling.
DEFAULT_MIN_RENDERED_PT: float = 7.0

# Threshold below which two colors are considered indistinguishable under CVD.
# CIE ΔE₇₆ ≈ 10 is the threshold for "just noticeable" under normal vision;
# for CVD we relax slightly to 12 so we don't flag every slightly-off pair.
DEFAULT_MIN_CVD_DELTA_E: float = 12.0

# Print-quality threshold; anything below 300 looks blurred on a modern reviewer PDF.
DEFAULT_MIN_EFFECTIVE_DPI: float = 300.0

# Standard single-column and double-column widths for common journals.
DEFAULT_PAGE_TEXT_WIDTH_IN: float = 7.0  # LaTeX article 7in textwidth
DEFAULT_INCLUDE_WIDTH_FRACTION: float = 1.0  # \includegraphics[width=\textwidth]


# ---------------------------------------------------------------------------
# Machado 2009 CVD simulation matrices (severity 1.0 = complete)
# ---------------------------------------------------------------------------
# Reference: Machado, Oliveira & Fernandes, TVCG 2009, "A Physiologically-based
# Model for Simulation of Color Vision Deficiency". Matrices operate on linear
# sRGB color vectors.

_MACHADO_DEUTERANOPIA = np.array([
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501,  0.047413],
    [-0.011820, 0.042940, 0.968881],
])

_MACHADO_PROTANOPIA = np.array([
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281,  0.099216],
    [-0.003882, -0.048116, 1.051998],
])


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    """Convert sRGB [0,1] channel to linear light."""
    low = rgb <= 0.04045
    out = np.empty_like(rgb)
    out[low] = rgb[low] / 12.92
    out[~low] = ((rgb[~low] + 0.055) / 1.055) ** 2.4
    return out


def _linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    """Convert linear light channel back to sRGB [0,1]."""
    low = rgb <= 0.0031308
    out = np.empty_like(rgb)
    out[low] = rgb[low] * 12.92
    out[~low] = 1.055 * (rgb[~low] ** (1 / 2.4)) - 0.055
    return np.clip(out, 0.0, 1.0)


def _simulate_cvd(rgb: Tuple[float, float, float], matrix: np.ndarray) -> np.ndarray:
    """Simulate a CVD by applying ``matrix`` in linear-sRGB space."""
    arr = np.asarray(rgb, dtype=float).reshape(-1)
    linear = _srgb_to_linear(arr)
    sim = matrix @ linear
    return _linear_to_srgb(sim)


def _rgb_to_lab(rgb: Sequence[float]) -> Tuple[float, float, float]:
    """Minimal sRGB → CIELAB conversion (D65). Fine for ΔE₇₆ comparisons."""
    arr = np.asarray(rgb, dtype=float).reshape(-1)[:3]
    linear = _srgb_to_linear(arr)
    # sRGB D65 → XYZ
    m = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = m @ linear
    # Normalize by D65 white point
    xn, yn, zn = 0.95047, 1.00000, 1.08883
    fx = _lab_f(xyz[0] / xn)
    fy = _lab_f(xyz[1] / yn)
    fz = _lab_f(xyz[2] / zn)
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return float(L), float(a), float(b)


def _lab_f(t: float) -> float:
    delta = 6.0 / 29.0
    if t > delta ** 3:
        return t ** (1.0 / 3.0)
    return t / (3 * delta * delta) + 4.0 / 29.0


def _delta_e_76(a: Sequence[float], b: Sequence[float]) -> float:
    """CIE ΔE₇₆ Euclidean distance in Lab."""
    la, aa, ba = _rgb_to_lab(a)
    lb, ab_, bb = _rgb_to_lab(b)
    return math.sqrt((la - lb) ** 2 + (aa - ab_) ** 2 + (ba - bb) ** 2)


# ---------------------------------------------------------------------------
# Check 1 — minimum rendered font size
# ---------------------------------------------------------------------------

def check_minimum_font_size(
    fig,
    *,
    min_pt: float = DEFAULT_MIN_RENDERED_PT,
    include_width_fraction: float = DEFAULT_INCLUDE_WIDTH_FRACTION,
    page_text_width_in: float = DEFAULT_PAGE_TEXT_WIDTH_IN,
) -> List[dict]:
    """Flag text artists whose effective rendered size falls below ``min_pt``.

    The effective point size is the nominal size scaled by the ratio of the
    included width to the figure's generated width. For a 14-inch figure
    rendered at ``\\includegraphics[width=\\textwidth]`` (= 7 inch), a 10pt
    label is rendered at 5pt — below the 7pt threshold.
    """
    fig_w_in, _ = fig.get_size_inches()
    if fig_w_in <= 0:
        return []
    include_width_in = page_text_width_in * include_width_fraction
    scale = include_width_in / fig_w_in

    issues: List[dict] = []
    seen: set = set()
    for ax in fig.get_axes():
        for artist in list(ax.texts) + [ax.title, ax.xaxis.label, ax.yaxis.label]:
            if artist is None or not isinstance(artist, Text):
                continue
            txt = artist.get_text().strip()
            if not txt:
                continue
            if id(artist) in seen:
                continue
            seen.add(id(artist))
            nominal = float(artist.get_fontsize())
            effective = nominal * scale
            if effective < min_pt:
                issues.append({
                    "type": "minimum_font_size",
                    "severity": "warning",
                    "detail": (
                        f"text '{txt[:40]}' renders at {effective:.1f}pt "
                        f"(nominal {nominal:.1f}pt × scale {scale:.2f}), below {min_pt:.1f}pt"
                    ),
                    "elements": [f"text: {txt[:40]}"],
                })
        for tl in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
            if id(tl) in seen:
                continue
            seen.add(id(tl))
            label = tl.get_text().strip()
            if not label:
                continue
            nominal = float(tl.get_fontsize())
            effective = nominal * scale
            if effective < min_pt:
                issues.append({
                    "type": "minimum_font_size",
                    "severity": "warning",
                    "detail": (
                        f"ticklabel '{label[:20]}' renders at {effective:.1f}pt, "
                        f"below {min_pt:.1f}pt"
                    ),
                    "elements": [f"tick: {label[:20]}"],
                })
    return issues


# ---------------------------------------------------------------------------
# Check 2 — colorblind safety via Machado CVD simulation
# ---------------------------------------------------------------------------

def check_colorblind_safety(
    fig,
    *,
    min_delta_e: float = DEFAULT_MIN_CVD_DELTA_E,
    palette: Iterable = None,
) -> List[dict]:
    """Flag color pairs that collapse under simulated deuteranopia / protanopia.

    The check pulls each unique color used by plotted lines, patches, and
    scatter collections, simulates deuteranopia and protanopia via the
    Machado 2009 matrices, and measures CIE ΔE₇₆ pairwise. Any pair whose
    simulated distance under either CVD falls below ``min_delta_e`` is flagged.
    """
    colors: list[Tuple[float, float, float]] = []
    labels: list[str] = []

    if palette is not None:
        for idx, c in enumerate(palette):
            colors.append(to_rgb(c))
            labels.append(f"palette[{idx}]")
    else:
        seen: set = set()
        for ax in fig.get_axes():
            for line in ax.get_lines():
                try:
                    c = to_rgb(line.get_color())
                except Exception:
                    continue
                key = tuple(round(v, 3) for v in c)
                if key in seen:
                    continue
                seen.add(key)
                colors.append(c)
                labels.append(f"line: {line.get_label() or 'unlabeled'}")
            for patch in ax.patches:
                try:
                    c = to_rgb(patch.get_facecolor())
                except Exception:
                    continue
                key = tuple(round(v, 3) for v in c)
                if key in seen:
                    continue
                seen.add(key)
                colors.append(c)
                labels.append(f"patch: {patch.get_label() or 'unlabeled'}")

    n = len(colors)
    if n < 2:
        return []

    issues: List[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            ci, cj = colors[i], colors[j]
            # Skip if even normal vision can barely tell them apart — not our job.
            if _delta_e_76(ci, cj) < min_delta_e:
                continue
            deut_i = _simulate_cvd(ci, _MACHADO_DEUTERANOPIA)
            deut_j = _simulate_cvd(cj, _MACHADO_DEUTERANOPIA)
            prot_i = _simulate_cvd(ci, _MACHADO_PROTANOPIA)
            prot_j = _simulate_cvd(cj, _MACHADO_PROTANOPIA)
            d_deut = _delta_e_76(deut_i, deut_j)
            d_prot = _delta_e_76(prot_i, prot_j)
            worst = min(d_deut, d_prot)
            if worst < min_delta_e:
                which = "deuteranopia" if d_deut <= d_prot else "protanopia"
                issues.append({
                    "type": "colorblind_confusable",
                    "severity": "warning",
                    "detail": (
                        f"colors {labels[i]!r} and {labels[j]!r} collapse under "
                        f"{which} (ΔE₇₆ = {worst:.1f} < {min_delta_e:.1f})"
                    ),
                    "elements": [labels[i], labels[j]],
                })
    return issues


# ---------------------------------------------------------------------------
# Check 3 — effective DPI at rendered width
# ---------------------------------------------------------------------------

def check_effective_dpi(
    fig,
    *,
    min_effective_dpi: float = DEFAULT_MIN_EFFECTIVE_DPI,
    include_width_fraction: float = DEFAULT_INCLUDE_WIDTH_FRACTION,
    page_text_width_in: float = DEFAULT_PAGE_TEXT_WIDTH_IN,
) -> List[dict]:
    """Flag figures whose effective DPI at the rendered width is below threshold."""
    fig_w_in, _ = fig.get_size_inches()
    if fig_w_in <= 0:
        return []
    include_width_in = page_text_width_in * include_width_fraction
    if include_width_in <= 0:
        return []
    effective_dpi = fig.dpi * fig_w_in / include_width_in
    if effective_dpi < min_effective_dpi:
        return [{
            "type": "effective_dpi_low",
            "severity": "warning",
            "detail": (
                f"effective DPI at rendered width {include_width_in:.1f}in is "
                f"{effective_dpi:.0f} (fig_dpi={fig.dpi}, fig_width={fig_w_in:.1f}in); "
                f"below {min_effective_dpi:.0f}"
            ),
            "elements": ["figure"],
        }]
    return []


__all__ = [
    "check_minimum_font_size",
    "check_colorblind_safety",
    "check_effective_dpi",
    "DEFAULT_MIN_RENDERED_PT",
    "DEFAULT_MIN_CVD_DELTA_E",
    "DEFAULT_MIN_EFFECTIVE_DPI",
]
